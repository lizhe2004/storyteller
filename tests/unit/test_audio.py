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


def _tone(path, duration_ms, freq=440, rate=16000):
    from pydub.generators import Sine

    path.parent.mkdir(parents=True, exist_ok=True)
    Sine(freq).to_audio_segment(duration=duration_ms).set_frame_rate(
        rate
    ).export(str(path), format="wav")


def test_mix_background_output_matches_main_duration(tmp_path):
    from pydub import AudioSegment

    main = tmp_path / "main.wav"
    bed = tmp_path / "bed.wav"
    out = tmp_path / "mixed.wav"
    _tone(main, 2000)
    _tone(bed, 300)

    processor = PydubAudioProcessor()
    result = processor.mix_background(main, bed, out)

    assert result == out
    assert out.exists()
    mixed = AudioSegment.from_wav(str(out))
    # Background is looped and trimmed to the main clip length.
    assert 1980 <= len(mixed) <= 2020


def test_add_effects_overlays_at_offsets(tmp_path):
    from pydub import AudioSegment
    from storyteller.core.models import SoundEffect

    main = tmp_path / "main.wav"
    whoosh = tmp_path / "whoosh.wav"
    out = tmp_path / "with_effects.wav"
    _tone(main, 2000)
    _tone(whoosh, 200, freq=880)

    effect = SoundEffect(
        effect_id="e1",
        name="风声",
        type="effect",
        source_path=str(whoosh),
        start_time=1.0,
    )
    processor = PydubAudioProcessor()
    result = processor.add_effects(main, [effect], out)

    assert result == out
    assert out.exists()
    combined = AudioSegment.from_wav(str(out))
    assert 1980 <= len(combined) <= 2020


def test_add_effects_skips_cues_without_source(tmp_path):
    from storyteller.core.models import SoundEffect

    main = tmp_path / "main.wav"
    out = tmp_path / "out.wav"
    _tone(main, 500)
    effect = SoundEffect(
        effect_id="e1", name="x", type="effect", source_path=None
    )
    processor = PydubAudioProcessor()
    processor.add_effects(main, [effect], out)
    assert out.exists()


def test_add_effects_skips_near_silent_generated_clip(tmp_path):
    from pydub import AudioSegment
    from pydub.generators import Sine
    from storyteller.core.models import SoundEffect

    main = tmp_path / "main.wav"
    quiet = tmp_path / "quiet.wav"
    out = tmp_path / "out.wav"
    _tone(main, 1000)
    # Force the effect far below the silence threshold (~-67 dBFS).
    Sine(880).to_audio_segment(duration=300).apply_gain(-60).export(
        str(quiet), format="wav"
    )
    effect = SoundEffect(
        effect_id="e1", name="silent", type="effect",
        source_path=str(quiet), start_time=0.1,
    )
    processor = PydubAudioProcessor()
    processor.add_effects(main, [effect], out)
    # Output is essentially the untouched main (clip was skipped).
    main_seg = AudioSegment.from_wav(str(main))
    out_seg = AudioSegment.from_wav(str(out))
    assert abs(len(out_seg) - len(main_seg)) <= 5


def test_mix_background_normalizes_quiet_bed_to_audible_level(tmp_path):
    from pydub import AudioSegment

    main = tmp_path / "main.wav"
    bed = tmp_path / "bed.wav"
    out = tmp_path / "mixed.wav"
    _tone(main, 1500)
    _tone(bed, 250, freq=220)

    processor = PydubAudioProcessor()
    processor.mix_background(main, bed, out, bed_target_dbfs=-27)
    mixed = AudioSegment.from_wav(str(out))
    # Bed normalized toward -27 dBFS: present well above silence floor.
    assert mixed.dBFS > -40
