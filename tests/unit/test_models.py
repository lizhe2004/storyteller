from datetime import datetime

from storyteller.core.models import (
    SoundEffect,
    VoiceConfig,
    Character,
    ScriptLine,
    Script,
    ProjectState,
    LineType,
    SoundType,
    ProjectStatus,
)


# ========== VoiceConfig ==========
def test_voice_config_creation():
    vc = VoiceConfig(
        provider="volcengine",
        voice_id="test_voice",
        voice_type="narrator",
        language="zh-CN",
    )
    assert vc.provider == "volcengine"
    assert vc.voice_id == "test_voice"
    assert vc.voice_type == "narrator"
    assert vc.speed == 1.0
    assert vc.pitch == 1.0
    assert vc.volume == 1.0
    assert vc.style is None


# ========== Character ==========
def test_character_creation():
    char = Character(id="narrator", name="旁白", description="故事旁白")
    assert char.id == "narrator"
    assert char.name == "旁白"
    assert char.voice_config is None


def test_character_with_voice():
    vc = VoiceConfig(
        provider="volcengine",
        voice_id="v1",
        voice_type="male",
    )
    char = Character(id="hero", name="英雄", description="主角", voice_config=vc)
    assert char.voice_config.voice_id == "v1"


# ========== ScriptLine ==========
def test_script_line_narration():
    line = ScriptLine(line_id="1", line_type="narration", text="从前有座山...")
    assert line.line_type == "narration"
    assert line.character_id is None
    assert line.sound_effects == []
    assert line.background_music is None


def test_script_line_dialogue():
    line = ScriptLine(
        line_id="2",
        line_type="dialogue",
        character_id="cat",
        text="喵~",
    )
    assert line.character_id == "cat"


def test_script_line_default_independent_lists():
    line1 = ScriptLine(line_id="1", line_type="narration")
    line2 = ScriptLine(line_id="2", line_type="narration")
    line1.sound_effects.append("x")
    assert line2.sound_effects == []


# ========== Script ==========
def test_script_creation():
    script = Script(script_id="test-001", title="测试故事", topic="测试")
    assert script.script_id == "test-001"
    assert script.title == "测试故事"
    assert len(script.characters) == 0
    assert len(script.lines) == 0
    assert isinstance(script.created_at, datetime)
    assert isinstance(script.updated_at, datetime)


def test_script_with_content():
    char = Character(id="narrator", name="旁白", description="旁白")
    line = ScriptLine(line_id="1", line_type="narration", text="开始")
    script = Script(
        script_id="s1",
        title="故事",
        topic="主题",
        characters=[char],
        lines=[line],
    )
    assert len(script.characters) == 1
    assert len(script.lines) == 1


# ========== SoundEffect ==========
def test_sound_effect_creation():
    sfx = SoundEffect(
        effect_id="sfx1",
        name="雨声",
        type="ambient",
        source_path="/sounds/rain.mp3",
    )
    assert sfx.type == "ambient"
    assert sfx.volume == 1.0
    assert sfx.fade_in == 0.0


# ========== ProjectState ==========
def test_project_state_defaults():
    state = ProjectState(project_id="p1")
    assert state.state == "initialized"
    assert state.script is None
    assert state.config == {}
    assert isinstance(state.created_at, datetime)


def test_project_state_with_status():
    state = ProjectState(project_id="p1", state="script_generated")
    assert state.state == "script_generated"


# ========== Enums ==========
def test_enums_have_expected_values():
    assert LineType.DIALOGUE.value == "dialogue"
    assert LineType.NARRATION.value == "narration"
    assert SoundType.MUSIC.value == "music"
    assert ProjectStatus.COMPLETED.value == "completed"
    assert ProjectStatus.FAILED.value == "failed"


def test_enums_are_strings():
    # Enums should compare equal to their string values
    assert LineType.DIALOGUE == "dialogue"
    assert ProjectStatus.COMPLETED == "completed"
