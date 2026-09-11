import pytest

from storyteller.providers.volcengine.tts import load_voice_catalog

VALID_TYPES = {"male", "female", "child", "narrator"}
VALID_AGES = {"child", "teen", "young_adult", "middle_aged", "senior"}
VALID_RESOURCES = {"seed-tts-2.0"}


@pytest.fixture(autouse=True)
def _clear_cache():
    load_voice_catalog.cache_clear()
    yield
    load_voice_catalog.cache_clear()


def test_catalog_loads_and_is_nonempty():
    voices = load_voice_catalog()
    assert len(voices) > 200


def test_catalog_records_have_required_fields():
    for v in load_voice_catalog():
        assert v["voice_id"]
        assert v["name"]
        assert v["voice_type"] in VALID_TYPES
        assert v["gender"] in ("male", "female")
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


def test_catalog_has_narrator_and_child_voices():
    voices = load_voice_catalog()
    assert any(v["voice_type"] == "narrator" for v in voices)
    children = [v for v in voices if v["voice_type"] == "child"]
    assert len(children) >= 5


def test_catalog_is_2_0_only_and_has_bilingual():
    voices = load_voice_catalog()
    resources = {v["resource_id"] for v in voices}
    assert resources == VALID_RESOURCES
    assert any(v["bilingual"] for v in voices)
