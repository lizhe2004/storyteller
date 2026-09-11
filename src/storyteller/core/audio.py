from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .models import SoundEffect
from .sound_library import MIN_SOUND_DBFS


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
        target = format or _format_for(output_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        segment.export(str(output_path), format=target)
        return output_path

    def mix_background(
        self,
        main_audio,
        background,
        output_path,
        bed_target_dbfs=-27,
        fade_ms=2000,
    ):
        """Lay a looping background bed under the main audio.

        The bed is normalized to an absolute target loudness rather than a
        fixed relative gain, because generated music clips vary widely in
        level (some arrive near -30 dBFS); a relative trim would leave those
        inaudible. The result loops to fill the main clip with edge fades.
        """
        from pydub import AudioSegment

        main = AudioSegment.from_file(str(main_audio))
        bed = AudioSegment.from_file(str(background))
        bed = self._match(bed, main)
        if bed.dBFS != float("-inf"):
            bed = bed.apply_gain(bed_target_dbfs - bed.dBFS)

        duration_ms = len(main)
        loops = duration_ms // len(bed) + 1 if len(bed) else 1
        bed = bed * loops
        bed = bed[:duration_ms]
        fade = min(fade_ms, duration_ms // 2) if duration_ms else 0
        if fade:
            bed = bed.fade_in(fade).fade_out(fade)

        mixed = main.overlay(bed)
        return self._export(mixed, output_path)

    def add_effects(self, main_audio, sound_effects, output_path):
        """Overlay each sound effect at its start_time (seconds) onto main."""
        from pydub import AudioSegment

        mixed = AudioSegment.from_file(str(main_audio))
        for effect in sound_effects:
            if not effect.source_path:
                continue
            clip = AudioSegment.from_file(str(effect.source_path))
            clip = self._match(clip, mixed)
            # A generated clip can be unusably quiet (a failed generation).
            # Skip near-silence rather than amplifying noise; lift an
            # abnormally-but-usably quiet effect up to a clear level.
            if clip.dBFS == float("-inf") or clip.dBFS < MIN_SOUND_DBFS:
                continue
            if clip.dBFS < _EFFECT_FLOOR_DBFS:
                clip = clip.apply_gain(_EFFECT_TARGET_DBFS - clip.dBFS)
            if effect.volume and effect.volume > 0:
                clip = clip + _gain_for_volume(effect.volume)
            if effect.fade_in:
                clip = clip.fade_in(int(effect.fade_in * 1000))
            if effect.fade_out:
                clip = clip.fade_out(int(effect.fade_out * 1000))
            position_ms = max(0, int((effect.start_time or 0.0) * 1000))
            mixed = mixed.overlay(clip, position=position_ms)
        return self._export(mixed, output_path)

    @staticmethod
    def _match(segment, reference):
        """Align frame rate and channel count before overlaying."""
        if segment.frame_rate != reference.frame_rate:
            segment = segment.set_frame_rate(reference.frame_rate)
        if segment.channels != reference.channels:
            segment = segment.set_channels(reference.channels)
        return segment

    @staticmethod
    def _export(segment, output_path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        segment.export(str(output_path), format=_format_for(output_path))
        return output_path



def _format_for(path):
    suffix = str(path).lower().rsplit(".", 1)[-1] if "." in str(path) else "mp3"
    if suffix in ("mp3", "wav", "ogg", "opus", "flac", "aac"):
        return suffix
    return "mp3"


def _gain_for_volume(volume):
    """Linear volume multiplier -> dB gain (1.0 -> 0 dB)."""
    import math

    if volume <= 0:
        return -120
    return 20.0 * math.log10(volume)


# Clips below MIN_SOUND_DBFS (imported from sound_library) are treated as
# failed (near-silent) generations and skipped rather than amplified into
# hiss. Usable-but-quiet effects below -40 dBFS are lifted to -20 dBFS;
# normal-level effects are unchanged.
_EFFECT_FLOOR_DBFS = -40
_EFFECT_TARGET_DBFS = -20
