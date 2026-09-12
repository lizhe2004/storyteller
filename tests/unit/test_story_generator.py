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


def test_generate_script_parses_direction_into_metadata():
    payload = {
        "title": "测试",
        "characters": [
            {"id": "c1", "name": "小兔", "description": "女孩"}
        ],
        "lines": [
            {"line_id": "1", "line_type": "narration", "text": "天黑了。"},
            {
                "line_id": "2",
                "line_type": "dialogue",
                "character_id": "c1",
                "text": "我好害怕。",
                "direction": "声音发抖，带着哭腔",
            },
        ],
    }
    generator, _ = _make_generator(json.dumps(payload, ensure_ascii=False))
    script = generator.generate_script(topic="测试")
    assert script.lines[0].metadata == {}
    assert script.lines[1].metadata["direction"] == "声音发抖，带着哭腔"


def test_generate_script_injects_narrator_when_missing():
    payload = {
        "title": "测试",
        "characters": [
            {"id": "c1", "name": "小兔", "description": "女孩"}
        ],
        "lines": [
            {"line_id": "1", "line_type": "narration", "text": "天黑了。"},
            {
                "line_id": "2", "line_type": "dialogue",
                "character_id": "c1", "text": "我好害怕。",
            },
        ],
    }
    generator, _ = _make_generator(json.dumps(payload, ensure_ascii=False))
    script = generator.generate_script(topic="测试")
    narrator = [c for c in script.characters if c.id == "narrator"]
    assert len(narrator) == 1
    assert narrator[0].name == "旁白"
    assert script.characters[0].id == "narrator"


def test_generate_script_keeps_existing_narrator():
    payload = {
        "title": "测试",
        "characters": [
            {"id": "narrator", "name": "旁白", "description": "旁白"},
            {"id": "c1", "name": "小兔", "description": "女孩"},
        ],
        "lines": [
            {"line_id": "1", "line_type": "narration", "text": "开场。"},
        ],
    }
    generator, _ = _make_generator(json.dumps(payload, ensure_ascii=False))
    script = generator.generate_script(topic="测试")
    assert [c.id for c in script.characters] == ["narrator", "c1"]


def test_generate_script_no_narration_needs_no_narrator():
    payload = {
        "title": "测试",
        "characters": [
            {"id": "c1", "name": "小兔", "description": "女孩"}
        ],
        "lines": [
            {
                "line_id": "1", "line_type": "dialogue",
                "character_id": "c1", "text": "你好。",
            },
        ],
    }
    generator, _ = _make_generator(json.dumps(payload, ensure_ascii=False))
    script = generator.generate_script(topic="测试")
    assert [c.id for c in script.characters] == ["c1"]


def test_generate_script_uses_custom_system_prompt():
    config = Config()
    llm = MockLLMProvider(config)
    custom_prompt = "你是故事生成专家，始终用简体中文回复。"
    generator = StoryGenerator(llm, system_prompt=custom_prompt)
    generator.generate_script(topic="测试")
    messages = llm.calls[-1]["messages"]
    assert messages[0]["content"] == custom_prompt


# ---------- sound effects / background music ----------
def test_generate_script_parses_top_level_bgm():
    payload = {
        "title": "测试",
        "characters": [
            {"id": "narrator", "name": "旁白", "description": "旁白"}
        ],
        "lines": [
            {"line_id": "1", "line_type": "narration", "text": "开场。"},
        ],
        "background_music": {
            "name": "冒险主题曲",
            "type": "music",
            "description": "轻快温馨的管弦乐",
            "prompt": "轻快温暖的管弦乐，无人声",
        },
    }
    generator, _ = _make_generator(json.dumps(payload, ensure_ascii=False))
    script = generator.generate_script(topic="测试")
    bgm = script.background_music
    assert bgm is not None
    assert bgm.type == "music"
    assert bgm.name == "冒险主题曲"
    assert bgm.prompt == "轻快温暖的管弦乐，无人声"
    assert bgm.description == "轻快温馨的管弦乐"
    assert bgm.source_path is None
    assert bgm.source_type == "builtin"


def test_generate_script_parses_inline_sound_effects():
    payload = {
        "title": "测试",
        "characters": [
            {"id": "narrator", "name": "旁白", "description": "旁白"}
        ],
        "lines": [
            {
                "line_id": "1",
                "line_type": "narration",
                "text": "下雨了。",
                "sound_effects": [
                    {
                        "name": "雨声",
                        "type": "ambient",
                        "description": "窗外雨声",
                        "prompt": "舒缓的下雨声，无人声",
                        "tags": ["天气"],
                    },
                    {
                        "name": "雷",
                        "type": "effect",
                        "prompt": "一声闷雷",
                        "anchor": "下雨了",
                    },
                ],
            },
        ],
    }
    generator, _ = _make_generator(json.dumps(payload, ensure_ascii=False))
    script = generator.generate_script(topic="测试")
    effects = script.lines[0].sound_effects
    assert [e.type for e in effects] == ["ambient", "effect"]
    assert effects[0].name == "雨声"
    assert effects[0].prompt == "舒缓的下雨声，无人声"
    assert effects[0].tags == ["天气"]
    assert effects[0].source_path is None
    assert effects[0].anchor is None  # ambient beds carry no anchor
    assert effects[1].name == "雷"
    assert effects[1].anchor == "下雨了"


def test_effect_anchor_not_in_text_is_dropped():
    payload = {
        "title": "测试",
        "characters": [
            {"id": "narrator", "name": "旁白", "description": "旁白"}
        ],
        "lines": [
            {
                "line_id": "1",
                "line_type": "narration",
                "text": "天黑了下来。",
                "sound_effects": [
                    {
                        "name": "雷",
                        "type": "effect",
                        "prompt": "一声闷雷，无人声",
                        # Paraphrase, not a verbatim substring of the text:
                        # the cue describes a sound the line never mentions,
                        # so it must be dropped entirely rather than played
                        # unannounced at the line head.
                        "anchor": "天空中打雷",
                    },
                ],
            },
        ],
    }
    generator, _ = _make_generator(json.dumps(payload, ensure_ascii=False))
    script = generator.generate_script(topic="测试")
    assert script.lines[0].sound_effects == []


def test_effect_without_anchor_is_dropped():
    payload = {
        "title": "测试",
        "characters": [
            {"id": "narrator", "name": "旁白", "description": "旁白"}
        ],
        "lines": [
            {
                "line_id": "1",
                "line_type": "narration",
                "text": "屋里安静极了。",
                "sound_effects": [
                    {
                        "name": "脚步",
                        "type": "effect",
                        "prompt": "一阵脚步声，无人声",
                    },
                ],
            },
        ],
    }
    generator, _ = _make_generator(json.dumps(payload, ensure_ascii=False))
    script = generator.generate_script(topic="测试")
    assert script.lines[0].sound_effects == []


def test_ambient_without_anchor_is_kept():
    payload = {
        "title": "测试",
        "characters": [
            {"id": "narrator", "name": "旁白", "description": "旁白"}
        ],
        "lines": [
            {
                "line_id": "1",
                "line_type": "narration",
                "text": "夜深了。",
                "sound_effects": [
                    {
                        "name": "夜风",
                        "type": "ambient",
                        "prompt": "持续的夜晚风声，无人声",
                    },
                ],
            },
        ],
    }
    generator, _ = _make_generator(json.dumps(payload, ensure_ascii=False))
    script = generator.generate_script(topic="测试")
    effects = script.lines[0].sound_effects
    assert len(effects) == 1
    assert effects[0].type == "ambient"
    assert effects[0].anchor is None


def test_sound_prompt_requires_sound_evidence_in_line_text():
    from storyteller.core.story_generator import _SOUND_PROMPT

    # The prompt must forbid sounds the line never mentions (off-screen
    # actions on dialogue lines) and require the sound to be written into
    # the narration/dialogue text first.
    assert "画外" in _SOUND_PROMPT
    assert "先在旁白" in _SOUND_PROMPT


def test_sound_cue_without_prompt_is_dropped():
    payload = {
        "title": "测试",
        "characters": [
            {"id": "narrator", "name": "旁白", "description": "旁白"}
        ],
        "lines": [
            {
                "line_id": "1",
                "line_type": "narration",
                "text": "安静。",
                "sound_effects": [{"name": "空", "type": "effect"}],
            },
        ],
        "background_music": {"name": "无prompt", "type": "music"},
    }
    generator, _ = _make_generator(json.dumps(payload, ensure_ascii=False))
    script = generator.generate_script(topic="测试")
    assert script.lines[0].sound_effects == []
    assert script.background_music is None


def test_standalone_sound_line_is_merged_into_next_spoken_line():
    # The model emitted a separate sound-only pseudo-line (empty text,
    # line_type sound_effects). It must not become a ScriptLine; its cue is
    # attached to the following spoken line at the same timeline position.
    payload = {
        "title": "雷雨",
        "characters": [
            {"id": "narrator", "name": "旁白", "description": "旁白"}
        ],
        "lines": [
            {
                "line_id": "9",
                "line_type": "dialogue",
                "character_id": "squirrel",
                "text": "我跑来找你啦！",
            },
            {
                "line_id": "10",
                "line_type": "sound_effects",
                "text": "",
                "sound_effects": [
                    {"name": "打雷", "type": "effect",
                     "prompt": "低沉轰鸣的雷声，有回响",
                     "anchor": "雷声炸响"},
                ],
            },
            {
                "line_id": "11",
                "line_type": "narration",
                "text": "一个巨大的雷声炸响。",
            },
        ],
    }
    generator, _ = _make_generator(json.dumps(payload, ensure_ascii=False))
    script = generator.generate_script(topic="雷雨")

    assert [l.line_id for l in script.lines] == ["9", "11"]
    assert all(l.line_type in ("dialogue", "narration") for l in script.lines)
    merged = script.lines[1]
    assert merged.line_id == "11"
    assert len(merged.sound_effects) == 1
    assert merged.sound_effects[0].name == "打雷"


def test_trailing_standalone_sound_attaches_to_last_line():
    payload = {
        "title": "雨停",
        "characters": [
            {"id": "narrator", "name": "旁白", "description": "旁白"}
        ],
        "lines": [
            {"line_id": "1", "line_type": "narration", "text": "雨停了。"},
            {
                "line_id": "2",
                "line_type": "sound_effects",
                "sound_effects": [
                    {"name": "滴水", "type": "ambient",
                     "prompt": "屋檐轻微滴水声，无人声"},
                ],
            },
        ],
    }
    generator, _ = _make_generator(json.dumps(payload, ensure_ascii=False))
    script = generator.generate_script(topic="雨停")
    assert len(script.lines) == 1
    assert script.lines[0].sound_effects[0].name == "滴水"


def test_with_sound_appends_sound_prompt():
    generator, llm = _make_generator()
    generator.generate_script(topic="测试", with_sound=True)
    system = llm.calls[-1]["messages"][0]["content"]
    assert "background_music" in system
    assert "sound_effects" in system

    generator, llm2 = _make_generator()
    generator.generate_script(topic="测试", with_sound=False)
    assert "sound_effects" not in llm2.calls[-1]["messages"][0]["content"]
