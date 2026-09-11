from pathlib import Path

import pytest

from storyteller.core.config import Config
from storyteller.core.exceptions import TTSError
from storyteller.core.pipeline import Pipeline
from storyteller.providers.mock.llm import MockLLMProvider
from storyteller.providers.mock.tts import MockTTSProvider


def _make_pipeline(tmp_path):
    config = Config()
    config.set("data_dir", str(tmp_path / ".storyteller"))
    config.resolve_paths()
    config.set("llm.default_provider", "mock")
    config.set("tts.default_provider", "mock")

    pipeline = Pipeline(config)
    pipeline.registry.register_llm("mock", MockLLMProvider)
    pipeline.registry.register_tts("mock", MockTTSProvider)
    return pipeline


def test_run_generates_audio_file(tmp_path):
    pipeline = _make_pipeline(tmp_path)
    result_path = pipeline.run("太空冒险")
    assert Path(result_path).exists()
    assert Path(result_path).name == "story.mp3"
    assert Path(result_path).parent.parent.name == "stories"


def test_run_saves_project_state(tmp_path):
    pipeline = _make_pipeline(tmp_path)
    result_path = Path(pipeline.run("测试故事"))

    # State and audio share the per-project folder.
    project_dir = result_path.parent
    assert (project_dir / "project.json").exists()
    assert project_dir.parent == tmp_path / ".storyteller" / "stories"


def test_run_writes_script_and_audio(tmp_path):
    pipeline = _make_pipeline(tmp_path)
    result_path = Path(pipeline.run("小猫咪的故事"))

    project_dir = result_path.parent
    assert result_path.exists()
    assert (project_dir / "audio").is_dir()
    assert list((project_dir / "audio").glob("*.mp3"))


def test_run_exports_script_json(tmp_path):
    import json

    pipeline = _make_pipeline(tmp_path)
    result_path = Path(pipeline.run("小刺猬的故事"))

    script_file = result_path.parent / "story.script.json"
    assert script_file.exists()

    data = json.loads(script_file.read_text(encoding="utf-8"))
    assert data["topic"] == "小刺猬的故事"
    assert data["title"]
    assert len(data["lines"]) >= 1
    assert {"line_id", "line_type", "text"} <= set(data["lines"][0])


def test_run_exported_script_includes_matched_voices(tmp_path):
    import json

    pipeline = _make_pipeline(tmp_path)
    result_path = Path(pipeline.run("小狐狸的故事"))

    script_file = result_path.parent / "story.script.json"
    data = json.loads(script_file.read_text(encoding="utf-8"))
    # The standalone JSON is re-exported after voice matching, so every
    # character carries the TTS voice that will actually be used.
    voiced = [c for c in data["characters"] if c.get("voice_config")]
    assert voiced
    for char in voiced:
        vc = char["voice_config"]
        assert vc["provider"]
        assert vc["voice_id"]



def test_line_context_builds_directive_and_quoted_context():
    from storyteller.core.models import Script, ScriptLine, Character
    from storyteller.core.pipeline import Pipeline

    lines = [
        ScriptLine(line_id="1", line_type="narration", text="下雨了。"),
        ScriptLine(line_id="2", line_type="dialogue", character_id="a",
                   text="你带伞了吗？"),
        ScriptLine(
            line_id="3", line_type="dialogue", character_id="b",
            text="没有，一起躲雨吧。",
            metadata={"direction": "害羞又期待"},
        ),
    ]
    directives, context = Pipeline._line_context(lines, 2)
    assert directives == ["害羞又期待"]
    # Most recent narration and dialogue, in story order.
    assert context == ["下雨了。", "你带伞了吗？"]


def test_line_context_first_line_has_no_context():
    from storyteller.core.models import ScriptLine
    from storyteller.core.pipeline import Pipeline

    lines = [ScriptLine(line_id="1", line_type="narration", text="开场。")]
    directives, context = Pipeline._line_context(lines, 0)
    assert directives == [] and context == []


def test_run_passes_directive_and_context_to_tts(tmp_path):
    import json as _json
    from storyteller.core.config import Config
    from storyteller.core.pipeline import Pipeline
    from storyteller.providers.mock.llm import MockLLMProvider
    from storyteller.providers.mock.tts import MockTTSProvider

    script = {
        "title": "躲雨",
        "characters": [
            {"id": "narrator", "name": "旁白", "description": "故事旁白"},
            {"id": "a", "name": "小兔", "description": "女孩"},
        ],
        "lines": [
            {"line_id": "1", "line_type": "narration", "text": "突然下起大雨。"},
            {
                "line_id": "2", "line_type": "dialogue", "character_id": "a",
                "text": "我们一起躲雨吧。",
                "direction": "害羞又期待地轻声说",
            },
        ],
    }
    config = Config()
    config.set("data_dir", str(tmp_path / ".storyteller"))
    config.resolve_paths()
    config.set("llm.default_provider", "mock")
    config.set("tts.default_provider", "mock")
    pipeline = Pipeline(config)
    llm = MockLLMProvider(config)
    llm.set_response(_json.dumps(script, ensure_ascii=False))
    tts = MockTTSProvider(config)
    pipeline.registry.register_llm("mock", lambda c: llm)
    pipeline.registry.register_tts("mock", lambda c: tts)

    pipeline.run("躲雨")

    dialogue_call = next(
        c for c in tts.synth_calls if c["text"] == "我们一起躲雨吧。"
    )
    assert dialogue_call["kwargs"]["directives"] == ["害羞又期待地轻声说"]
    assert dialogue_call["kwargs"]["context"] == ["突然下起大雨。"]


def test_narration_uses_narrator_voice_when_llm_omits_it(tmp_path):
    import json as _json
    from storyteller.core.config import Config
    from storyteller.core.pipeline import Pipeline
    from storyteller.providers.mock.llm import MockLLMProvider
    from storyteller.providers.mock.tts import MockTTSProvider

    # The LLM emits narration lines but no narrator character.
    script = {
        "title": "无旁白角色",
        "characters": [
            {"id": "a", "name": "小兔", "description": "女孩"},
        ],
        "lines": [
            {"line_id": "1", "line_type": "narration", "text": "天亮了。"},
            {
                "line_id": "2", "line_type": "dialogue", "character_id": "a",
                "text": "早安！",
            },
        ],
    }
    config = Config()
    config.set("data_dir", str(tmp_path / ".storyteller"))
    config.resolve_paths()
    config.set("llm.default_provider", "mock")
    config.set("tts.default_provider", "mock")
    pipeline = Pipeline(config)
    llm = MockLLMProvider(config)
    llm.set_response(_json.dumps(script, ensure_ascii=False))
    tts = MockTTSProvider(config)
    pipeline.registry.register_llm("mock", lambda c: llm)
    pipeline.registry.register_tts("mock", lambda c: tts)

    pipeline.run("无旁白角色")

    from storyteller.core.voice_matcher import is_narration_voice

    narration_call = next(c for c in tts.synth_calls if c["text"] == "天亮了。")
    assert is_narration_voice(narration_call["voice_config"])
    dialogue_call = next(c for c in tts.synth_calls if c["text"] == "早安！")
    assert dialogue_call["voice_config"].voice_id != narration_call["voice_config"].voice_id


def test_draft_script_saves_json_without_audio(tmp_path):
    import json

    pipeline = _make_pipeline(tmp_path)
    script, script_path = pipeline.draft_script("只看剧本")

    assert Path(script_path).exists()
    data = json.loads(Path(script_path).read_text(encoding="utf-8"))
    assert data["topic"] == "只看剧本"
    assert data["title"] == script.title

    # No audio segments or final mp3 should be produced.
    assert list((tmp_path / ".storyteller").rglob("*.mp3")) == []


def test_resume_from_script_generated(tmp_path):
    from storyteller.core.project import ProjectManager
    from storyteller.core.models import Script, ScriptLine, Character

    stories_root = tmp_path / ".storyteller" / "stories"
    pm = ProjectManager(stories_root)
    state = pm.create_project(topic="resume-test")
    script = Script(script_id="s1", title="已生成", topic="resume-test")
    script.characters.append(
        Character(id="narrator", name="旁白", description="故事旁白")
    )
    script.lines.append(
        ScriptLine(line_id="1", line_type="narration", text="你好")
    )
    state.script = script
    state.state = "script_generated"
    pm.save_project(state)

    pipeline = _make_pipeline(tmp_path)
    result_path = pipeline.resume(state.project_id)
    assert Path(result_path).exists()


def test_resume_completed_returns_output(tmp_path):
    pipeline = _make_pipeline(tmp_path)
    result_path = Path(pipeline.run("故事"))
    # Resuming a completed project returns the same output path
    project_id = result_path.parent.name
    resume_path = pipeline.resume(project_id)
    assert Path(resume_path).exists()


# ---------- sound effects / background music ----------
def _sound_script():
    import json as _json

    return _json.dumps(
        {
            "title": "雨夜",
            "characters": [
                {"id": "narrator", "name": "旁白", "description": "旁白"},
                {"id": "a", "name": "小兔", "description": "女孩"},
            ],
            "lines": [
                {
                    "line_id": "1",
                    "line_type": "narration",
                    "text": "夜里下起了雨。",
                    "sound_effects": [
                        {
                            "name": "雨声",
                            "type": "ambient",
                            "description": "窗外雨声",
                            "prompt": "舒缓的下雨声，无人声",
                        }
                    ],
                },
                {
                    "line_id": "2",
                    "line_type": "dialogue",
                    "character_id": "a",
                    "text": "好大的雨呀。",
                },
            ],
            "background_music": {
                "name": "宁静夜曲",
                "type": "music",
                "description": "安静的钢琴",
                "prompt": "安静舒缓的钢琴独奏，无人声",
            },
        },
        ensure_ascii=False,
    )


def _make_sound_pipeline(tmp_path, llm, provider, library):
    config = Config()
    config.set("data_dir", str(tmp_path / ".storyteller"))
    config.resolve_paths()
    config.set("sound.enabled", True)
    config.set("sound.dir", str(tmp_path / "sounds"))
    config.set("llm.default_provider", "mock")
    config.set("tts.default_provider", "mock")
    pipeline = Pipeline(
        config, sound_provider=provider, sound_library=library
    )
    pipeline.registry.register_llm("mock", lambda c: llm)
    pipeline.registry.register_tts("mock", MockTTSProvider)
    return pipeline


def test_run_with_sound_mixes_and_backfills_paths(tmp_path):
    import json as _json
    from storyteller.providers.mock.sfx import MockSoundProvider
    from storyteller.core.sound_library import SoundLibrary

    config = Config()
    llm = MockLLMProvider(config)
    llm.set_response(_sound_script())
    provider = MockSoundProvider(config)
    library = SoundLibrary(tmp_path / "sounds")
    pipeline = _make_sound_pipeline(tmp_path, llm, provider, library)

    result_path = Path(pipeline.run("雨夜"))
    assert result_path.exists()

    # Both the BGM and the inline ambient cue were generated exactly once.
    assert len(provider.calls) == 2
    assert len(library.all()) == 2

    data = _json.loads(
        (result_path.parent / "story.script.json").read_text(encoding="utf-8")
    )
    assert data["background_music"]["source_path"]
    assert data["lines"][0]["sound_effects"][0]["source_path"]

    # Every cue has a Chinese-named raw clip INSIDE the project dir...
    project_sounds = result_path.parent / "sounds"
    raw_names = sorted(p.name for p in project_sounds.glob("*.mp3"))
    assert raw_names == ["宁静夜曲.mp3", "雨声.mp3"]
    bgm_path = Path(data["background_music"]["source_path"])
    cue_path = Path(data["lines"][0]["sound_effects"][0]["source_path"])
    assert bgm_path.parent == project_sounds
    assert cue_path.parent == project_sounds
    # ...and an admitted snd_ copy in the global library.
    assert len(list((tmp_path / "sounds").glob("snd_*.mp3"))) == 2

    # No stray temp bed left behind.
    assert list(result_path.parent.glob("*.bgm.mp3")) == []


def test_run_with_sound_reuses_cache_on_second_story(tmp_path):
    import json as _json
    from storyteller.providers.mock.sfx import MockSoundProvider
    from storyteller.core.sound_library import SoundLibrary

    config = Config()
    provider = MockSoundProvider(config)
    library = SoundLibrary(tmp_path / "sounds")

    for _ in range(2):
        llm = MockLLMProvider(config)
        llm.set_response(_sound_script())
        pipeline = _make_sound_pipeline(tmp_path, llm, provider, library)
        result_path = pipeline.run("雨夜")
        assert Path(result_path).exists()

    # Two distinct sounds, requested twice -> still only two API generations.
    assert len(provider.calls) == 2

    # Both projects are self-contained: cache hits are COPIED into each
    # project dir under the cue name, never regenerated.
    project_dirs = sorted(
        p.parent for p in tmp_path.rglob("story.mp3")
    )
    assert len(project_dirs) == 2
    for project_dir in project_dirs:
        names = sorted(p.name for p in (project_dir / "sounds").glob("*.mp3"))
        assert names == ["宁静夜曲.mp3", "雨声.mp3"]


def test_sound_disabled_by_default_ignores_cues(tmp_path):
    import json as _json
    from storyteller.providers.mock.sfx import MockSoundProvider
    from storyteller.core.sound_library import SoundLibrary

    config = Config()
    llm = MockLLMProvider(config)
    llm.set_response(_sound_script())
    provider = MockSoundProvider(config)
    library = SoundLibrary(tmp_path / "sounds")

    # Standard pipeline (sound.enabled left at its default False).
    pipeline = _make_pipeline(tmp_path)
    pipeline.registry.register_llm("mock", lambda c: llm)
    # Recreate with sound dependencies available but feature flag off.
    pipeline._sound_provider = provider
    pipeline._sound_library = library
    result_path = pipeline.run("雨夜")

    assert Path(result_path).exists()
    assert provider.calls == []
    assert not (tmp_path / "sounds").exists()


class _NearSilentSoundProvider:
    """Sound stub that writes an effectively silent clip (~-70 dBFS)."""

    name = "mock"
    model = "mock-sound"

    def generate(self, prompt, output_path, *, audio_format="mp3", **kwargs):
        from pydub.generators import Sine

        output_path.parent.mkdir(parents=True, exist_ok=True)
        Sine(440).to_audio_segment(duration=300).apply_gain(-70).export(
            str(output_path), format="wav"
        )
        return output_path, 0.3


def test_failed_sound_clip_is_kept_in_project_but_not_mixed(tmp_path):
    from storyteller.core.sound_library import SoundLibrary

    config = Config()
    config.set("data_dir", str(tmp_path / ".storyteller"))
    config.resolve_paths()
    config.set("sound.enabled", True)
    config.set("sound.dir", str(tmp_path / "sounds"))
    config.set("llm.default_provider", "mock")
    config.set("tts.default_provider", "mock")

    llm = MockLLMProvider(config)
    llm.set_response(_sound_script())
    library = SoundLibrary(tmp_path / "sounds")
    pipeline = Pipeline(
        config,
        sound_provider=_NearSilentSoundProvider(),
        sound_library=library,
    )
    pipeline.registry.register_llm("mock", lambda c: llm)
    pipeline.registry.register_tts("mock", MockTTSProvider)

    result_path = Path(pipeline.run("雨夜"))
    assert result_path.exists()

    # Both clips failed the gate: raw files kept with cue names...
    project_sounds = result_path.parent / "sounds"
    assert sorted(p.name for p in project_sounds.glob("*.mp3")) == [
        "宁静夜曲.mp3",
        "雨声.mp3",
    ]
    # ...nothing admitted to the global library...
    assert library.all() == []
    assert list((tmp_path / "sounds").glob("snd_*.mp3")) == []
    # ...and the failed cues carry no source_path, so nothing is mixed.
    import json as _json

    data = _json.loads(
        (result_path.parent / "story.script.json").read_text(encoding="utf-8")
    )
    assert data["background_music"]["source_path"] is None
    assert data["lines"][0]["sound_effects"][0]["source_path"] is None


def _make_registry_sound_pipeline(tmp_path, llm, library):
    """Like _make_sound_pipeline, but the sound provider comes from the
    registry (config-selected) instead of constructor injection."""
    from storyteller.providers.mock.sfx import MockSoundProvider

    config = Config()
    config.set("data_dir", str(tmp_path / ".storyteller"))
    config.resolve_paths()
    config.set("sound.enabled", True)
    config.set("sound.dir", str(tmp_path / "sounds"))
    config.set("sound.default_provider", "mock")
    config.set("llm.default_provider", "mock")
    config.set("tts.default_provider", "mock")
    pipeline = Pipeline(config, sound_library=library)
    pipeline.registry.register_llm("mock", lambda c: llm)
    pipeline.registry.register_tts("mock", MockTTSProvider)
    pipeline.registry.register_sound("mock", MockSoundProvider)
    return pipeline


def test_run_resolves_sound_provider_from_registry(tmp_path):
    from storyteller.providers.mock.sfx import MockSoundProvider
    from storyteller.core.sound_library import SoundLibrary

    config = Config()
    llm = MockLLMProvider(config)
    llm.set_response(_sound_script())
    library = SoundLibrary(tmp_path / "sounds")
    pipeline = _make_registry_sound_pipeline(tmp_path, llm, library)

    result_path = Path(pipeline.run("雨夜"))
    assert result_path.exists()
    # Both cues generated through the registry-resolved mock provider.
    assert len(library.all()) == 2
    assert isinstance(pipeline._get_sound_provider(), MockSoundProvider)


def test_sound_enabled_without_any_provider_raises(tmp_path):
    # The mock default script has no cues, so use _sound_script(): the
    # soundtrack stage only resolves the provider when pending cues exist.
    config = Config()
    config.set("data_dir", str(tmp_path / ".storyteller"))
    config.resolve_paths()
    config.set("sound.enabled", True)
    config.set("sound.dir", str(tmp_path / "sounds"))
    config.set("llm.default_provider", "mock")
    config.set("tts.default_provider", "mock")
    llm = MockLLMProvider(config)
    llm.set_response(_sound_script())
    pipeline = Pipeline(config)
    pipeline.registry.register_llm("mock", lambda c: llm)
    pipeline.registry.register_tts("mock", MockTTSProvider)
    # No sound provider registered at all.

    with pytest.raises(TTSError, match="No sound provider configured"):
        pipeline.run("雨夜")


def test_unknown_tts_provider_fails_before_matching(tmp_path):
    pipeline = _make_pipeline(tmp_path)
    with pytest.raises(TTSError, match="Unknown TTS provider"):
        pipeline.run("雨夜", tts_providers=["aliyun"])