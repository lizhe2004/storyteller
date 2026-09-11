import pytest

from storyteller.providers.volcengine.tts import load_voice_catalog

VALID_GENDERS = {"male", "female"}
VALID_AGES = {"child", "teen", "young_adult", "middle_aged", "senior"}
VALID_RESOURCES = {"seed-tts-2.0"}
NARRATION_CATEGORY = "有声阅读"


@pytest.fixture(autouse=True)
def _clear_cache():
    load_voice_catalog.cache_clear()
    yield
    load_voice_catalog.cache_clear()


def test_catalog_loads_and_is_nonempty():
    assert len(load_voice_catalog()) > 200


def test_catalog_records_have_required_fields():
    for v in load_voice_catalog():
        assert v["voice_id"]
        assert v["name"]
        assert "voice_type" not in v
        assert v["gender"] in VALID_GENDERS
        assert v["age"] in VALID_AGES
        assert v["language"] == "zh-CN"
        assert v["resource_id"] in VALID_RESOURCES
        assert isinstance(v["bilingual"], bool)
        assert "description" in v and isinstance(v["tags"], list)


def test_catalog_voice_ids_unique():
    voices = load_voice_catalog()
    ids = [v["voice_id"] for v in voices]
    assert len(ids) == len(set(ids))


def test_catalog_excludes_service_and_accent_voices():
    for v in load_voice_catalog():
        assert v["category"] not in ("客服场景", "陪聊", "直播")
        assert "口音" not in v["category"]


def test_catalog_has_narration_and_child_voices():
    voices = load_voice_catalog()
    assert any(v["category"] == NARRATION_CATEGORY for v in voices)
    children = [v for v in voices if v["age"] == "child"]
    assert len(children) >= 5


def test_catalog_narration_voices_sort_first():
    voices = load_voice_catalog()
    first_non_narration = next(
        i for i, v in enumerate(voices) if v["category"] != NARRATION_CATEGORY
    )
    assert all(
        v["category"] == NARRATION_CATEGORY for v in voices[:first_non_narration]
    )


def test_catalog_is_2_0_only_and_has_bilingual():
    voices = load_voice_catalog()
    assert {v["resource_id"] for v in voices} == VALID_RESOURCES
    assert any(v["bilingual"] for v in voices)
