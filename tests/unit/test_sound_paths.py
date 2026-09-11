import pytest

from storyteller.core.sound_library import safe_sound_name, unique_path


def test_safe_sound_name_strips_illegal_characters():
    assert safe_sound_name('风吹/树叶:沙沙?') == "风吹_树叶_沙沙_"
    assert safe_sound_name('  雨声  ') == "雨声"
    assert safe_sound_name('a\\b*c') == "a_b_c"


def test_safe_sound_name_falls_back_when_empty():
    assert safe_sound_name("", fallback="sfx_abc123") == "sfx_abc123"
    assert safe_sound_name("   ", fallback="x") == "x"
    assert safe_sound_name(None) == "sound"
    assert safe_sound_name("...") == "sound"


def test_safe_sound_name_collapses_inner_whitespace():
    assert safe_sound_name("猴子  捞月\n") == "猴子 捞月"


def test_unique_path_appends_counter_on_collision(tmp_path):
    first = unique_path(tmp_path, "雨声", "mp3")
    first.write_bytes(b"a")
    second = unique_path(tmp_path, "雨声", "mp3")
    second.write_bytes(b"b")
    third = unique_path(tmp_path, "雨声", "mp3")
    assert first.name == "雨声.mp3"
    assert second.name == "雨声-2.mp3"
    assert third.name == "雨声-3.mp3"


def test_unique_path_creates_no_files(tmp_path):
    path = unique_path(tmp_path / "sounds", "雷声", "mp3")
    assert not path.exists()
    assert path.parent == tmp_path / "sounds"
