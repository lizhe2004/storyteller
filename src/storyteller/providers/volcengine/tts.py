from __future__ import annotations

import base64
from collections import deque
import json
import math
import struct
import threading
import uuid
from functools import lru_cache
from pathlib import Path

import requests

from ...core.exceptions import TTSError
from ...core.models import VoiceConfig
from ...core.streaming_tts import StreamingTTSProvider, StreamingTTSSession
from ...core.tts import TTSProvider, StreamChunk, CHUNK_AUDIO, STREAM_SAMPLE_RATE
from ..base import BaseProvider

_DEFAULT_ENDPOINT = (
    "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
)
_DEFAULT_RESOURCE_ID = "seed-tts-2.0"
_DEFAULT_REALTIME_ENDPOINT = (
    "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
)
_DONE_CODE = 20000000
_VOICE_CATALOG = Path(__file__).with_name("voices.json")

_EVENT_START_CONNECTION = 1
_EVENT_CONNECTION_STARTED = 50
_EVENT_CONNECTION_FAILED = 51
_EVENT_START_SESSION = 100
_EVENT_CANCEL_SESSION = 101
_EVENT_FINISH_SESSION = 102
_EVENT_SESSION_STARTED = 150
_EVENT_SESSION_CANCELED = 151
_EVENT_SESSION_FINISHED = 152
_EVENT_SESSION_FAILED = 153
_EVENT_TASK_REQUEST = 200
_EVENT_TTS_AUDIO = 352


class _WebSocketTransport:
    """Small adapter around websocket-client's binary socket API."""

    def __init__(self, socket):
        self._socket = socket

    def send(self, frame):
        self._socket.send_binary(frame)

    def recv(self):
        return self._socket.recv()

    def close(self):
        self._socket.close()


def _open_realtime_transport(endpoint, headers):
    """Construct the optional websocket dependency only for realtime TTS."""
    try:
        import websocket
        socket = websocket.create_connection(
            endpoint,
            header=["{}: {}".format(key, value) for key, value in headers.items()],
            timeout=60,
        )
    except Exception as exc:
        raise TTSError("Volcengine realtime TTS connection failed") from exc
    return _WebSocketTransport(socket)


class VolcengineStreamingTTSSession(StreamingTTSSession):
    """One Volcengine bidirectional TTS session over an injected transport."""

    # Bound the wait for the terminal SESSION_FINISHED after FINISH is sent.
    _FINISH_TIMEOUT_SECONDS = 30.0

    def __init__(self, transport, voice, *, directives=None, context=None):
        self._transport = transport
        self._voice = voice
        self._directives = directives
        self._context = context
        self._session_id = uuid.uuid4().hex.encode("ascii")
        self._audio = deque()
        self._changed = threading.Condition(threading.Lock())
        self._reader = None
        self._reader_done = threading.Event()
        self._accepting = True
        self._finished = False
        self._cancelled = False
        self._transport_closed = False
        self._failure = None

        try:
            self._send(_EVENT_START_CONNECTION, {})
            self._expect_event(_EVENT_CONNECTION_STARTED)
            self._send(_EVENT_START_SESSION, self._session_request(), self._session_id)
            self._expect_event(_EVENT_SESSION_STARTED)
        except Exception:
            self._close_transport()
            raise

    def send_text(self, text):
        if not isinstance(text, str) or not text:
            raise TTSError("Volcengine realtime TTS text must be a non-empty string")
        send_error = None
        with self._changed:
            self._raise_if_unavailable()
            try:
                self._send(
                    _EVENT_TASK_REQUEST,
                    {"req_params": {"text": text}},
                    self._session_id,
                )
            except TTSError as exc:
                send_error = exc
        if send_error is not None:
            self._record_failure(TTSError("Volcengine realtime TTS send failed"))
            raise send_error

    def iter_audio(self):
        self._start_reader()
        while True:
            with self._changed:
                while not self._audio and not self._finished and self._failure is None:
                    self._changed.wait()
                if self._audio:
                    chunk = self._audio.popleft()
                elif self._failure is not None:
                    raise self._failure
                else:
                    return
            yield chunk

    def finish(self):
        with self._changed:
            if self._cancelled:
                if self._failure is not None:
                    raise self._failure
                return
            if self._finished:
                if self._failure is not None:
                    raise self._failure
                return
            self._accepting = False
        try:
            self._send(_EVENT_FINISH_SESSION, {}, self._session_id)
        except Exception as exc:
            if isinstance(exc, TTSError):
                error = exc
            else:
                error = TTSError("Volcengine realtime TTS finish failed")
            self._record_failure(error)
            if error is exc:
                raise
            raise error from exc
        self._start_reader()
        if not self._reader_done.wait(self._FINISH_TIMEOUT_SECONDS):
            error = TTSError("Volcengine realtime TTS finish timed out")
            # Closing the transport unblocks the reader; it then records the failure.
            self._record_failure(error)
            raise error
        with self._changed:
            if self._failure is not None:
                raise self._failure

    def cancel(self):
        with self._changed:
            if self._cancelled:
                return
            self._accepting = False
            self._cancelled = True
            self._audio.clear()
            should_cancel = not self._finished and self._failure is None
            self._changed.notify_all()
        if should_cancel:
            try:
                self._send(_EVENT_CANCEL_SESSION, {}, self._session_id)
            except Exception:
                pass
        self._close_transport()
        with self._changed:
            self._finished = True
            self._changed.notify_all()

    def _session_request(self):
        audio_params = {
            "format": "pcm",
            "sample_rate": STREAM_SAMPLE_RATE,
            "speech_rate": _clamp(
                int(round((self._voice.speed - 1.0) * 100)), -50, 100,
            ),
            "loudness_rate": _clamp(
                int(round((self._voice.volume - 1.0) * 100)), -50, 100,
            ),
        }
        req_params = {
            "speaker": self._voice.voice_id,
            "audio_params": audio_params,
        }
        context_texts = _build_context_texts(self._directives, self._context)
        if context_texts:
            req_params["additions"] = json.dumps(
                {"context_texts": context_texts}, ensure_ascii=False,
            )
        if self._voice.pitch != 1.0:
            semitones = _clamp(
                int(round(12 * _safe_log2(self._voice.pitch))), -12, 12,
            )
            if semitones:
                req_params["post_process"] = {"pitch": semitones}
        return {"req_params": req_params}

    def _send(self, event, payload, session_id=None):
        try:
            self._transport.send(_build_realtime_frame(event, payload, session_id))
        except TTSError:
            raise
        except Exception as exc:
            raise TTSError("Volcengine realtime TTS transport failed") from exc

    def _expect_event(self, expected_event):
        event, payload = _parse_realtime_frame(self._receive())
        if event == _EVENT_CONNECTION_FAILED:
            raise _realtime_failure(
                "Volcengine realtime TTS connection failed", payload,
            )
        if event != expected_event:
            raise TTSError(
                "Volcengine realtime TTS protocol error: expected event {}, got {}".format(
                    expected_event, event,
                )
            )

    def _receive(self):
        try:
            frame = self._transport.recv()
        except Exception as exc:
            raise TTSError("Volcengine realtime TTS receive failed") from exc
        if not isinstance(frame, bytes):
            raise TTSError("Volcengine realtime TTS returned a non-binary frame")
        return frame

    def _start_reader(self):
        with self._changed:
            if self._reader is not None:
                return
            self._reader = threading.Thread(
                target=self._read_until_terminal,
                name="volcengine-realtime-tts",
                daemon=True,
            )
            self._reader.start()

    def _read_until_terminal(self):
        try:
            while True:
                try:
                    frame = self._transport.recv()
                except Exception as exc:
                    # A read deadline on a quiet connection is not a failure: the
                    # opening session stays open across whole-script generation.
                    # Keep reading; finish() bounds the terminal-frame wait.
                    if self._is_idle_timeout(exc):
                        with self._changed:
                            if self._cancelled or self._finished or self._failure is not None:
                                return
                        continue
                    raise TTSError("Volcengine realtime TTS receive failed") from exc
                event, payload = _parse_realtime_frame(frame)
                if event == _EVENT_TTS_AUDIO:
                    if payload:
                        with self._changed:
                            if self._cancelled:
                                return
                            self._audio.append(StreamChunk(CHUNK_AUDIO, payload))
                            self._changed.notify_all()
                    continue
                if event == _EVENT_SESSION_FINISHED:
                    if _realtime_status_failed(payload):
                        raise _realtime_failure(
                            "Volcengine realtime TTS session failed", payload,
                        )
                    with self._changed:
                        self._finished = True
                        self._changed.notify_all()
                    return
                if event in (_EVENT_SESSION_CANCELED, _EVENT_SESSION_FAILED):
                    raise _realtime_failure("Volcengine realtime TTS session failed", payload)
        except TTSError as exc:
            self._record_failure(exc)
        except Exception as exc:
            self._record_failure(
                TTSError("Volcengine realtime TTS receive failed")
            )
        finally:
            self._close_transport()
            self._reader_done.set()

    def _record_failure(self, error):
        with self._changed:
            if self._failure is None:
                self._failure = error
            self._accepting = False
            self._finished = True
            self._changed.notify_all()
        self._close_transport()

    @staticmethod
    def _is_idle_timeout(exc):
        # websocket-client raises WebSocketTimeoutException on a read deadline.
        # Match by name to keep the optional dependency import lazy/coupling-free.
        return type(exc).__name__ == "WebSocketTimeoutException"

    def _raise_if_unavailable(self):
        if self._failure is not None:
            raise self._failure
        if not self._accepting:
            raise TTSError("Volcengine realtime TTS session is closed")

    def _close_transport(self):
        with self._changed:
            if self._transport_closed:
                return
            self._transport_closed = True
        try:
            self._transport.close()
        except Exception:
            pass


class VolcengineTTS(BaseProvider, TTSProvider, StreamingTTSProvider):
    """Volcengine text-to-speech provider (v3 seed-tts streaming API)."""

    supports_streaming = True

    def __init__(self, config, provider_name="volcengine"):
        super().__init__(config)
        self.provider_name = provider_name
        provider_config = config.get(
            "tts.provider_config.{}".format(provider_name), {}
        ) or {}
        self.api_key = provider_config.get("api_key")
        self.endpoint = _DEFAULT_ENDPOINT
        self.resource_id = (
            provider_config.get("resource_id") or _DEFAULT_RESOURCE_ID
        )
        self.realtime_endpoint = (
            provider_config.get("realtime_endpoint") or _DEFAULT_REALTIME_ENDPOINT
        ).rstrip("/")

        if not self.api_key:
            raise TTSError(
                "Volcengine TTS api_key is missing "
                "(STORYTELLER_TTS_VOLCENGINE_API_KEY)"
            )

        self._session = requests.Session()
        self._realtime_transport_factory = _open_realtime_transport

    @property
    def name(self):
        return self.provider_name

    @property
    def display_name(self):
        return "火山引擎"

    @property
    def display_description(self):
        return "seed-tts 2.0 语音合成（火山方舟）"

    def _resource_id_for(self, voice_id):
        """Resource id for a voice from the catalog, else the configured one.

        All shipped voices are seed-tts-2.0, but the lookup lets future
        voices (e.g. seed-icl-2.0 clones) carry their own resource id.
        """
        record = load_voice_index().get(voice_id)
        if record:
            return record.get("resource_id", self.resource_id)
        return self.resource_id

    def list_voices(self, **kwargs):
        return [
            VoiceConfig(
                provider=self.provider_name,
                voice_id=record["voice_id"],
                language=record.get("language", "zh-CN"),
                name=record.get("name"),
                gender=record.get("gender"),
                age=record.get("age"),
                category=record.get("category"),
                description=record.get("description"),
            )
            for record in load_voice_catalog()
        ]

    def open_stream(self, voice, *, directives=None, context=None):
        headers = {
            "X-Api-Key": self.api_key,
            "X-Api-Resource-Id": self._resource_id_for(voice.voice_id),
            "X-Api-Connect-Id": uuid.uuid4().hex,
        }
        try:
            transport = self._realtime_transport_factory(
                self.realtime_endpoint, headers,
            )
            return VolcengineStreamingTTSSession(
                transport, voice, directives=directives, context=context,
            )
        except TTSError:
            raise
        except Exception as exc:
            raise TTSError("Volcengine realtime TTS connection failed") from exc

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

        audio_format = _encoding_for_path(output_path)
        headers, body = self._build_request(
            text, voice_config, audio_format, directives, context)

        response = None
        try:
            response = self._session.post(
                self.endpoint,
                headers=headers,
                json=body,
                stream=True,
                timeout=60,
            )
            response.raise_for_status()
            audio_bytes = b"".join(self._iter_ndjson(response))
        except requests.RequestException as exc:
            raise TTSError(
                "Volcengine TTS request failed: {}".format(exc)
            ) from exc
        finally:
            if response is not None:
                response.close()

        if not audio_bytes:
            raise TTSError("Volcengine TTS returned no audio data")

        output_path.write_bytes(bytes(audio_bytes))
        return output_path

    def _build_request(self, text, voice_config, audio_format, directives, context):
        audio_params = {
            "format": audio_format,
            "sample_rate": 48000 if audio_format == "ogg_opus" else STREAM_SAMPLE_RATE,
            "speech_rate": _clamp(int(round((voice_config.speed - 1.0) * 100)), -50, 100),
            "loudness_rate": _clamp(int(round((voice_config.volume - 1.0) * 100)), -50, 100),
        }
        additions = {"disable_markdown_filter": True, "disable_emoji_filter": True}
        context_texts = _build_context_texts(directives, context)
        if context_texts:
            additions["context_texts"] = context_texts
        req_params = {
            "text": text, "speaker": voice_config.voice_id,
            "audio_params": audio_params,
            "additions": json.dumps(additions, ensure_ascii=False),
        }
        if voice_config.pitch != 1.0:
            semitones = _clamp(int(round(12 * _safe_log2(voice_config.pitch))), -12, 12)
            if semitones:
                req_params["post_process"] = {"pitch": semitones}
        headers = {
            "X-Api-Key": self.api_key,
            "X-Api-Resource-Id": self._resource_id_for(voice_config.voice_id),
            "X-Api-Request-Id": uuid.uuid4().hex,
            "Content-Type": "application/json", "Connection": "keep-alive",
        }
        return headers, {"req_params": req_params}

    def _iter_ndjson(self, response):
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError as exc:
                raise TTSError(
                    "Invalid JSON chunk from Volcengine TTS"
                ) from exc

            code = data.get("code", 0)
            if code == _DONE_CODE:
                break
            if code > 0:
                raise TTSError(
                    "Volcengine TTS error (code {}): {}".format(
                        code, data.get("message", "unknown")
                    )
                )
            chunk = data.get("data")
            if chunk:
                try:
                    yield base64.b64decode(chunk)
                except (ValueError, TypeError) as exc:
                    raise TTSError(
                        "Failed to decode Volcengine audio chunk"
                    ) from exc
    def _read_stream(self, response):
        return bytearray(b"".join(self._iter_ndjson(response)))

    def stream_synthesize(self, text, voice_config, *, directives=None, context=None):
        headers, body = self._build_request(
            text, voice_config, "pcm", directives, context)
        response = None
        try:
            response = self._session.post(
                self.endpoint, headers=headers, json=body,
                stream=True, timeout=60)
            response.raise_for_status()
            for piece in self._iter_ndjson(response):
                yield StreamChunk(CHUNK_AUDIO, bytes(piece))
        except requests.RequestException as exc:
            raise TTSError("Volcengine TTS request failed: {}".format(exc)) from exc
        finally:
            if response is not None:
                response.close()


def _encoding_for_path(output_path):
    suffix = output_path.suffix.lower().lstrip(".")
    if suffix in ("mp3", "wav", "pcm", "ogg", "opus"):
        if suffix == "ogg":
            return "ogg_opus"
        return suffix
    return "mp3"


def _build_realtime_frame(event, payload, session_id=None):
    """Build a documented Volcengine v3 JSON frame with an optional session."""
    try:
        payload_bytes = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TTSError("Volcengine realtime TTS could not encode request") from exc
    frame = bytearray(b"\x11\x14\x10\x00")
    frame.extend(struct.pack(">I", event))
    if session_id is not None:
        frame.extend(struct.pack(">I", len(session_id)))
        frame.extend(session_id)
    frame.extend(struct.pack(">I", len(payload_bytes)))
    frame.extend(payload_bytes)
    return bytes(frame)


def _parse_realtime_frame(frame):
    """Return ``(event, payload)`` or raise a provider-safe protocol error."""
    if len(frame) < 4 or frame[0] != 0x11:
        raise TTSError("Volcengine realtime TTS returned an invalid protocol frame")
    message_type = frame[1] >> 4
    if message_type == 0xF:
        if len(frame) < 12:
            raise TTSError("Volcengine realtime TTS returned a truncated error frame")
        code = struct.unpack(">I", frame[4:8])[0]
        payload_size = struct.unpack(">I", frame[8:12])[0]
        payload = _realtime_json(frame[12:], payload_size)
        raise _realtime_failure(
            "Volcengine realtime TTS error (code {})".format(code), payload,
        )
    if message_type not in (0x9, 0xB) or (frame[1] & 0x0F) != 0x04:
        raise TTSError("Volcengine realtime TTS returned an unsupported protocol frame")
    if len(frame) < 16:
        raise TTSError("Volcengine realtime TTS returned a truncated protocol frame")
    event = struct.unpack(">I", frame[4:8])[0]
    session_size = struct.unpack(">I", frame[8:12])[0]
    payload_offset = 12 + session_size
    if len(frame) < payload_offset + 4:
        raise TTSError("Volcengine realtime TTS returned a truncated session frame")
    payload_size = struct.unpack(">I", frame[payload_offset:payload_offset + 4])[0]
    payload = frame[payload_offset + 4:]
    if len(payload) != payload_size:
        raise TTSError("Volcengine realtime TTS returned a truncated payload")
    if message_type == 0xB:
        return event, payload
    return event, _realtime_json(payload, payload_size)


def _realtime_json(payload, payload_size):
    if len(payload) != payload_size:
        raise TTSError("Volcengine realtime TTS returned a truncated payload")
    if not payload:
        return {}
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise TTSError("Volcengine realtime TTS returned invalid JSON") from exc
    return data if isinstance(data, dict) else {}


def _realtime_failure(prefix, payload):
    message = payload.get("message") if isinstance(payload, dict) else None
    status = None
    if isinstance(payload, dict):
        status = payload.get("status_code", payload.get("code"))
    detail = message or "unknown"
    if status is not None:
        detail = "status {}: {}".format(status, detail)
    return TTSError("{}: {}".format(prefix, detail))


def _realtime_status_failed(payload):
    if not isinstance(payload, dict):
        return False
    status = payload.get("status_code", payload.get("code"))
    return status not in (None, 0, _DONE_CODE)


def _clamp(value, low, high):
    return max(low, min(high, value))


def _build_context_texts(directives, context):
    """Assemble additions.context_texts.

    Directives are acting instructions and get a leading "#"; quoted
    context (recent narration / previous line) is passed verbatim and is
    not synthesized. Order: directives first, then context.
    """
    texts = []
    for d in directives or []:
        d = (d or "").strip()
        if d:
            texts.append(d if d.startswith("#") else "#" + d)
    for c in context or []:
        c = (c or "").strip()
        if c:
            texts.append(c)
    return texts


def _safe_log2(value):
    return math.log(value, 2) if value and value > 0 else 0.0


@lru_cache(maxsize=1)
def load_voice_catalog():
    """Return the packaged Volcengine voice records as a list of dicts.

    Each record has voice_id, name, gender, age, category,
    description, tags, language, bilingual, resource_id. Cached.
    """
    data = json.loads(_VOICE_CATALOG.read_text(encoding="utf-8"))
    return data["voices"]


@lru_cache(maxsize=1)
def load_voice_index():
    """Map voice_id -> record for the packaged catalog."""
    return {v["voice_id"]: v for v in load_voice_catalog()}
