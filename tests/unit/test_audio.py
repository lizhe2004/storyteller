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


def test_add_effect_groups_overlays_at_offsets(tmp_path):
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
    result = processor.add_effect_groups(
        main, [(1.0, None, [(effect, 0.0)])], out
    )

    assert result == out
    assert out.exists()
    combined = AudioSegment.from_wav(str(out))
    assert 1980 <= len(combined) <= 2020


def test_add_effect_groups_trims_clip_to_line_duration(tmp_path):
    from pydub import AudioSegment
    from storyteller.core.models import SoundEffect

    main = tmp_path / "main.wav"
    bed = tmp_path / "bed.wav"
    out = tmp_path / "with_bed.wav"
    from pydub import AudioSegment as _AS
    _AS.silent(duration=3000, frame_rate=16000).export(str(main), format="wav")
    # Ambient clip much longer than the owning line (0.8s).
    _tone(bed, 2000, freq=220)

    effect = SoundEffect(
        effect_id="e1",
        name="溪水",
        type="ambient",
        source_path=str(bed),
    )
    processor = PydubAudioProcessor()
    processor.add_effect_groups(main, [(0.0, 0.8, [(effect, 0.0)])], out)

    # The bed is cut at the line end (0.8s); everything after is silence.
    combined = AudioSegment.from_wav(str(out))
    assert combined[900:1500].dBFS == float("-inf")


def test_add_effect_groups_caps_combined_level(tmp_path):
    from pydub import AudioSegment
    from storyteller.core import audio as audio_mod
    from storyteller.core.models import SoundEffect

    main = tmp_path / "main.wav"
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    out = tmp_path / "capped.wav"
    # Silent backbone so the head level reflects only the effect group.
    from pydub import AudioSegment as AS
    AS.silent(duration=2000, frame_rate=16000).export(str(main), format="wav")
    _tone(a, 500, freq=440)
    _tone(b, 500, freq=660)

    effects = [
        SoundEffect(effect_id="e1", name="a", type="effect", source_path=str(a)),
        SoundEffect(effect_id="e2", name="b", type="effect", source_path=str(b)),
    ]
    processor = PydubAudioProcessor()
    processor.add_effect_groups(main, [(0.0, None, [(e, 0.0) for e in effects])], out)

    # Two effects each at -14 dBFS would stack to ~-11 dBFS; the group cap
    # must pull the combined head back down to the cap.
    mixed = AudioSegment.from_wav(str(out))
    assert mixed[:500].dBFS < audio_mod._GROUP_EFFECT_CAP_DBFS + 1.0


def test_add_effect_groups_skips_cues_without_source(tmp_path):
    from storyteller.core.models import SoundEffect

    main = tmp_path / "main.wav"
    out = tmp_path / "out.wav"
    _tone(main, 500)
    effect = SoundEffect(
        effect_id="e1", name="x", type="effect", source_path=None
    )
    processor = PydubAudioProcessor()
    processor.add_effect_groups(main, [(0.0, None, [(effect, 0.0)])], out)
    assert out.exists()


def test_add_effect_groups_skips_near_silent_generated_clip(tmp_path):
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
    processor.add_effect_groups(main, [(0.1, None, [(effect, 0.0)])], out)
    # Output is essentially the untouched main (clip was skipped).
    main_seg = AudioSegment.from_wav(str(main))
    out_seg = AudioSegment.from_wav(str(out))
    assert abs(len(out_seg) - len(main_seg)) <= 5


def test_add_effect_groups_places_cue_at_intra_offset(tmp_path):
    from pydub import AudioSegment as AS
    from storyteller.core.models import SoundEffect

    main = tmp_path / "main.wav"
    ping = tmp_path / "ping.wav"
    out = tmp_path / "offset.wav"
    AS.silent(duration=3000, frame_rate=16000).export(str(main), format="wav")
    _tone(ping, 200, freq=880)

    effect = SoundEffect(
        effect_id="e1", name="肚子", type="effect", source_path=str(ping)
    )
    processor = PydubAudioProcessor()
    # Group starts at 1.0s; cue fires 1.5s into the line -> 2.5s absolute.
    processor.add_effect_groups(
        main, [(1.0, None, [(effect, 1.5)])], out
    )
    combined = AS.from_wav(str(out))
    # Silence before the cue's absolute position (allow fade headroom).
    assert combined[1000:2400].dBFS == float("-inf")
    assert combined[2500:2700].dBFS > float("-inf")


def test_anchor_offset_proportional_to_text_position():
    from storyteller.core.models import ScriptLine, SoundEffect
    from storyteller.core.pipeline import Pipeline

    line = ScriptLine(
        line_id="11",
        line_type="narration",
        character_id=None,
        text="打了整整一个上午，锄头终于打好了。小锤肚子咕咕叫了起来。",
    )
    cue = SoundEffect(
        effect_id="e1", name="肚子", type="effect",
        anchor="肚子咕咕叫了起来",
    )
    offset = Pipeline._anchor_offset(line, cue, 10.0)
    # Anchor sits near the end (~80%) of the spoken text, not at the head.
    assert 6.5 < offset < 9.0

    # Ambient beds and missing anchors always start at the head.
    bed = SoundEffect(effect_id="e2", name="虫鸣", type="ambient")
    assert Pipeline._anchor_offset(line, bed, 10.0) == 0.0
    no_anchor = SoundEffect(effect_id="e3", name="x", type="effect")
    assert Pipeline._anchor_offset(line, no_anchor, 10.0) == 0.0


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
