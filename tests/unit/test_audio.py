from pathlib import Path

import pytest

from storyteller.core.audio import PydubAudioProcessor


def _make_silence_clip(path, duration_ms=500):
    """Create a real silent WAV file using pydub."""
    from pydub import AudioSegment
    from pydub.generators import Sine

    clip = Sine(440).to_audio_segment(duration=duration_ms)
    path.parent.mkdir(parents=True, exist_ok=True)
    clip.export(str(path), format="wav")


def test_concatenate_combines_audio(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    out = tmp_path / "out.wav"
    _make_silence_clip(a, 500)
    _make_silence_clip(b, 500)

    processor = PydubAudioProcessor()
    result = processor.concatenate([a, b], out)

    assert result == out
    assert out.exists()

    from pydub import AudioSegment

    combined = AudioSegment.from_wav(str(out))
    # Two 500ms clips -> ~1000ms (allow small container padding)
    assert 990 <= len(combined) <= 1010


def test_concatenate_single_input(tmp_path):
    a = tmp_path / "a.wav"
    out = tmp_path / "out.wav"
    _make_silence_clip(a, 300)

    processor = PydubAudioProcessor()
    result = processor.concatenate([a], out)
    assert out.exists()

    from pydub import AudioSegment

    clip = AudioSegment.from_wav(str(out))
    assert 290 <= len(clip) <= 310


def test_convert_format_wav_to_mp3(tmp_path):
    src = tmp_path / "src.wav"
    dst = tmp_path / "dst.mp3"
    _make_silence_clip(src, 300)

    processor = PydubAudioProcessor()
    result = processor.convert_format(src, dst, format="mp3")
    assert result == dst
    assert dst.exists()
    assert dst.suffix == ".mp3"


def test_convert_format_mp3_to_wav(tmp_path):
    from pydub import AudioSegment
    from pydub.generators import Sine

    src = tmp_path / "src.mp3"
    dst = tmp_path / "dst.wav"
    Sine(440).to_audio_segment(duration=300).export(
        str(src), format="mp3"
    )

    processor = PydubAudioProcessor()
    result = processor.convert_format(src, dst, format="wav")
    assert dst.exists()
    clip = AudioSegment.from_wav(str(dst))
    assert len(clip) > 0


def test_concatenate_empty_list_raises(tmp_path):
    out = tmp_path / "out.wav"
    processor = PydubAudioProcessor()
    with pytest.raises(ValueError):
        processor.concatenate([], out)


def test_concatenate_preserves_order(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    out = tmp_path / "out.wav"
    _make_silence_clip(a, 400)
    _make_silence_clip(b, 400)

    processor = PydubAudioProcessor()
    processor.concatenate([a, b], out)
    assert out.exists()

    from pydub import AudioSegment

    combined = AudioSegment.from_wav(str(out))
    # Order: a then b -> 400 + 400 ms
    assert 790 <= len(combined) <= 810
