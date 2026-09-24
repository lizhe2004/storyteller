from datetime import datetime, timedelta

from storyteller.core.models import Character, Script, ScriptLine, VoiceConfig
from storyteller.core.project import ProjectManager
from storyteller.core.voice_overrides import voice_key
from storyteller.web.voice_catalog import VoiceClipCatalog


class FakeRegistry:
    def __init__(self, voices):
        self.voices = voices
        self.voice_overrides = type("Overrides", (), {"is_enabled": lambda _self, _key: True})()

    def list_tts_voices(self, include_disabled=False):
        return list(self.voices)


def voice(provider, model, voice_id, name, gender, age, category="有声阅读", tags=None):
    return VoiceConfig(
        provider=provider,
        model=model,
        voice_id=voice_id,
        name=name,
        gender=gender,
        age=age,
        category=category,
        description=name + " description",
        tags=tags or [],
    )


def save_story(manager, project_id, title, created_at, lines):
    state = manager.create_project(topic=title)
    state.project_id = project_id
    state.created_at = created_at
    state.script = Script(
        script_id="script-" + project_id,
        title=title,
        topic=title,
        characters=[Character(id="hero", name="主角", description="角色")],
        lines=lines,
    )
    manager.save_project(state)
    project_dir = manager.resolve_project_dir(project_id)
    return project_dir


def test_catalog_lists_all_voices_and_story_clips(tmp_path):
    manager = ProjectManager(tmp_path / "stories")
    older = datetime(2026, 1, 1, 10, 0, 0)
    newer = older + timedelta(days=1)
    catalog_voice = voice("volcengine", "resource-a", "v1", "温柔女声", "female", ["child", "young_adult"], tags=["温暖", "治愈"])
    other_voice = voice("aliyun", "cosyvoice-v2", "v2", "沉稳男声", "male", ["middle_aged"])

    first = save_story(
        manager,
        "project-old",
        "旧故事",
        older,
        [ScriptLine(
            line_id="line-1",
            line_type="dialogue",
            character_id="hero",
            text="旧台词",
            voice_config=VoiceConfig(provider="volcengine", model=None, voice_id="v1"),
        )],
    )
    (first / "audio").mkdir()
    (first / "audio" / "line-1.mp3").write_bytes(b"mp3")

    second = save_story(
        manager,
        "project-new",
        "新故事",
        newer,
        [ScriptLine(
            line_id="line-2",
            line_type="dialogue",
            character_id="hero",
            text="新台词",
            voice_config=VoiceConfig(provider="volcengine", model="resource-a", voice_id="v1"),
        ), ScriptLine(
            line_id="line-missing",
            line_type="dialogue",
            character_id="hero",
            text="没有音频",
            voice_config=VoiceConfig(provider="aliyun", model="cosyvoice-v2", voice_id="v2"),
        )],
    )
    (second / "audio").mkdir()
    (second / "audio" / "line-2.mp3").write_bytes(b"mp3")

    # A malformed project must not hide valid projects.
    broken = manager.project_root / "broken"
    broken.mkdir()
    (broken / "project.json").write_text("{not json", encoding="utf-8")

    service = VoiceClipCatalog(FakeRegistry([catalog_voice, other_voice]), manager)
    records = service.list_voices()
    by_key = {record["key"]: record for record in records}

    assert set(by_key) == {voice_key(catalog_voice), voice_key(other_voice)}
    assert by_key[voice_key(catalog_voice)]["clip_count"] == 2
    assert by_key[voice_key(other_voice)]["clip_count"] == 0
    assert by_key[voice_key(other_voice)]["has_clips"] is False
    assert by_key[voice_key(catalog_voice)]["tags"] == ["温暖", "治愈"]

    clips = service.clips_for_voice(voice_key(catalog_voice))
    assert [clip["text"] for clip in clips] == ["新台词", "旧台词"]
    assert clips[0]["story_title"] == "新故事"
    assert clips[0]["character_name"] == "主角"
    assert clips[0]["audio_url_id"]


def test_catalog_filters_provider_model_gender_and_age(tmp_path):
    manager = ProjectManager(tmp_path / "stories")
    voices = [
        voice("volcengine", "resource-a", "v1", "女声", "female", ["child", "young_adult"]),
        voice("volcengine", "resource-b", "v2", "男声", "male", ["middle_aged"]),
        voice("aliyun", "cosyvoice-v2", "v3", "另一女声", "female", ["senior"]),
    ]
    service = VoiceClipCatalog(FakeRegistry(voices), manager)

    assert len(service.filter_voices(provider="volcengine")["voices"]) == 2
    assert len(service.filter_voices(model="resource-b")["voices"]) == 1
    assert len(service.filter_voices(gender="female")["voices"]) == 2
    result = service.filter_voices(age="child")
    assert [item["voice_id"] for item in result["voices"]] == ["v1"]


def test_catalog_uses_character_voice_config_when_line_voice_is_empty(tmp_path):
    manager = ProjectManager(tmp_path / "stories")
    narrator_voice = voice("volcengine", "resource-a", "narrator", "旁白", "female", ["young_adult"])
    hero_voice = voice("aliyun", "cosyvoice-v2", "hero", "主角", "male", ["child"])
    state = manager.create_project(topic="角色音频")
    state.script = Script(
        script_id="script-roles",
        title="角色音频",
        topic="测试",
        characters=[
            Character(id="narrator", name="旁白", description="旁白", voice_config=narrator_voice),
            Character(id="hero", name="主角", description="角色", voice_config=hero_voice),
        ],
        lines=[
            ScriptLine(line_id="1", line_type="narration", text="旁白台词", voice_config=None),
            ScriptLine(line_id="2", line_type="dialogue", character_id="hero", text="角色台词", voice_config=None),
        ],
    )
    manager.save_project(state)
    project_dir = manager.resolve_project_dir(state.project_id)
    (project_dir / "audio").mkdir()
    (project_dir / "audio" / "1.mp3").write_bytes(b"mp3")
    (project_dir / "audio" / "2.mp3").write_bytes(b"mp3")

    service = VoiceClipCatalog(FakeRegistry([narrator_voice, hero_voice]), manager)

    assert service.list_voices()[0]["clip_count"] + service.list_voices()[1]["clip_count"] == 2
    assert len(service.clips_for_voice(voice_key(narrator_voice))) == 1
    assert len(service.clips_for_voice(voice_key(hero_voice))) == 1


def test_catalog_returns_complete_filter_options_independent_of_page(tmp_path):
    manager = ProjectManager(tmp_path / "stories")
    voices = [
        voice("volcengine", "resource-a", "v1", "火山女声", "female", ["child"]),
        voice("aliyun", "cosyvoice-v2", "v2", "阿里男声", "male", ["senior"]),
    ]
    service = VoiceClipCatalog(FakeRegistry(voices), manager)

    result = service.filter_voices(page=1, page_size=1)

    assert result["total"] == 2
    assert result["filters"] == {
        "providers": ["aliyun", "volcengine"],
        "models": ["cosyvoice-v2", "resource-a"],
        "genders": ["female", "male"],
        "ages": ["child", "senior"],
    }


def test_catalog_rejects_unknown_or_unsafe_clip_resolution(tmp_path):
    manager = ProjectManager(tmp_path / "stories")
    catalog_voice = voice("volcengine", "resource-a", "v1", "女声", "female", ["child"])
    service = VoiceClipCatalog(FakeRegistry([catalog_voice]), manager)

    assert service.resolve_clip_audio(voice_key(catalog_voice), "missing") is None
    assert service.resolve_clip_audio(
        voice_key(catalog_voice), "../project/audio/file.mp3"
    ) is None
