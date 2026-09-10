import pytest

from storyteller.core.config import Config
from storyteller.core.models import Character, Script
from storyteller.core.voice_matcher import VoiceMatcher
from storyteller.core.exceptions import ProviderError
from storyteller.providers.registry import ProviderRegistry
from storyteller.providers.mock.tts import MockTTSProvider


def _make_script_with_characters(*characters):
    return Script(script_id="s1", title="测试", topic="测试", characters=list(characters))


def _make_matcher():
    config = Config()
    registry = ProviderRegistry(config)
    registry.register_tts("mock", MockTTSProvider)
    return VoiceMatcher(registry)


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


def test_match_voices_child_by_description():
    matcher = _make_matcher()
    kid = Character(id="kid", name="小明", description="一个五六岁的小男孩")
    script = _make_script_with_characters(kid)
    matcher.match_voices(script)
    assert kid.voice_config.voice_type == "child"


def test_match_voices_does_not_reuse_same_voice():
    matcher = _make_matcher()
    a = Character(id="a", name="甲", description="男孩")
    b = Character(id="b", name="乙", description="另一个男孩")
    script = _make_script_with_characters(a, b)
    matcher.match_voices(script)
    assert a.voice_config.voice_id != b.voice_config.voice_id


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
