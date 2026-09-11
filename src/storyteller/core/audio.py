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

    def add_effect_groups(self, main_audio, groups, output_path):
        """Mix per-line sound effect groups onto the main audio.

        Each group is ``(start_sec, duration_sec, entries)`` where entries is a
        list of ``(effect, intra_offset_sec)``. Cues fire at
        ``start_sec + intra_offset_sec`` (an anchored punctual effect is offset
        to its trigger phrase; ambience starts at the line head), and the whole
        group is hard-cut at the owning line's end (``duration_sec``) so a long
        bed never spills into the next line. Cues are normalized by type, then
        the combined group is capped as a unit so simultaneous cues cannot
        stack loud enough to bury the narration.
        """
        raise NotImplementedError("add_effect_groups not implemented")


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

    def add_effect_groups(self, main_audio, groups, output_path):
        """Overlay per-line cue groups with per-group loudness caps and cuts.

        ``groups`` is a list of ``(start_sec, duration_sec, entries)`` with
        entries a list of ``(effect, intra_offset_sec)``. Each cue is placed at
        its intra-line offset (anchored punctual effects land on their trigger
        phrase; ambience starts at the head); clips running past the owning
        line's ``duration_sec`` are trimmed with a short tail fade so they
        cannot continue into the next line. Cues are normalized by type, then
        the combined group is capped as a unit.
        """
        from pydub import AudioSegment

        mixed = AudioSegment.from_file(str(main_audio))
        for start_sec, duration_sec, entries in groups:
            track = self._build_group_track(mixed, entries)
            if track is None:
                continue
            if duration_sec and len(track) > duration_sec * 1000:
                limit_ms = int(duration_sec * 1000)
                fade = min(_TAIL_FADE_MS, limit_ms // 2)
                track = track[:limit_ms].fade_out(fade)
            position_ms = max(0, int((start_sec or 0.0) * 1000))
            mixed = mixed.overlay(track, position=position_ms)
        return self._export(mixed, output_path)

    def _build_group_track(self, reference, entries):
        """Render one line's cues, each at its intra offset, capped together."""
        from pydub import AudioSegment

        placed = []
        has_effect = False
        for effect, offset_sec in entries:
            if not effect.source_path:
                continue
            clip = AudioSegment.from_file(str(effect.source_path))
            clip = self._match(clip, reference)
            # A generated clip can be unusably quiet (a failed generation).
            # Skip near-silence rather than amplifying noise.
            if clip.dBFS == float("-inf") or clip.dBFS < MIN_SOUND_DBFS:
                continue
            target = (
                _AMBIENT_TARGET_DBFS
                if effect.type in ("ambient", "music")
                else _EFFECT_TARGET_DBFS
            )
            clip = clip.apply_gain(target - clip.dBFS)
            if effect.volume and effect.volume > 0:
                clip = clip + _gain_for_volume(effect.volume)
            if effect.fade_in:
                clip = clip.fade_in(int(effect.fade_in * 1000))
            if effect.fade_out:
                clip = clip.fade_out(int(effect.fade_out * 1000))
            if effect.type not in ("ambient", "music"):
                has_effect = True
            placed.append((max(0, int((offset_sec or 0.0) * 1000)), clip))
        if not placed:
            return None

        end_ms = max(off + len(clip) for off, clip in placed)
        track = AudioSegment.silent(
            duration=end_ms, frame_rate=reference.frame_rate
        ).set_channels(reference.channels)
        for off, clip in placed:
            track = track.overlay(clip, position=off)

        # Cap the combined group: punctual effects may cut through but never
        # dominate the speech; ambience-only groups stay a bed.
        cap = _GROUP_EFFECT_CAP_DBFS if has_effect else _GROUP_AMBIENT_CAP_DBFS
        if track.dBFS != float("-inf") and track.dBFS > cap:
            track = track.apply_gain(cap - track.dBFS)
        return track

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


# Per-cue normalization targets (absolute dBFS): punctual effects sit just
# above the narration (~-22 dBFS) so they cut through; sustained ambience and
# music stay well under it. Clips below MIN_SOUND_DBFS (imported from
# sound_library) are failed generations and skipped entirely.
_EFFECT_TARGET_DBFS = -14
_AMBIENT_TARGET_DBFS = -27

# Combined-level caps for every cue group sharing one line. Without a cap,
# several cues each normalized to target stack 3-6 dB louder and bury the
# speech. A group containing effects may be present but not dominant; an
# ambience-only group stays a bed.
_GROUP_EFFECT_CAP_DBFS = -16
_GROUP_AMBIENT_CAP_DBFS = -22

# Tail fade when a clip is cut at the owning line's end.
_TAIL_FADE_MS = 600
