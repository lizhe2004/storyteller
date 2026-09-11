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
from ...core.tts import TTSProvider
from ..base import BaseProvider

_DEFAULT_ENDPOINT = (
    "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
)
_DEFAULT_RESOURCE_ID = "seed-tts-2.0"
_DONE_CODE = 20000000
_VOICE_CATALOG = Path(__file__).with_name("voices.json")


class VolcengineTTS(BaseProvider, TTSProvider):
    """Volcengine text-to-speech provider (v3 seed-tts streaming API)."""

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
                voice_type=record["voice_type"],
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
        audio_params = {
            "format": audio_format,
            # ogg_opus is only supported at 48 kHz; others default to 24 kHz.
            "sample_rate": 48000 if audio_format == "ogg_opus" else 24000,
            # speech_rate / loudness_rate are integer offsets: 0 normal,
            # [-50, 100] (100 = 2x, -50 = 0.5x).
            "speech_rate": _clamp(
                int(round((voice_config.speed - 1.0) * 100)), -50, 100
            ),
            "loudness_rate": _clamp(
                int(round((voice_config.volume - 1.0) * 100)), -50, 100
            ),
        }
        additions = {
            # Strip markdown syntax and emoji so they are not read aloud.
            "disable_markdown_filter": True,
            "disable_emoji_filter": True,
        }
        context_texts = _build_context_texts(directives, context)
        if context_texts:
            # Voice directives use a leading "#"; quoted context does not.
            additions["context_texts"] = context_texts

        req_params = {
            "text": text,
            "speaker": voice_config.voice_id,
            "audio_params": audio_params,
            "additions": json.dumps(additions, ensure_ascii=False),
        }
        # post_process.pitch is semitones in [-12, 12], default 0.
        if voice_config.pitch != 1.0:
            semitones = _clamp(
                int(round(12 * _safe_log2(voice_config.pitch))), -12, 12
            )
            if semitones:
                req_params["post_process"] = {"pitch": semitones}
        body = {"req_params": req_params}

        headers = {
            "X-Api-Key": self.api_key,
            "X-Api-Resource-Id": self._resource_id_for(voice_config.voice_id),
            "X-Api-Request-Id": uuid.uuid4().hex,
            "Content-Type": "application/json",
            "Connection": "keep-alive",
        }

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
            audio_bytes = self._read_stream(response)
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

    @staticmethod
    def _read_stream(response):
        """Collect base64 audio chunks from the NDJSON response stream."""
        audio = bytearray()
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
                    audio.extend(base64.b64decode(chunk))
                except (ValueError, TypeError) as exc:
                    raise TTSError(
                        "Failed to decode Volcengine audio chunk"
                    ) from exc
        return audio


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

    Each record has voice_id, name, gender, age, voice_type, category,
    description, tags, language, bilingual, resource_id. Cached.
    """
    data = json.loads(_VOICE_CATALOG.read_text(encoding="utf-8"))
    return data["voices"]


@lru_cache(maxsize=1)
def load_voice_index():
    """Map voice_id -> record for the packaged catalog."""
    return {v["voice_id"]: v for v in load_voice_catalog()}
