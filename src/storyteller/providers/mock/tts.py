from __future__ import annotations

import wave
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


def _write_silence_wav(path, duration_ms=100, frame_rate=16000):
    """Write a real silent WAV file using the stdlib wave module.

    pydub/ffmpeg can read this regardless of the file extension.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n_frames = int(frame_rate * duration_ms / 1000)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(frame_rate)
        wf.writeframes(b"\x00\x00" * n_frames)


class MockTTSProvider(BaseProvider, TTSProvider):
    """TTS provider that writes silent placeholder audio files. Used for tests."""

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
        _write_silence_wav(output_path)
        return Path(output_path)