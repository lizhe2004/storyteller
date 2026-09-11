import json

import pytest

from storyteller.core.sound_library import (
    MIN_SOUND_DBFS,
    SoundLibrary,
    fingerprint_for,
    normalize_prompt,
)


class _StubProvider:
    """Only the identity attributes find()/admit() hash on."""

    name = "fake"
    model = "fake-model-1"


def _write_tone(path, *, gain=0, duration_ms=200, freq=440):
    from pydub.generators import Sine

    path = path if hasattr(path, "parent") else __import__("pathlib").Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Sine(freq).to_audio_segment(duration=duration_ms).apply_gain(gain).export(
        str(path), format="wav"
    )
    return path


def test_admit_copies_audible_clip_into_library_and_keeps_source(tmp_path):
    library = SoundLibrary(tmp_path / "sounds")
    raw = _write_tone(tmp_path / "project" / "sounds" / "笛声.mp3")
    provider = _StubProvider()

    record = library.admit(
        raw, provider, prompt="远处的笛声", name="笛声", kind="ambient",
        description="悠扬笛声", tags=["古风", "宁静"], duration=1.5,
    )

    assert record["name"] == "笛声"
    assert record["kind"] == "ambient"
    assert record["description"] == "悠扬笛声"
    assert record["tags"] == ["古风", "宁静"]
    assert record["model"] == "fake-model-1"
    assert record["duration"] == 1.5
    assert record["prompt"] == "远处的笛声"
    assert record["fingerprint"]
    assert record["path"].startswith("snd_")
    # Library copy exists AND the project raw clip was copied, not moved.
    assert library.path_for(record).exists()
    assert raw.exists()
    assert len(library.all()) == 1


def test_find_returns_cached_record_and_skips_missing_file(tmp_path):
    library = SoundLibrary(tmp_path / "sounds")
    raw = _write_tone(tmp_path / "雨声.mp3")
    record = library.admit(
        raw, _StubProvider(), prompt="下雨声", name="雨声", kind="ambient"
    )

    found = library.find(_StubProvider(), "下雨声")
    assert found is not None
    assert found["id"] == record["id"]
    assert library.find(_StubProvider(), "雷声") is None

    # Index entry whose file vanished is treated as a miss.
    library.path_for(record).unlink()
    assert library.find(_StubProvider(), "下雨声") is None


def test_find_normalizes_prompt_and_format_participates(tmp_path):
    library = SoundLibrary(tmp_path / "sounds")
    _write_tone(tmp_path / "a.mp3")
    library.admit(
        tmp_path / "a.mp3", _StubProvider(),
        prompt="微风  鸟鸣", name="a", kind="ambient",
    )
    assert library.find(_StubProvider(), " 微风 鸟鸣 ") is not None
    assert library.find(_StubProvider(), "微风  鸟鸣", audio_format="wav") is None
    assert fingerprint_for("m", "同一提示", "mp3") != fingerprint_for(
        "m", "同一提示", "wav"
    )
    assert normalize_prompt(" 微风  鸟鸣 ") == "微风 鸟鸣"


def test_index_persisted_and_reloaded(tmp_path):
    root = tmp_path / "sounds"
    SoundLibrary(root).admit(
        _write_tone(tmp_path / "琴.mp3"), _StubProvider(),
        prompt="琴声", name="琴", kind="music", description="古琴",
        tags=["古风"],
    )

    data = json.loads((root / "index.json").read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert len(data["sounds"]) == 1
    stored = data["sounds"][0]
    assert stored["name"] == "琴"
    assert stored["description"] == "古琴"
    assert stored["tags"] == ["古风"]

    reloaded = SoundLibrary(root)
    assert len(reloaded.all()) == 1
    assert reloaded.find(_StubProvider(), "琴声") is not None


def test_search_filters_by_keyword_and_kind(tmp_path):
    library = SoundLibrary(tmp_path / "sounds")
    library.admit(
        _write_tone(tmp_path / "1.mp3"), _StubProvider(),
        prompt="gentle rain", name="雨声", description="窗外舒缓的下雨声",
        tags=["天气"], kind="ambient",
    )
    library.admit(
        _write_tone(tmp_path / "2.mp3"), _StubProvider(),
        prompt="thunder", name="雷声", description="远处隆隆雷声",
        tags=["风暴"], kind="sfx",
    )

    assert {r["name"] for r in library.search("雨")} == {"雨声"}
    assert {r["name"] for r in library.search("rain")} == {"雨声"}
    assert {r["name"] for r in library.search("声")} == {"雨声", "雷声"}
    assert len(library.search("声", kind="sfx")) == 1
    assert library.search("雷声")[0]["kind"] == "sfx"


def test_corrupt_index_is_treated_as_empty(tmp_path):
    root = tmp_path / "sounds"
    root.mkdir()
    (root / "index.json").write_text("{ not json", encoding="utf-8")
    library = SoundLibrary(root)
    assert library.all() == []
    assert library.find(_StubProvider(), "风声") is None
    record = library.admit(
        _write_tone(tmp_path / "风声.mp3"), _StubProvider(),
        prompt="风声", name="风", kind="ambient",
    )
    assert library.path_for(record).exists()


def test_empty_prompt_and_bad_kind_rejected(tmp_path):
    library = SoundLibrary(tmp_path / "sounds")
    raw = _write_tone(tmp_path / "x.mp3")
    with pytest.raises(ValueError):
        library.find(_StubProvider(), "  ")
    with pytest.raises(ValueError):
        library.admit(
            raw, _StubProvider(), prompt="  ", name="x"
        )
    with pytest.raises(ValueError):
        library.admit(
            raw, _StubProvider(), prompt="雨声", name="雨", kind="nope"
        )


def test_admit_near_silent_raises_and_keeps_source(tmp_path):
    from storyteller.core.exceptions import SoundGenerationError

    root = tmp_path / "sounds"
    library = SoundLibrary(root)
    raw = _write_tone(
        tmp_path / "project" / "sounds" / "雨后.mp3", gain=-70
    )

    with pytest.raises(SoundGenerationError) as exc_info:
        library.admit(
            raw, _StubProvider(), prompt="雨后", name="雨后", kind="ambient"
        )

    message = str(exc_info.value)
    assert "dBFS" in message
    # The raw clip path is reported so the user can find the kept file.
    assert "雨后.mp3" in message
    # Nothing registered, no library copy, source preserved.
    assert library.all() == []
    assert list(root.glob("snd_*")) == []
    assert not (root / "index.json").exists()
    assert raw.exists()


def test_admit_unreadable_clip_raises_and_keeps_source(tmp_path):
    from storyteller.core.exceptions import SoundGenerationError

    root = tmp_path / "sounds"
    library = SoundLibrary(root)
    raw = tmp_path / "broken.mp3"
    raw.write_bytes(b"not an audio file")

    with pytest.raises(SoundGenerationError):
        library.admit(
            raw, _StubProvider(), prompt="坏文件", name="坏文件", kind="sfx"
        )
    assert library.all() == []
    assert raw.exists()


def test_failed_admit_can_be_retried(tmp_path):
    library = SoundLibrary(tmp_path / "sounds")
    silent = _write_tone(tmp_path / "雨后.mp3", gain=-70)
    with pytest.raises(Exception):
        library.admit(
            silent, _StubProvider(), prompt="雨后", name="雨后", kind="ambient"
        )
    # Replace the raw clip with an audible one and retry.
    _write_tone(silent, gain=0)
    record = library.admit(
        silent, _StubProvider(), prompt="雨后", name="雨后", kind="ambient"
    )
    assert library.path_for(record).exists()
    assert len(library.all()) == 1
