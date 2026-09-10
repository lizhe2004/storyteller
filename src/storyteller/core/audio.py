from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .models import SoundEffect


class AudioProcessor(ABC):
    """Abstract interface for audio post-processing.

    Knows only about audio files. Knows nothing about stories.
    """

    @abstractmethod
    def concatenate(self, audio_paths, output_path):
        """Concatenate a list of audio files into one. Returns output Path."""
        raise NotImplementedError

    @abstractmethod
    def convert_format(self, input_path, output_path, format="mp3", **kwargs):
        """Convert an audio file to a different format. Returns output Path."""
        raise NotImplementedError

    def mix_background(self, main_audio, background, output_path):
        """Mix a background sound under the main audio (reserved)."""
        raise NotImplementedError("mix_background not implemented")

    def add_effects(self, main_audio, sound_effects, output_path):
        """Layer sound effects onto the main audio (reserved)."""
        raise NotImplementedError("add_effects not implemented")
