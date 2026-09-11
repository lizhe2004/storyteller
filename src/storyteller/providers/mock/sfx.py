from __future__ import annotations

from pathlib import Path

from ...core.sfx import SoundEffectProvider
from ...providers.base import BaseProvider


class MockSoundProvider(BaseProvider, SoundEffectProvider):
    """Sound provider that writes a short audible tone. Used for tests."""

    def __init__(self, config):
        super().__init__(config)
        self._error = None
        self.calls = []

    @property
    def name(self):
        return "mock"

    model = "mock-sound"

    def set_error(self, error):
        """Configure an error that subsequent generate() calls raise."""
        self._error = error

    def generate(
        self,
        prompt,
        output_path,
        *,
        audio_format="mp3",
        sample_rate=None,
        references=None,
    ):
        self.calls.append(
            {
                "prompt": prompt,
                "output_path": str(output_path),
                "audio_format": audio_format,
                "sample_rate": sample_rate,
                "references": references,
            }
        )
        if self._error is not None:
            raise self._error
        # Content is WAV regardless of the requested extension; pydub/ffmpeg
        # detect it from the bytes, matching the mock TTS provider. The tone is
        # deliberately audible so the sound-library loudness gate accepts it.
        from pydub.generators import Sine

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        Sine(440).to_audio_segment(duration=300).export(str(path), format="wav")
        return path, 0.3
