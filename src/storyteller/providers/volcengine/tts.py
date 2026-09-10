from __future__ import annotations

import base64
import uuid
from pathlib import Path

import requests

from ...core.exceptions import TTSError
from ...core.models import VoiceConfig
from ...core.tts import TTSProvider
from ..base import BaseProvider

_DEFAULT_ENDPOINT = "https://openspeech.bytedance.com/api/v1/tts"
_SUCCESS_CODE = 3000


# A curated set of commonly used Volcengine voices. voice_id maps to the
# API's voice_type. This list can be extended via configuration later.
_BUILTIN_VOICES = [
    ("BV001_streaming", "narrator", "通用女声"),
    ("BV002_streaming", "narrator", "通用男声"),
    ("BV700_streaming", "female", "灿灿"),
    ("BV701_streaming", "male", "炀炀"),
    ("BV123_streaming", "male", "擎苍"),
    ("BV406_streaming", "female", "柠柠"),
    ("BV407_streaming", "child", "萌童"),
    ("BV021_streaming", "female", "通用赘婿-女声"),
    ("BV027_streaming", "male", "通用赘婿-男声"),
]


class VolcengineTTS(BaseProvider, TTSProvider):
    """Volcengine text-to-speech provider (HTTP synchronous API)."""

    def __init__(self, config):
        super().__init__(config)
        provider_config = config.get(
            "tts.provider_config.volcengine", {}
        ) or {}
        self.api_key = provider_config.get("api_key")
        self.endpoint = provider_config.get("endpoint") or _DEFAULT_ENDPOINT
        self.appid = provider_config.get("appid", "")
        self.cluster = provider_config.get("cluster", "volcano_tts")

        if not self.api_key:
            raise TTSError(
                "Volcengine TTS api_key is missing "
                "(STORYTELLER_TTS_VOLCENGINE_API_KEY)"
            )

        self._session = requests.Session()

    @property
    def name(self):
        return "volcengine"

    def list_voices(self, **kwargs):
        return [
            VoiceConfig(
                provider="volcengine",
                voice_id=voice_id,
                voice_type=voice_type,
                language="zh-CN",
            )
            for voice_id, voice_type, _desc in _BUILTIN_VOICES
        ]

    def synthesize(self, text, voice_config, output_path, **kwargs):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        encoding = _encoding_for_path(output_path)
        body = {
            "app": {
                "appid": self.appid,
                "token": self.api_key,
                "cluster": self.cluster,
            },
            "user": {"uid": "storyteller"},
            "audio": {
                "voice_type": voice_config.voice_id,
                "encoding": encoding,
                "speed_ratio": voice_config.speed,
                "volume_ratio": voice_config.volume,
                "pitch_ratio": voice_config.pitch,
            },
            "request": {
                "reqid": uuid.uuid4().hex,
                "text": text,
                "text_type": "plain",
                "operation": "query",
            },
        }

        headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            response = self._session.post(
                self.endpoint, headers=headers, json=body, timeout=60
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise TTSError(
                "Volcengine TTS request failed: {}".format(exc)
            ) from exc
        except ValueError as exc:
            raise TTSError("Invalid JSON from Volcengine TTS") from exc

        code = data.get("code")
        if code != _SUCCESS_CODE:
            raise TTSError(
                "Volcengine TTS error (code {}): {}".format(
                    code, data.get("message", "unknown")
                )
            )

        audio_b64 = data.get("data")
        if not audio_b64:
            raise TTSError("Volcengine TTS returned no audio data")

        try:
            audio_bytes = base64.b64decode(audio_b64)
        except (ValueError, TypeError) as exc:
            raise TTSError("Failed to decode Volcengine audio data") from exc

        output_path.write_bytes(audio_bytes)
        return output_path


def _encoding_for_path(output_path):
    suffix = output_path.suffix.lower().lstrip(".")
    if suffix in ("mp3", "wav", "pcm", "ogg", "opus"):
        if suffix == "ogg":
            return "ogg_opus"
        return suffix
    return "mp3"
