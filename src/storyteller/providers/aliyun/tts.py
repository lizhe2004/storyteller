from __future__ import annotations

import json
import logging
import re
import struct
import tempfile
import threading
from collections import deque
from functools import lru_cache
from pathlib import Path

import requests

from ...core.exceptions import TTSError
from ...core.models import VoiceConfig
from ...core.streaming_tts import StreamingTTSProvider, StreamingTTSSession
from ...core.tts import CHUNK_AUDIO, StreamChunk, TTSProvider
from ..base import BaseProvider

_DEFAULT_ENDPOINT = "https://dashscope.aliyuncs.com"
_API_PATH = "/api/v1/services/audio/tts/SpeechSynthesizer"
_WORKSPACE_HTTP_ENDPOINT_TEMPLATE = (
    "https://{workspace_id}.cn-beijing.maas.aliyuncs.com"
)
_REALTIME_WS_URL_TEMPLATE = (
    "wss://{workspace_id}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference"
)
logger = logging.getLogger(__name__)
_DASHSCOPE_CONFIGURATION_LOCK = threading.Lock()


class _PCM22050To24000Resampler:
    """Incrementally resample mono s16le PCM without retaining full audio."""

    _SOURCE_RATE = 22050
    _TARGET_RATE = 24000

    def __init__(self):
        self._samples = []
        self._sample_offset = 0
        self._next_output = 0
        self._trailing_byte = b""

    def feed(self, data, final=False):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TTSError("Aliyun realtime TTS returned invalid PCM audio")
        data = self._trailing_byte + bytes(data)
        if len(data) % 2:
            self._trailing_byte = data[-1:]
            data = data[:-1]
        else:
            self._trailing_byte = b""
        if data:
            self._samples.extend(
                struct.unpack("<{}h".format(len(data) // 2), data)
            )
        if final and self._trailing_byte:
            raise TTSError("Aliyun realtime TTS returned invalid PCM audio")
        return self._drain(final)

    def _drain(self, final):
        audio = bytearray()
        sample_limit = self._sample_offset + len(self._samples)
        while True:
            source_numerator = self._next_output * self._SOURCE_RATE
            source_index = source_numerator // self._TARGET_RATE
            if source_index >= sample_limit:
                break
            next_index = source_index + 1
            if next_index >= sample_limit and not final:
                break
            left = self._samples[source_index - self._sample_offset]
            if next_index < sample_limit:
                right = self._samples[next_index - self._sample_offset]
            else:
                right = left
            remainder = source_numerator % self._TARGET_RATE
            sample = (
                left * (self._TARGET_RATE - remainder) + right * remainder
            ) // self._TARGET_RATE
            sample = max(-32768, min(32767, sample))
            audio.extend(struct.pack("<h", sample))
            self._next_output += 1

        next_source_index = (
            self._next_output * self._SOURCE_RATE
        ) // self._TARGET_RATE
        discard = max(0, next_source_index - self._sample_offset)
        if discard:
            del self._samples[:discard]
            self._sample_offset += discard
        return bytes(audio)


class _AliyunRealtimeCallback:
    """Small duck-typed DashScope callback that keeps SDK types optional."""

    def __init__(self, session):
        self._session = session

    def on_open(self):
        pass

    def on_event(self, message):
        pass

    def on_data(self, data):
        self._session._on_audio(data)

    def on_complete(self):
        self._session._on_complete()

    def on_error(self, message):
        self._session._on_error(message)

    def on_close(self):
        pass


class AliyunStreamingTTSSession(StreamingTTSSession):
    """Bridge DashScope's callback API to the provider-neutral iterator."""

    _QUEUE_SIZE = 16
    # Bound the wait for DashScope's on_complete/on_error callback after
    # streaming_complete; a missing terminal callback must hang neither the job
    # nor the scheduler slot.
    _FINISH_TIMEOUT_SECONDS = 30.0

    def __init__(self, synthesizer, api_key):
        self._synthesizer = synthesizer
        self._api_key = api_key
        self._audio = deque()
        self._changed = threading.Condition(threading.Lock())
        self._submission = threading.Lock()
        self._spill = None
        self._spill_read_offset = 0
        self._resampler = _PCM22050To24000Resampler()
        self._completion = threading.Event()
        self._accepting = True
        self._finishing = False
        self._completed = False
        self._cancelled = False
        self._failure = None

    def send_text(self, text):
        if not isinstance(text, str) or not text:
            raise TTSError("Aliyun realtime TTS text must be a non-empty string")
        try:
            submit = self._synthesizer.streaming_call
        except Exception:
            error = TTSError("Aliyun realtime TTS send failed")
            self._record_failure(error)
            raise error from None
        with self._submission:
            with self._changed:
                self._raise_if_unavailable()
            try:
                submit(text)
            except Exception:
                error = TTSError("Aliyun realtime TTS send failed")
                self._record_failure(error)
                raise error from None
            with self._changed:
                if self._failure is not None:
                    raise self._failure

    def iter_audio(self):
        while True:
            with self._changed:
                while (
                    not self._audio
                    and not self._spill_has_audio()
                    and not self._completed
                    and self._failure is None
                ):
                    self._changed.wait()
                if self._audio:
                    chunk = self._audio.popleft()
                    self._changed.notify_all()
                elif self._spill_has_audio():
                    chunk = StreamChunk(CHUNK_AUDIO, self._read_spilled_audio())
                elif self._failure is not None:
                    self._close_spill()
                    raise self._failure
                else:
                    self._close_spill()
                    return
            yield chunk

    def finish(self):
        with self._submission:
            with self._changed:
                if self._cancelled:
                    if self._failure is not None:
                        raise self._failure
                    return
                if self._failure is not None:
                    raise self._failure
                should_complete = not self._finishing and not self._completed
                if should_complete:
                    self._accepting = False
                    self._finishing = True
            if should_complete:
                try:
                    self._synthesizer.streaming_complete()
                except Exception:
                    self._record_failure(
                        TTSError("Aliyun realtime TTS finish failed")
                    )
        if not self._completion.wait(self._FINISH_TIMEOUT_SECONDS):
            error = TTSError("Aliyun realtime TTS finish timed out")
            self._record_failure(error)
            self._completion.set()
            try:
                cancel = getattr(self._synthesizer, "streaming_cancel", None)
                if callable(cancel):
                    cancel()
            except Exception:
                pass
            raise error
        with self._changed:
            if self._failure is not None:
                raise self._failure

    def cancel(self):
        try:
            cancel = getattr(self._synthesizer, "streaming_cancel", None)
        except Exception:
            cancel = None
        with self._submission:
            with self._changed:
                if self._cancelled:
                    return
                self._accepting = False
                self._cancelled = True
                self._completed = True
                self._audio.clear()
                self._close_spill()
                self._completion.set()
                self._changed.notify_all()
        if callable(cancel):
            try:
                cancel()
            except Exception:
                pass

    def _on_audio(self, data):
        try:
            with self._changed:
                if self._cancelled or self._failure is not None:
                    return
                audio = self._resampler.feed(data)
            if audio:
                self._enqueue(audio)
        except TTSError as exc:
            self._record_failure(exc)
        except Exception:
            self._record_failure(
                TTSError("Aliyun realtime TTS audio conversion failed")
            )

    def _on_complete(self):
        try:
            with self._changed:
                if self._cancelled or self._failure is not None:
                    return
                trailing_audio = self._resampler.feed(b"", final=True)
            if trailing_audio:
                self._enqueue(trailing_audio)
            with self._changed:
                if self._cancelled or self._failure is not None:
                    return
                self._completed = True
                self._completion.set()
                self._changed.notify_all()
        except TTSError as exc:
            self._record_failure(exc)
        except Exception:
            self._record_failure(
                TTSError("Aliyun realtime TTS audio conversion failed")
            )

    def _on_error(self, message):
        self._record_failure(_realtime_error(message, self._api_key))

    def _enqueue(self, audio):
        with self._changed:
            if self._cancelled or self._failure is not None:
                return
            if self._spill is None and len(self._audio) < self._QUEUE_SIZE:
                self._audio.append(StreamChunk(CHUNK_AUDIO, audio))
            else:
                # DashScope may invoke callbacks synchronously from
                # streaming_complete().  Blocking that callback at capacity
                # would deadlock the documented finish-before-drain pattern.
                # Keep the in-memory queue bounded and spill overflow in FIFO
                # order so callbacks, completion, and the iterator progress
                # independently without losing audio.
                if self._spill is None:
                    self._spill = tempfile.TemporaryFile(mode="w+b")
                self._spill.seek(0, 2)
                self._spill.write(struct.pack("<I", len(audio)))
                self._spill.write(audio)
                self._spill.flush()
            self._changed.notify_all()

    def _spill_has_audio(self):
        if self._spill is None:
            return False
        self._spill.seek(0, 2)
        return self._spill.tell() > self._spill_read_offset

    def _read_spilled_audio(self):
        self._spill.seek(self._spill_read_offset)
        size = struct.unpack("<I", self._spill.read(4))[0]
        data = self._spill.read(size)
        self._spill_read_offset += 4 + size
        return data

    def _close_spill(self):
        if self._spill is not None:
            self._spill.close()
            self._spill = None

    def _record_failure(self, error):
        with self._changed:
            if self._failure is None:
                self._failure = error
            self._accepting = False
            self._completed = True
            self._completion.set()
            self._changed.notify_all()

    def _raise_if_unavailable(self):
        if self._failure is not None:
            raise self._failure
        if not self._accepting:
            raise TTSError("Aliyun realtime TTS session is closed")


def _create_dashscope_synthesizer(**kwargs):
    """Lazily create the optional SDK client with per-session credentials."""
    try:
        import dashscope
        from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer
    except Exception:
        raise TTSError("Aliyun realtime TTS requires the DashScope SDK") from None

    audio_format = getattr(AudioFormat, kwargs.pop("format"))
    api_key = kwargs.pop("api_key")
    websocket_api_url = kwargs.pop("websocket_api_url")
    with _DASHSCOPE_CONFIGURATION_LOCK:
        previous_api_key = getattr(dashscope, "api_key", None)
        dashscope.api_key = api_key
        try:
            return SpeechSynthesizer(
                format=audio_format, url=websocket_api_url, **kwargs
            )
        except Exception:
            raise TTSError("Aliyun realtime TTS connection failed") from None
        finally:
            dashscope.api_key = previous_api_key


def _realtime_error(message, api_key):
    detail = str(message or "provider error")
    if api_key:
        detail = detail.replace(str(api_key), "[redacted]")
    detail = re.sub(
        r"(?i)(authorization|api[_ -]?key|bearer)\s*[:=]\s*[^\s,;]+",
        r"\1=[redacted]",
        detail,
    )
    detail = re.sub(
        r"(?:https?|wss?)://[^\s]+\?[^\s]+",
        "[signed-url-redacted]",
        detail,
    )
    return TTSError("Aliyun realtime TTS failed: {}".format(detail[:512]))


class AliyunTTS(BaseProvider, TTSProvider, StreamingTTSProvider):
    """Aliyun Bailian (Model Studio) text-to-speech provider.

    Speaks the Qwen-Audio-TTS model family through the non-streaming
    SpeechSynthesizer HTTP API: the response carries a 24-hour audio URL
    which is downloaded immediately so artifacts never depend on it.
    """

    def __init__(self, config, provider_name="aliyun"):
        super().__init__(config)
        self.provider_name = provider_name
        provider_config = config.get(
            "tts.provider_config.{}".format(provider_name), {}
        ) or {}
        self.api_key = provider_config.get("api_key")
        self.workspace_id = (provider_config.get("workspace_id") or "").strip()
        endpoint = (
            _WORKSPACE_HTTP_ENDPOINT_TEMPLATE.format(
                workspace_id=self.workspace_id
            )
            if self.workspace_id
            else _DEFAULT_ENDPOINT
        ).rstrip("/")
        self.endpoint = (
            endpoint
            if endpoint.endswith(_API_PATH)
            else endpoint + _API_PATH
        )
        # Optional allowlist of model names (exact match, comma-separated).
        # When set, list_voices only exposes catalog voices whose ``model``
        # is in this set, so voice matching never assigns a model that is not
        # enabled (e.g. a tier whose quota is exhausted). Voices already
        # assigned in saved projects still synthesize so resume works.
        # Empty/unset = all catalog models exposed (backwards compatible).
        self._enabled_models = frozenset(
            s.strip()
            for s in (provider_config.get("models") or "").split(",")
            if s.strip()
        ) or None
        self.websocket_api_url = (
            _REALTIME_WS_URL_TEMPLATE.format(workspace_id=self.workspace_id)
            if self.workspace_id
            else ""
        )

        if not self.api_key:
            raise TTSError(
                "Aliyun TTS api_key is missing "
                "(STORYTELLER_TTS_ALIYUN_API_KEY)"
            )

        self._session = requests.Session()
        self._realtime_synthesizer_factory = _create_dashscope_synthesizer

    @property
    def name(self):
        return self.provider_name

    @property
    def display_name(self):
        return "阿里云百炼"

    @property
    def display_description(self):
        return "Qwen-Audio-TTS 语音合成（阿里云百炼）"

    def list_voices(self, **kwargs):
        enabled = self._enabled_models
        return [
            VoiceConfig(
                provider=self.provider_name,
                voice_id=record["voice_id"],
                model=record.get("model"),
                language=record.get("language", "zh-CN"),
                name=record.get("name"),
                gender=record.get("gender"),
                age=record.get("age"),
                category=record.get("category"),
                description=record.get("description"),
            )
            for record in load_voice_catalog()
            if enabled is None or record.get("model") in enabled
        ]

    def list_models(self):
        """List selectable TTS models for the per-story model picker.

        Queries the Bailian model catalog (``GET /api/v1/models``) with
        the TTS capability filters when ``workspace_id`` is configured,
        and always merges in models from the packaged voice catalog so
        locally-known tiers remain selectable. Without ``workspace_id``
        only the catalog models are returned.
        """
        models = {
            record["model"]: False
            for record in load_voice_catalog()
            if record.get("model")
        }
        if not self.workspace_id:
            return [
                {"id": model, "retiring": False} for model in sorted(models)
            ]
        base = _WORKSPACE_HTTP_ENDPOINT_TEMPLATE.format(
            workspace_id=self.workspace_id
        )
        headers = {
            "Authorization": "Bearer {}".format(self.api_key),
            "Content-Type": "application/json",
        }
        page = 1
        while True:
            params = [
                ("capabilities", "TTS"),
                ("capabilities", "Realtime-Text-to-Speech"),
                ("page_no", str(page)),
                ("page_size", "100"),
            ]
            try:
                response = self._session.get(
                    base + "/api/v1/models",
                    headers=headers,
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as exc:
                raise TTSError(
                    "Aliyun model list request failed: {}".format(exc)
                ) from exc
            except ValueError as exc:
                raise TTSError("Invalid JSON from Aliyun model list") from exc
            output = data.get("output") or {}
            records = output.get("models") or []
            for record in records:
                model = record.get("model")
                if model:
                    offline = (record.get("inference_offline_info") or {}).get(
                        "offline_time"
                    )
                    models[model] = models.get(model, False) or bool(offline)
            total = output.get("total") or 0
            if not records or page * 100 >= total:
                return [
                    {"id": model, "retiring": retiring}
                    for model, retiring in sorted(models.items())
                ]
            page += 1

    def open_stream(self, voice, *, directives=None, context=None):
        if not self.websocket_api_url:
            raise TTSError(
                "Aliyun realtime TTS workspace_id is not configured "
                "(STORYTELLER_TTS_ALIYUN_WORKSPACE_ID)"
            )
        callback = _AliyunRealtimeCallback(None)
        volume = _clamp(
            int(round((voice.volume - 1.0) * 50)) + 50, 0, 100
        )
        try:
            synthesizer = self._realtime_synthesizer_factory(
                model=self._model_for(voice.voice_id),
                voice=voice.voice_id,
                format="PCM_22050HZ_MONO_16BIT",
                volume=volume,
                speech_rate=_clamp(voice.speed, 0.5, 2.0),
                pitch_rate=_clamp(voice.pitch, 0.5, 2.0),
                instruction=_build_instruction(directives) or None,
                callback=callback,
                api_key=self.api_key,
                websocket_api_url=self.websocket_api_url,
            )
        except TTSError:
            raise
        except Exception:
            raise TTSError("Aliyun realtime TTS connection failed") from None
        session = AliyunStreamingTTSSession(synthesizer, self.api_key)
        callback._session = session
        return session

    def synthesize(
        self,
        text,
        voice_config,
        output_path,
        directives=None,
        context=None,
        **kwargs,
    ):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        model = self._model_for(voice_config.voice_id)
        audio_format = _encoding_for_path(output_path)
        req_input = {
            "text": text,
            "voice": voice_config.voice_id,
            "format": audio_format,
            # opus is only supported at 48 kHz; other formats use 24 kHz.
            "sample_rate": 48000 if audio_format == "opus" else 24000,
        }

        # rate/pitch are native 0.5..2.0 multipliers, same scale as
        # VoiceConfig; volume is a 0..100 integer centered at 50.
        rate = _clamp(voice_config.speed, 0.5, 2.0)
        pitch = _clamp(voice_config.pitch, 0.5, 2.0)
        if rate != 1.0:
            req_input["rate"] = rate
        if pitch != 1.0:
            req_input["pitch"] = pitch
        if voice_config.volume != 1.0:
            req_input["volume"] = _clamp(
                int(round((voice_config.volume - 1.0) * 50)) + 50, 0, 100
            )

        instruction = _build_instruction(directives)
        if instruction:
            req_input["instruction"] = instruction

        headers = {
            "Authorization": "Bearer {}".format(self.api_key),
            "Content-Type": "application/json",
        }
        body = {"model": model, "input": req_input}

        response = None
        try:
            response = self._session.post(
                self.endpoint,
                headers=headers,
                json=body,
                timeout=120,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            error_payload = _response_payload(response)
            logger.error(
                "event=tts_request_failed provider=aliyun model=%s "
                "voice_id=%s request_input_json=%s http_status=%s "
                "response_code=%s response_message=%s request_id=%s",
                model,
                voice_config.voice_id,
                json.dumps(req_input, ensure_ascii=False, separators=(",", ":")),
                getattr(response, "status_code", None),
                error_payload.get("code"),
                error_payload.get("message"),
                error_payload.get("request_id"),
            )
            raise TTSError(
                "Aliyun TTS request failed: {}".format(
                    _error_detail(exc, response)
                )
            ) from exc
        except ValueError as exc:
            _log_request_failure(
                "non_json_response", model, voice_config, req_input, response
            )
            raise TTSError(
                "Aliyun TTS returned a non-JSON response"
            ) from exc

        audio_url = (
            payload.get("output", {}).get("audio", {}).get("url")
            if isinstance(payload, dict)
            else None
        )
        if not audio_url:
            _log_request_failure(
                "missing_audio_url", model, voice_config, req_input, response,
                payload=payload,
            )
            raise TTSError("Aliyun TTS returned no audio URL")

        download = None
        try:
            download = self._session.get(audio_url, timeout=60)
            download.raise_for_status()
            audio_bytes = download.content
        except requests.RequestException as exc:
            # Never echo str(exc) here: requests' HTTP/connection errors
            # embed the signed audio URL, a 24h credential, and this text
            # flows into pipeline error logs. The chained traceback
            # (from exc) stays local and keeps the detail for debugging.
            status_code = getattr(download, "status_code", None)
            _log_request_failure(
                "audio_download_failed", model, voice_config, req_input,
                response, payload={"download_http_status": status_code},
            )
            if status_code is not None:
                detail = "HTTP {}".format(status_code)
            else:
                detail = "network error ({})".format(type(exc).__name__)
            raise TTSError(
                "Aliyun TTS audio download failed: {}".format(detail)
            ) from exc

        if not audio_bytes:
            raise TTSError("Aliyun TTS audio download was empty")

        output_path.write_bytes(bytes(audio_bytes))
        return output_path

    def _model_for(self, voice_id):
        record = load_voice_index().get(voice_id)
        if not record:
            raise TTSError(
                "Unknown Aliyun voice {!r}; voice must exist in the "
                "packaged catalog".format(voice_id)
            )
        return record["model"]


def _encoding_for_path(output_path):
    suffix = output_path.suffix.lower().lstrip(".")
    if suffix in ("mp3", "wav", "pcm", "opus", "ogg"):
        if suffix == "ogg":
            return "opus"
        return suffix
    return "mp3"


def _clamp(value, low, high):
    return max(low, min(high, value))


def _build_instruction(directives):
    """Collapse acting directives into Aliyun's single `instruction`.

    Volcengine separates directives (#-prefixed) from quoted context;
    Aliyun has one instruction string, so directives are joined and the
    quoted context is dropped.
    """
    parts = []
    for d in directives or []:
        d = (d or "").strip().lstrip("#").strip()
        if d:
            parts.append(d)
    return "，".join(parts)


def _error_detail(exc, response):
    """Prefer the server's message field, fall back to the exception text."""
    if response is not None:
        try:
            payload = response.json()
        except (ValueError, AttributeError):
            payload = None
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("code")
            if message:
                return message
    return str(exc)


def _response_payload(response):
    if response is None:
        return {}
    try:
        payload = response.json()
    except (ValueError, AttributeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _log_request_failure(reason, model, voice_config, req_input, response,
                         payload=None):
    payload = payload if payload is not None else _response_payload(response)
    logger.error(
        "event=tts_request_diagnostic provider=aliyun reason=%s model=%s "
        "voice_id=%s request_input_json=%s http_status=%s response_code=%s "
        "response_message=%s request_id=%s",
        reason,
        model,
        voice_config.voice_id,
        json.dumps(req_input, ensure_ascii=False, separators=(",", ":")),
        getattr(response, "status_code", None),
        payload.get("code"),
        payload.get("message"),
        payload.get("request_id"),
    )


@lru_cache(maxsize=1)
def load_voice_catalog():
    """Return the packaged Aliyun voice records as a list of dicts.

    Each record has voice_id, name, model, gender, age, category,
    description, tags, language, bilingual. Cached.
    """
    data = json.loads(_VOICE_CATALOG.read_text(encoding="utf-8"))
    return data["voices"]


@lru_cache(maxsize=1)
def load_voice_index():
    """Map voice_id -> record for the packaged catalog."""
    return {v["voice_id"]: v for v in load_voice_catalog()}


_VOICE_CATALOG = Path(__file__).with_name("voices.json")
