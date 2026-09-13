from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment

from ..core.tts import STREAM_CHANNELS, STREAM_SAMPLE_RATE, STREAM_SAMPLE_WIDTH


def _standard(segment):
    return segment.set_frame_rate(STREAM_SAMPLE_RATE).set_channels(STREAM_CHANNELS).set_sample_width(STREAM_SAMPLE_WIDTH)


def audio_file_to_standard_pcm(path):
    return _standard(AudioSegment.from_file(str(path))).raw_data


def pcm_to_mp3_file(pcm, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    segment = AudioSegment(data=pcm, sample_width=STREAM_SAMPLE_WIDTH,
                           frame_rate=STREAM_SAMPLE_RATE, channels=STREAM_CHANNELS)
    segment.export(str(out_path), format="mp3")
    return out_path


def iter_pcm_frames(pcm, frame_ms=200):
    size = int(STREAM_SAMPLE_RATE * STREAM_SAMPLE_WIDTH * frame_ms / 1000)
    if size <= 0:
        raise ValueError("frame_ms must be positive")
    for offset in range(0, len(pcm), size):
        yield pcm[offset:offset + size]


def pcm_duration_ms(pcm):
    return int(len(pcm) * 1000 / (STREAM_SAMPLE_RATE * STREAM_SAMPLE_WIDTH * STREAM_CHANNELS))
