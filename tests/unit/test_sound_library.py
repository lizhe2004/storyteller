import json

import pytest

from storyteller.core.sound_library import (
    SoundLibrary,
    fingerprint_for,
    normalize_prompt,
)


class _FakeProvider:
    """Records generate() calls and writes a short audible tone."""

    name = "fake"
    model = "fake-model-1"

    def __init__(self):
        self.calls = []

    def generate(self, prompt, output_path, *, audio_format="mp3", **kwargs):
        self.calls.append(
            {"prompt": prompt, "output_path": str(output_path),
             "audio_format": audio_format}
        )
        from pydub.generators import Sine

        output_path.parent.mkdir(parents=True, exist_ok=True)
        Sine(440).to_audio_segment(duration=200).export(
            str(output_path), format="wav"
        )
        return output_path, 1.5


def test_get_or_create_generates_on_first_call(tmp_path):
    provider = _FakeProvider()
    library = SoundLibrary(tmp_path / "sounds")

    path, record, created = library.get_or_create(
        provider, prompt="远处的笛声", name="笛声", kind="ambient",
        description="悠扬笛声", tags=["古风", "宁静"],
    )

    assert created is True
    assert path.exists()
    assert path.stat().st_size > 0
    assert len(provider.calls) == 1
    assert record["name"] == "笛声"
    assert record["kind"] == "ambient"
    assert record["description"] == "悠扬笛声"
    assert record["tags"] == ["古风", "宁静"]
    assert record["model"] == "fake-model-1"
    assert record["duration"] == 1.5
    assert record["prompt"] == "远处的笛声"
    assert record["fingerprint"]
    assert record["path"] == path.name


def test_same_prompt_is_cache_hit_without_provider_call(tmp_path):
    provider = _FakeProvider()
    library = SoundLibrary(tmp_path / "sounds")

    first, rec1, created1 = library.get_or_create(
        provider, prompt="下雨声", name="雨声", kind="ambient"
    )
    second, rec2, created2 = library.get_or_create(
        provider, prompt="下雨声", name="雨声（重复）", kind="ambient"
    )

    assert created1 is True
    assert created2 is False
    assert first == second
    assert rec1["id"] == rec2["id"]
    assert len(provider.calls) == 1
    # First-seen metadata is preserved on cache hit.
    assert rec2["name"] == "雨声"


def test_different_prompts_generate_separately(tmp_path):
    provider = _FakeProvider()
    library = SoundLibrary(tmp_path / "sounds")
    library.get_or_create(provider, prompt="雨声", name="雨", kind="ambient")
    library.get_or_create(provider, prompt="雷声", name="雷", kind="sfx")
    assert len(provider.calls) == 2
    assert len(library.all()) == 2


def test_prompt_normalization_matters_for_cache(tmp_path):
    provider = _FakeProvider()
    library = SoundLibrary(tmp_path / "sounds")
    library.get_or_create(provider, prompt="微风  鸟鸣", name="a", kind="ambient")
    library.get_or_create(provider, prompt=" 微风 鸟鸣 ", name="b", kind="ambient")
    assert len(provider.calls) == 1
    assert normalize_prompt(" 微风  鸟鸣 ") == "微风 鸟鸣"


def test_format_participates_in_fingerprint():
    fp_mp3 = fingerprint_for("m", "同一提示", "mp3")
    fp_wav = fingerprint_for("m", "同一提示", "wav")
    assert fp_mp3 != fp_wav


def test_index_persisted_and_reloaded(tmp_path):
    provider = _FakeProvider()
    root = tmp_path / "sounds"
    SoundLibrary(root).get_or_create(
        provider, prompt="琴声", name="琴", kind="music",
        description="古琴", tags=["古风"],
    )

    data = json.loads((root / "index.json").read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert len(data["sounds"]) == 1
    stored = data["sounds"][0]
    assert stored["name"] == "琴"
    assert stored["description"] == "古琴"
    assert stored["tags"] == ["古风"]

    # A fresh instance reads the same index and serves a cache hit.
    reloaded = SoundLibrary(root)
    assert len(reloaded.all()) == 1
    _, _, created = reloaded.get_or_create(
        provider, prompt="琴声", name="琴", kind="music"
    )
    assert created is False
    assert len(provider.calls) == 1


def test_search_filters_by_keyword_and_kind(tmp_path):
    provider = _FakeProvider()
    library = SoundLibrary(tmp_path / "sounds")
    library.get_or_create(
        provider, prompt="gentle rain", name="雨声",
        description="窗外舒缓的下雨声", tags=["天气"], kind="ambient",
    )
    library.get_or_create(
        provider, prompt="thunder", name="雷声",
        description="远处隆隆雷声", tags=["风暴"], kind="sfx",
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
    provider = _FakeProvider()
    library = SoundLibrary(root)
    assert library.all() == []
    path, _, created = library.get_or_create(
        provider, prompt="风声", name="风", kind="ambient"
    )
    assert created is True
    assert path.exists()


def test_missing_cached_file_triggers_regeneration(tmp_path):
    provider = _FakeProvider()
    library = SoundLibrary(tmp_path / "sounds")
    path, _, created = library.get_or_create(
        provider, prompt="雨声", name="雨", kind="ambient"
    )
    path.unlink()
    path2, _, created2 = library.get_or_create(
        provider, prompt="雨声", name="雨", kind="ambient"
    )
    assert created2 is True
    assert path2.exists()
    assert len(provider.calls) == 2


def test_empty_prompt_and_bad_kind_rejected(tmp_path):
    library = SoundLibrary(tmp_path / "sounds")
    with pytest.raises(ValueError):
        library.get_or_create(_FakeProvider(), prompt="  ", name="x")
    with pytest.raises(ValueError):
        library.get_or_create(
            _FakeProvider(), prompt="雨声", name="雨", kind="nope"
        )


class _NearSilentProvider:
    """Writes an audible-shaped but effectively silent clip (~-70 dBFS)."""

    name = "fake"
    model = "fake-model-1"

    def __init__(self):
        self.calls = []

    def generate(self, prompt, output_path, *, audio_format="mp3", **kwargs):
        self.calls.append(prompt)
        from pydub.generators import Sine

        output_path.parent.mkdir(parents=True, exist_ok=True)
        Sine(440).to_audio_segment(duration=200).apply_gain(-70).export(
            str(output_path), format="wav"
        )
        return output_path, 0.2


def test_near_silent_generation_is_discarded_and_not_cached(tmp_path):
    from storyteller.core.exceptions import SoundGenerationError

    provider = _NearSilentProvider()
    root = tmp_path / "sounds"
    library = SoundLibrary(root)

    with pytest.raises(SoundGenerationError):
        library.get_or_create(
            provider, prompt="雨后", name="雨后", kind="ambient"
        )

    # Nothing was registered, and the audio file was removed.
    assert library.all() == []
    assert list(root.glob("snd_*")) == []
    assert not (root / "index.json").exists()


def test_failed_silent_generation_is_retried_not_cache_hit(tmp_path):
    provider = _NearSilentProvider()
    library = SoundLibrary(tmp_path / "sounds")

    for _ in range(2):
        with pytest.raises(Exception):
            library.get_or_create(
                provider, prompt="雨后", name="雨后", kind="ambient"
            )

    # Both attempts reached the provider: the failure was never cached.
    assert len(provider.calls) == 2
    assert library.all() == []
