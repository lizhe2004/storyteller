from __future__ import annotations

import base64
import json
import math
import uuid
from functools import lru_cache
from pathlib import Path

import requests

from ...core.exceptions import TTSError
from ...core.models import VoiceConfig
from ...core.tts import TTSProvider, StreamChunk, CHUNK_AUDIO, STREAM_SAMPLE_RATE
from ..base import BaseProvider

_DEFAULT_ENDPOINT = (
    "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
)
_DEFAULT_RESOURCE_ID = "seed-tts-2.0"
_DONE_CODE = 20000000
_VOICE_CATALOG = Path(__file__).with_name("voices.json")


class VolcengineTTS(BaseProvider, TTSProvider):
    """Volcengine text-to-speech provider (v3 seed-tts streaming API)."""

    supports_streaming = True

    def __init__(self, config):
        super().__init__(config)
        provider_config = config.get(
            "tts.provider_config.volcengine", {}
        ) or {}
        self.api_key = provider_config.get("api_key")
        self.endpoint = (
            provider_config.get("endpoint") or _DEFAULT_ENDPOINT
        ).rstrip("/")
        self.resource_id = (
            provider_config.get("resource_id") or _DEFAULT_RESOURCE_ID
        )

        if not self.api_key:
            raise TTSError(
                "Volcengine TTS api_key is missing "
                "(STORYTELLER_TTS_VOLCENGINE_API_KEY)"
            )

        self._session = requests.Session()

    @property
    def name(self):
        return "volcengine"

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
                provider="volcengine",
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
