import json

import pytest

from storyteller.core.story_generator import StoryGenerator
from storyteller.core.config import Config
from storyteller.core.exceptions import LLMError
from storyteller.providers.mock.llm import MockLLMProvider, DEFAULT_SCRIPT


def _make_generator(response=None):
    config = Config()
    llm = MockLLMProvider(config)
    if response is not None:
        llm.set_response(response)
    return StoryGenerator(llm), llm


def test_generate_script_parses_mock_response():
    generator, _ = _make_generator()
    script = generator.generate_script(topic="测试故事")
    assert script.title == "小猫的冒险"
    assert len(script.characters) == 2
    assert len(script.lines) == 4


def test_generate_script_sets_topic():
    generator, _ = _make_generator()
    script = generator.generate_script(topic="太空冒险")
    assert script.topic == "太空冒险"


def test_generate_script_prompt_contains_length_and_complexity():
    generator, llm = _make_generator()
    generator.generate_script(
        topic="测试", length="long", complexity="rich"
    )
    # Last call was the script generation
    messages = llm.calls[-1]["messages"]
    user_content = messages[1]["content"]
    assert "long" in user_content
    assert "rich" in user_content


def test_generate_script_prompt_has_system_and_user():
    generator, llm = _make_generator()
    generator.generate_script(topic="测试")
    messages = llm.calls[-1]["messages"]
    roles = [m["role"] for m in messages]
    assert roles == ["system", "user"]


def test_generate_script_invalid_json_raises():
    generator, _ = _make_generator("this is not json")
    with pytest.raises(LLMError):
        generator.generate_script(topic="测试")


def test_generate_script_handles_code_fence_json():
    wrapped = "```json\n" + json.dumps(DEFAULT_SCRIPT, ensure_ascii=False) + "\n```"
    generator, _ = _make_generator(wrapped)
    script = generator.generate_script(topic="测试")
    assert script.title == "小猫的冒险"


def test_generate_script_dialogue_lines_have_character_ids():
    generator, _ = _make_generator()
    script = generator.generate_script(topic="测试")
    dialogue_lines = [
        line for line in script.lines if line.line_type == "dialogue"
    ]
    assert dialogue_lines
    for line in dialogue_lines:
        assert line.character_id


def test_generate_script_uses_custom_system_prompt():
    config = Config()
    llm = MockLLMProvider(config)
    custom_prompt = "你是故事生成专家，始终用简体中文回复。"
    generator = StoryGenerator(llm, system_prompt=custom_prompt)
    generator.generate_script(topic="测试")
    messages = llm.calls[-1]["messages"]
    assert messages[0]["content"] == custom_prompt
