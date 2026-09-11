from __future__ import annotations

from pathlib import Path

import requests

from ...core.exceptions import TTSError
from ...core.models import VoiceConfig
from ...core.tts import TTSProvider
from ..base import BaseProvider


_BUILTIN_VOICES = [
    ("alloy", None),
    ("echo", None),
    ("fable", None),
    ("onyx", "male"),
    ("nova", "female"),
    ("shimmer", "female"),
    ("coral", "female"),
]


class OpenAICompatibleTTS(BaseProvider, TTSProvider):
    """OpenAI-compatible text-to-speech provider (e.g. custom endpoints)."""

    def __init__(self, config, provider_name=None):
        super().__init__(config)
        self.provider_name = provider_name or "openai_compatible"
        provider_config = (
            config.get("tts.provider_config.{}".format(self.provider_name))
            or {}
        )
        if not provider_config:
            raise TTSError(
                "No configuration found for TTS provider {}".format(
                    self.provider_name
                )
            )

        self.api_key = provider_config.get("api_key")
        self.base_url = provider_config.get("base_url", "https://api.openai.com/v1")
        self.model = provider_config.get("model", "tts-1")

        if not self.api_key:
            raise TTSError(
                "OpenAI-compatible TTS api_key is missing for {}".format(
                    self.provider_name
                )
            )

        self._session = requests.Session()

    @property
    def name(self):
        return self.provider_name

    @property
    def display_name(self):
        return self.provider_name

    @property
    def display_description(self):
        return "OpenAI 兼容 TTS 服务（{}）".format(self.model)

    def list_voices(self, **kwargs):
        return [
            VoiceConfig(
                provider=self.provider_name,
                voice_id=voice_id,
                gender=gender,
                language="zh-CN",
            )
            for voice_id, gender in _BUILTIN_VOICES
        ]

    def synthesize(self, text, voice_config, output_path, **kwargs):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        format_ = _format_for_path(output_path)
        body = {
            "model": self.model,
            "input": text,
            "voice": voice_config.voice_id,
            "response_format": format_,
        }

        url = "{}/audio/speech".format(self.base_url.rstrip("/"))
        headers = {
            "Authorization": "Bearer {}".format(self.api_key),
            "Content-Type": "application/json",
        }

        try:
            response = self._session.post(
                url, headers=headers, json=body, timeout=60
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise TTSError(
                "OpenAI-compatible TTS request failed: {}".format(exc)
            ) from exc

        output_path.write_bytes(response.content)
        return output_path


def _format_for_path(output_path):
    suffix = output_path.suffix.lower().lstrip(".")
    if suffix in ("mp3", "wav", "aac", "flac", "opus", "pcm"):
        return suffix
    return "mp3"
