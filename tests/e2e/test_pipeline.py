from pathlib import Path

import pytest

from storyteller.core.config import Config
from storyteller.core.pipeline import Pipeline
from storyteller.providers.mock.llm import MockLLMProvider
from storyteller.providers.mock.tts import MockTTSProvider


def _make_pipeline(tmp_path):
    config = Config()
    config.set("output_dir", str(tmp_path / "outputs"))
    config.set("project_dir", str(tmp_path / "projects"))
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
    assert Path(result_path).suffix == ".mp3"


def test_run_saves_project_state(tmp_path):
    pipeline = _make_pipeline(tmp_path)
    pipeline.run("测试故事")

    project_dir = tmp_path / "projects"
    assert project_dir.exists()
    projects = list(project_dir.iterdir())
    assert len(projects) >= 1
    json_files = [f for f in projects[0].iterdir() if f.suffix == ".json"]
    assert len(json_files) >= 1


def test_run_writes_script_and_audio(tmp_path):
    pipeline = _make_pipeline(tmp_path)
    result_path = pipeline.run("小猫咪的故事")

    outputs = tmp_path / "outputs"
    assert outputs.exists()
    audio_files = list(outputs.rglob("*.mp3"))
    assert len(audio_files) >= 1


def test_resume_from_script_generated(tmp_path):
    from storyteller.core.project import ProjectManager
    from storyteller.core.models import Script, ScriptLine, Character

    pm = ProjectManager(tmp_path / "projects")
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
    result_path = pipeline.run("故事")
    # Resuming a completed project returns the same output path
    project_id = Path(result_path).stem
    resume_path = pipeline.resume(project_id)
    assert Path(resume_path).exists()