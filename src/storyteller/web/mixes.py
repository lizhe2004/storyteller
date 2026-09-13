from __future__ import annotations

from pathlib import Path

from ..core.audio import PydubAudioProcessor


def mix_line_with_cues(voice_path, entries, output_path):
    return PydubAudioProcessor().mix_line(
        Path(voice_path), entries, Path(output_path))
