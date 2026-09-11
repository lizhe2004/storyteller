import json

import pytest

from storyteller.core.config import Config
from storyteller.core.models import Character, Script
from storyteller.core.voice_matcher import VoiceMatcher, _infer_age
from storyteller.core.exceptions import ProviderError
from storyteller.providers.registry import ProviderRegistry
from storyteller.providers.mock.tts import MockTTSProvider
from storyteller.providers.mock.llm import MockLLMProvider


def _make_script_with_characters(*characters):
    return Script(script_id="s1", title="测试", topic="测试", characters=list(characters))


def _make_matcher(llm=None, mode="rule"):
    config = Config()
    registry = ProviderRegistry(config)
    registry.register_tts("mock", MockTTSProvider)
    return VoiceMatcher(registry, llm=llm, mode=mode)


def _make_llm(response):
    llm = MockLLMProvider(Config())
    llm.set_response(json.dumps(response, ensure_ascii=False))
    return llm


def test_match_voices_assigns_narrator_voice():
    matcher = _make_matcher()
    narrator = Character(id="narrator", name="旁白", description="故事旁白")
    script = _make_script_with_characters(narrator)
    matcher.match_voices(script)
    assert narrator.voice_config is not None
    assert narrator.voice_config.voice_type == "narrator"
    assert narrator.voice_config.provider == "mock"


def test_match_voices_male_by_description():
    matcher = _make_matcher()
    hero = Character(id="hero", name="大壮", description="一个成年男子，勇敢")
    script = _make_script_with_characters(hero)
    matcher.match_voices(script)
    assert hero.voice_config.voice_type == "male"


def test_match_voices_female_by_description():
    matcher = _make_matcher()
    girl = Character(id="girl", name="小红", description="温柔的女孩")
    script = _make_script_with_characters(girl)
    matcher.match_voices(script)
    assert girl.voice_config.voice_type == "female"


def test_match_voices_gender_from_kinship_title():
    matcher = _make_matcher()
    mom = Character(id="mom", name="企鹅妈妈", description="成年企鹅，温柔耐心，声音温暖")
    dad = Character(id="dad", name="熊爸爸", description="成年熊，沉稳可靠")
    script = _make_script_with_characters(mom, dad)
    matcher.match_voices(script)
    assert mom.voice_config.voice_type == "female"
    assert dad.voice_config.voice_type == "male"


def test_match_voices_child_by_description():
    matcher = _make_matcher()
    kid = Character(id="kid", name="小明", description="一个五六岁的小男孩")
    script = _make_script_with_characters(kid)
    matcher.match_voices(script)
    assert kid.voice_config.voice_type == "child"


def test_adult_described_with_child_word_is_not_child():
    matcher = _make_matcher()
    # "哄孩子" describes an adult action; the role is a senior female.
    granny = Character(id="granny", name="月亮婆婆",
                       description="慈祥温柔的老年女性，声音轻缓，像在哄孩子")
    kid = Character(id="kid", name="小星星",
                    description="活泼好奇的幼年男孩，声音清脆")
    script = _make_script_with_characters(granny, kid)
    matcher.match_voices(script)
    assert granny.voice_config.voice_type == "female"
    assert kid.voice_config.voice_type == "child"


def test_match_voices_child_by_numeric_age():
    matcher = _make_matcher()
    kid = Character(id="kid", name="小熊", description="5岁，男孩，憨厚")
    teen = Character(id="teen", name="阿杰", description="15岁，男孩")
    script = _make_script_with_characters(kid, teen)
    matcher.match_voices(script)
    assert kid.voice_config.voice_type == "child"
    # 13+ is a teenager, not the single child voice.
    assert teen.voice_config.voice_type == "male"


def test_match_voices_does_not_reuse_same_voice():
    matcher = _make_matcher()
    a = Character(id="a", name="甲", description="男孩")
    b = Character(id="b", name="乙", description="另一个男孩")
    script = _make_script_with_characters(a, b)
    matcher.match_voices(script)
    assert a.voice_config.voice_id != b.voice_config.voice_id


def test_match_voices_uses_narrator_only_as_last_resort():
    # With one female voice available, three female characters fall through
    # child -> male; narrator must be the very last fallback, never first.
    matcher = _make_matcher()
    girls = [
        Character(id="g{}".format(i), name="女{}".format(i), description="女孩")
        for i in range(3)
    ]
    script = _make_script_with_characters(*girls)
    matcher.match_voices(script)
    assigned = {g.voice_config.voice_type for g in girls}
    assert "narrator" not in assigned
    assert "female" in assigned


def test_match_voices_respects_allowed_voice_ids():
    matcher = _make_matcher()
    narrator = Character(id="narrator", name="旁白", description="旁白")
    script = _make_script_with_characters(narrator)
    matcher.match_voices(
        script, allowed_voice_ids={"male_01"}
    )
    assert narrator.voice_config.voice_id == "male_01"


def test_match_voices_respects_allowed_providers():
    matcher = _make_matcher()
    narrator = Character(id="narrator", name="旁白", description="旁白")
    script = _make_script_with_characters(narrator)
    # Only ask for a provider that isn't registered -> no voices available.
    with pytest.raises(ProviderError):
        matcher.match_voices(script, allowed_providers=["unknown"])


def test_match_voices_writes_config_on_script_characters():
    matcher = _make_matcher()
    narrator = Character(id="narrator", name="旁白", description="旁白")
    script = _make_script_with_characters(narrator)
    matcher.match_voices(script)
    assert script.characters[0].voice_config is not None


def test_match_voices_overwrites_existing_config():
    matcher = _make_matcher()
    hero = Character(id="hero", name="大壮", description="成年男子")
    hero.voice_config = None
    script = _make_script_with_characters(hero)
    matcher.match_voices(script)
    assert hero.voice_config is not None


# ---------- age inference ----------
@pytest.mark.parametrize(
    "name,desc,expected",
    [
        ("月亮婆婆", "慈祥的月亮婆婆，温柔缓慢", "senior"),
        ("王奶奶", "满头白发的老奶奶", "senior"),
        ("温柔妈妈", "孩子的妈妈，温柔耐心", "middle_aged"),
        ("小女孩", "扎辫子的小女孩", "child"),
        ("阿杰", "15岁的少年", "teen"),
        ("大壮", "一个勇敢的年轻人", "young_adult"),
        ("小熊", "5岁，男孩", "child"),
    ],
)
def test_infer_age(name, desc, expected):
    assert _infer_age("{} {}".format(name, desc)) == expected


# ---------- LLM semantic matching ----------
def _two_call_llm(classify, assign):
    """Mock LLM returning classify JSON on call #1, assign JSON on #2."""
    llm = MockLLMProvider(Config())
    llm.set_responses([
        json.dumps(classify, ensure_ascii=False),
        json.dumps(assign, ensure_ascii=False),
    ])
    return llm


def test_llm_classify_then_pick_assigns_voices():
    narrator = Character(id="narrator", name="旁白", description="旁白")
    mom = Character(id="mom", name="月亮婆婆", description="慈祥温柔缓慢的老婆婆")
    classify = {"characters": [
        {"character_id": "mom", "gender": "female", "age": "senior"},
    ]}
    assign = {"assignments": [
        {"character_id": "narrator", "voice_index": 1},
        {"character_id": "mom", "voice_index": 2},
    ]}
    matcher = _make_matcher(
        llm=_two_call_llm(classify, assign), mode="llm"
    )
    script = _make_script_with_characters(narrator, mom)
    matcher.match_voices(script)
    assert narrator.voice_config.voice_id == "narrator_01"
    # Candidates are grouped [narrator, female]; mom's female pick is index 2.
    assert mom.voice_config.voice_id == "female_01"
    assert mom.voice_config.description


def test_llm_classifies_boy_as_child_and_picks_child_voice():
    # The key regression: "男孩" must be read by the LLM as a child, not an
    # adult male (the keyword rule alone mapped it to young_adult).
    boy = Character(id="b1", name="小一", description="数字积木，矮小害羞的男孩")
    classify = {"characters": [
        {"character_id": "b1", "gender": "male", "age": "child"},
    ]}
    assign = {"assignments": [
        {"character_id": "b1", "voice_index": 1},
    ]}
    matcher = _make_matcher(
        llm=_two_call_llm(classify, assign), mode="llm"
    )
    script = _make_script_with_characters(boy)
    matcher.match_voices(script)
    assert boy.voice_config.voice_type == "child"
    assert boy.voice_config.voice_id == "child_01"


def test_llm_pick_falls_back_on_out_of_range_index():
    mom = Character(id="mom", name="阿姨", description="温柔的中年女性")
    classify = {"characters": [
        {"character_id": "mom", "gender": "female", "age": "middle_aged"},
    ]}
    assign = {"assignments": [{"character_id": "mom", "voice_index": 99}]}
    matcher = _make_matcher(
        llm=_two_call_llm(classify, assign), mode="llm"
    )
    script = _make_script_with_characters(mom)
    matcher.match_voices(script)
    assert mom.voice_config is not None
    assert mom.voice_config.voice_type == "female"


def test_llm_classify_bad_json_falls_back_to_rules():
    mom = Character(id="mom", name="阿姨", description="温柔的中年女性")
    llm = MockLLMProvider(Config())
    llm.set_responses(["not json", "not json"])
    matcher = _make_matcher(llm=llm, mode="llm")
    script = _make_script_with_characters(mom)
    matcher.match_voices(script)
    assert mom.voice_config.voice_type == "female"


def test_llm_classify_error_falls_back_to_rules():
    mom = Character(id="mom", name="阿姨", description="温柔的中年女性")
    llm = MockLLMProvider(Config())
    llm.set_error(RuntimeError("boom"))
    matcher = _make_matcher(llm=llm, mode="llm")
    script = _make_script_with_characters(mom)
    matcher.match_voices(script)  # must not raise
    assert mom.voice_config.voice_type == "female"


def test_llm_invalid_gender_ignored_and_rule_used():
    mom = Character(id="mom", name="阿姨", description="温柔的中年女性")
    classify = {"characters": [
        {"character_id": "mom", "gender": "robot", "age": "senior"},
    ]}
    assign = {"assignments": []}
    matcher = _make_matcher(
        llm=_two_call_llm(classify, assign), mode="llm"
    )
    script = _make_script_with_characters(mom)
    matcher.match_voices(script)
    # Invalid classification dropped -> rule path still gives a female voice.
    assert mom.voice_config.voice_type == "female"


def test_llm_duplicate_index_falls_back_to_distinct_voice():
    from storyteller.core.models import VoiceConfig

    class _MultiFemaleTTS:
        def __init__(self, config):
            pass

        def list_voices(self, **kwargs):
            return [
                VoiceConfig(provider="p", voice_id="f1", voice_type="female",
                            name="年轻御姐", age="young_adult",
                            description="干练利落的年轻女声"),
                VoiceConfig(provider="p", voice_id="f2", voice_type="female",
                            name="温柔妈妈", age="middle_aged",
                            description="舒缓温润的中年女声"),
            ]

    config = Config()
    registry = ProviderRegistry(config)
    registry.register_tts("multi", _MultiFemaleTTS)
    a = Character(id="a", name="甲", description="年轻女孩")
    b = Character(id="b", name="乙", description="慈祥老婆婆")
    classify = {"characters": [
        {"character_id": "a", "gender": "female", "age": "young_adult"},
        {"character_id": "b", "gender": "female", "age": "senior"},
    ]}
    # Pick call wrongly hands the same index to both.
    assign = {"assignments": [
        {"character_id": "a", "voice_index": 1},
        {"character_id": "b", "voice_index": 1},
    ]}
    llm = _two_call_llm(classify, assign)
    matcher = VoiceMatcher(registry, llm=llm, mode="llm")
    script = _make_script_with_characters(a, b)
    matcher.match_voices(script)
    # a keeps the LLM pick; b falls back to rule and gets the other voice.
    assert a.voice_config.voice_id == "f1"
    assert b.voice_config.voice_id == "f2"


def test_rule_mode_does_not_call_llm():
    mom = Character(id="mom", name="阿姨", description="温柔的中年女性")
    llm = MockLLMProvider(Config())
    matcher = _make_matcher(llm=llm, mode="rule")
    script = _make_script_with_characters(mom)
    matcher.match_voices(script)
    assert llm.calls == []
    assert mom.voice_config.voice_type == "female"
