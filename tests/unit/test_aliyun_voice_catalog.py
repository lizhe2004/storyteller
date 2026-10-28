import pytest

from storyteller.providers.aliyun.tts import load_voice_catalog

VALID_GENDERS = {"male", "female"}
VALID_AGES = {"child", "teen", "young_adult", "middle_aged", "senior"}
VALID_MODELS = {
    "qwen-audio-3.0-tts-plus",
    "qwen-audio-3.0-tts-flash",
    "qwen-audio-3.1-tts-flash",
}


@pytest.fixture(autouse=True)
def _clear_cache():
    load_voice_catalog.cache_clear()
    yield
    load_voice_catalog.cache_clear()


def test_catalog_loads_and_is_nonempty():
    assert len(load_voice_catalog()) == 1285


def test_catalog_records_have_required_fields():
    for v in load_voice_catalog():
        assert v["voice_id"]
        assert v["name"]
        assert v["model"] in VALID_MODELS or v["model"] == "sambert"
        assert v["gender"] in VALID_GENDERS or (
            v["model"] == "sambert" and v["gender"] is None
        )
        ages = v["age"] if isinstance(v["age"], list) else [v["age"]]
        assert all(age in VALID_AGES for age in ages)
        assert ages or v["model"] == "sambert"
        assert v["language"]
        assert isinstance(v["bilingual"], bool)
        assert v["category"]
        assert v["description"]
        assert isinstance(v["tags"], list)


def test_catalog_voice_ids_unique():
    voices = load_voice_catalog()
    ids = [v["voice_id"] for v in voices]
    assert len(ids) == len(set(ids))


def test_catalog_excludes_english_only_voices():
    # English-only voices are omitted in v1: the matcher does not filter
    # candidates by language yet, so they must not enter the Chinese pool.
    ids = {v["voice_id"] for v in load_voice_catalog()}
    assert "loongmary" not in ids
    assert "loongeva_v3.6" not in ids
    assert "loongjohn" not in ids


def test_catalog_has_child_voices_and_all_product_models():
    voices = load_voice_catalog()
    children = [
        v for v in voices
        if "child" in (v["age"] if isinstance(v["age"], list) else [v["age"]])
    ]
    assert len(children) > 100
    assert {v["voice_id"] for v in children} >= {
        "longjielidou_v3.6",
        "longpaopao_v3.6",
        "longhuohuo_v3.6",
        "qwen-audio-3.0-tts-flash-longjufuhe",
        "qwen-audio-3.0-tts-plus-longlanxuejun",
    }
    models = {v["model"] for v in voices}
    assert VALID_MODELS <= models
    assert "sambert" in models
    assert not any(model.startswith("sambert-") for model in models)
    sambert_voices = [v for v in voices if v["model"] == "sambert"]
    assert len(sambert_voices) == 43
    assert {v["voice_id"] for v in sambert_voices} >= {
        "sambert-beth-v1", "sambert-betty-v1", "sambert-zhiyue-v1",
    }


def test_catalog_preserves_scalar_and_array_age_values():
    index = {voice["voice_id"]: voice for voice in load_voice_catalog()}
    assert index["longpaopao_v3.6"]["age"] == ["child", "teen"]
    assert index["longanhuan_v3.6"]["age"] == "young_adult"


def test_known_voices_bound_to_correct_model():
    # A voice requested against the wrong model returns InvalidParameter.
    index = {v["voice_id"]: v["model"] for v in load_voice_catalog()}
    assert index["longanlingxin"] == "qwen-audio-3.0-tts-plus"
    assert index["longanlufeng"] == "qwen-audio-3.0-tts-plus"
    assert index["longanhuan_v3.6"] == "qwen-audio-3.0-tts-flash"
    assert index["longchuanshu_v3.6"] == "qwen-audio-3.0-tts-flash"
    assert index["sambert-zhide-v1"] == "sambert"
    assert index["sambert-zhiyue-v1"] == "sambert"


def test_sambert_catalog_keeps_vendor_model_id_separate_from_product_model():
    index = {v["voice_id"]: v for v in load_voice_catalog()}
    assert index["sambert-zhiye-v1"]["model"] == "sambert"
    assert index["sambert-zhiye-v1"]["provider_model"] == "sambert-zhiye-v1"


def test_markdown_catalog_voices_are_available_with_normalized_metadata():
    index = {v["voice_id"]: v for v in load_voice_catalog()}

    flash = index["qwen-audio-3.0-tts-flash-longcanzhuyue"]
    assert flash == {
        "voice_id": "qwen-audio-3.0-tts-flash-longcanzhuyue",
        "name": "龙璨竹月",
        "model": "qwen-audio-3.0-tts-flash",
        "gender": "female",
        "age": "young_adult",
        "category": "日常对话",
        "description": "26岁，平实质朴音",
        "tags": [],
        "language": "zh-CN",
        "bilingual": False,
    }

    plus = index["qwen-audio-3.0-tts-plus-longlingzhixing"]
    assert plus["model"] == "qwen-audio-3.0-tts-plus"
    assert plus["gender"] == "male"
    assert plus["age"] == "senior"
    assert plus["category"] == "有声阅读"


def test_markdown_english_voices_are_excluded():
    ids = {v["voice_id"] for v in load_voice_catalog()}
    assert "qwen-audio-3.0-tts-flash-loongolivialin" not in ids
    assert "qwen-audio-3.0-tts-plus-loongolivialin" not in ids
    assert "Emily_v3.1" not in ids
    assert "Andy_v3.1" not in ids


def test_31_voices_cover_all_sections_with_normalized_metadata():
    index = {v["voice_id"]: v for v in load_voice_catalog()}

    # Multilingual voices keep their persona metadata and note the dialects.
    multi = index["longanlingxin_v3.1"]
    assert multi["model"] == "qwen-audio-3.1-tts-flash"
    assert multi["category"] == "社交陪伴"
    assert "多语种" in multi["description"]
    assert "方言" in multi["tags"]

    # Premium Chinese narration voice.
    narration = index["xieshurou_v3.1"]
    assert narration["category"] == "有声阅读"
    assert narration["tags"] == ["精品音色"]

    # Child persona from the "other" table inherits the v3.6 twin's age.
    child = index["longjielidou_v3.1"]
    assert child["age"] == "child"
    assert child["category"] == "儿童陪伴"
