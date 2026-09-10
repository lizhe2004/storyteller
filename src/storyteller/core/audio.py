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


class PydubAudioProcessor(AudioProcessor):
    """Audio processor backed by pydub (which shells out to ffmpeg)."""

    def concatenate(self, audio_paths, output_path):
        if not audio_paths:
            raise ValueError("Cannot concatenate an empty list of audio files")

        from pydub import AudioSegment

        segments = [AudioSegment.from_file(str(p)) for p in audio_paths]
        combined = segments[0]
        for seg in segments[1:]:
            combined += seg

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        combined.export(str(output_path), format=_format_for(output_path))
        return output_path

    def convert_format(self, input_path, output_path, format="mp3", **kwargs):
        from pydub import AudioSegment

        segment = AudioSegment.from_file(str(input_path))
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        target = format or _format_for(output_path)
        segment.export(str(output_path), format=target)
        return output_path


def _format_for(path):
    suffix = str(path).lower().rsplit(".", 1)[-1] if "." in str(path) else "mp3"
    if suffix in ("mp3", "wav", "ogg", "opus", "flac", "aac"):
        return suffix
    return "mp3"
