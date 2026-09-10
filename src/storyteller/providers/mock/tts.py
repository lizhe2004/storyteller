from __future__ import annotations

from pathlib import Path

from ...core.models import VoiceConfig
from ...core.tts import TTSProvider
from ...providers.base import BaseProvider


MOCK_VOICES = [
    VoiceConfig(
        provider="mock",
        voice_id="narrator_01",
        voice_type="narrator",
        language="zh-CN",
    ),
    VoiceConfig(
        provider="mock",
        voice_id="male_01",
        voice_type="male",
        language="zh-CN",
    ),
    VoiceConfig(
        provider="mock",
        voice_id="female_01",
        voice_type="female",
        language="zh-CN",
    ),
    VoiceConfig(
        provider="mock",
        voice_id="child_01",
        voice_type="child",
        language="zh-CN",
    ),
]


# Minimal valid WAV header (44 bytes) for an empty 0-length PCM file.
# pydub/ffmpeg can read this; we just need a non-empty file for tests.
_WAV_HEADER = (
    b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00"
    b"\x01\x00\x40\x1f\x00\x00\x40\x1f\x00\x00\x01\x00\x08\x00"
    b"data\x00\x00\x00\x00"
)


class MockTTSProvider(BaseProvider, TTSProvider):
    """TTS provider that writes empty placeholder audio files. Used for tests."""

    def __init__(self, config):
        super().__init__(config)
        self._error = None
        self.synth_calls = []

    @property
    def name(self):
        return "mock"

    def list_voices(self, **kwargs):
        return list(MOCK_VOICES)

    def set_error(self, error):
        """Configure an error that subsequent synthesize() calls raise."""
        self._error = error

    def synthesize(self, text, voice_config, output_path, **kwargs):
        self.synth_calls.append(
            {
                "text": text,
                "voice_config": voice_config,
                "output_path": str(output_path),
                "kwargs": kwargs,
            }
        )
        if self._error is not None:
            raise self._error
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Write a small placeholder WAV so the file exists and is non-empty.
        output_path.write_bytes(_WAV_HEADER)
        return output_path
