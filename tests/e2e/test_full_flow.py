"""End-to-end test for the complete story-to-audio pipeline."""
from pathlib import Path

import pytest
from click.testing import CliRunner

from storyteller.cli.main import cli


_MOCK_ENV = {
    "STORYTELLER_LLM_PROVIDERS": "mock",
    "STORYTELLER_LLM_MOCK_TYPE": "mock",
    "STORYTELLER_LLM_DEFAULT_PROVIDER": "mock",
    "STORYTELLER_TTS_PROVIDERS": "mock",
    "STORYTELLER_TTS_MOCK_TYPE": "mock",
    "STORYTELLER_TTS_DEFAULT_PROVIDER": "mock",
}


def test_full_flow_generate_produces_audio(tmp_path):
    runner = CliRunner()
    env = dict(_MOCK_ENV)
    env["STORYTELLER_OUTPUT_DIR"] = str(tmp_path / "outputs")
    env["STORYTELLER_PROJECT_DIR"] = str(tmp_path / "projects")

    result = runner.invoke(
        cli,
        ["generate", "一只在公园里迷路的小猫"],
        env=env,
    )
    assert result.exit_code == 0, result.output

    # Output audio exists
    outputs = tmp_path / "outputs"
    assert outputs.exists()
    mp3_files = list(outputs.glob("*.mp3"))
    assert len(mp3_files) >= 1, f"Expected at least one mp3 in {outputs}, got {list(outputs.iterdir())}"

    # Per-line audio segments exist
    audio_dir = list(outputs.iterdir())
    assert any(p.is_dir() for p in audio_dir), "Expected project subdirectory"

    # Project state is saved
    projects = tmp_path / "projects"
    assert projects.exists()
    assert len(list(projects.iterdir())) >= 1


def test_full_flow_continue_project(tmp_path):
    runner = CliRunner()
    env = dict(_MOCK_ENV)
    env["STORYTELLER_OUTPUT_DIR"] = str(tmp_path / "outputs")
    env["STORYTELLER_PROJECT_DIR"] = str(tmp_path / "projects")

    # First, generate
    result = runner.invoke(
        cli, ["generate", "测试故事"], env=env
    )
    assert result.exit_code == 0, result.output

    # Extract project_id from output directory
    project_dirs = [p for p in (tmp_path / "outputs").iterdir() if p.is_dir()]
    assert len(project_dirs) >= 1
    project_id = project_dirs[0].name

    # Continue should succeed (already completed, just return output)
    result = runner.invoke(
        cli, ["continue", project_id], env=env
    )
    assert result.exit_code == 0, result.output


def test_full_flow_dry_run(tmp_path):
    runner = CliRunner()
    env = dict(_MOCK_ENV)
    env["STORYTELLER_OUTPUT_DIR"] = str(tmp_path / "outputs")
    env["STORYTELLER_PROJECT_DIR"] = str(tmp_path / "projects")

    result = runner.invoke(
        cli, ["generate", "dry-run测试", "--dry-run"], env=env
    )
    assert result.exit_code == 0, result.output
    assert "Dry-run" in result.output


def test_full_flow_list_projects(tmp_path):
    runner = CliRunner()
    env = dict(_MOCK_ENV)
    env["STORYTELLER_OUTPUT_DIR"] = str(tmp_path / "outputs")
    env["STORYTELLER_PROJECT_DIR"] = str(tmp_path / "projects")

    # Generate two projects
    runner.invoke(cli, ["generate", "故事一"], env=env)
    runner.invoke(cli, ["generate", "故事二"], env=env)

    # List should show both
    result = runner.invoke(cli, ["list-projects"], env=env)
    assert result.exit_code == 0, result.output


def test_full_flow_list_voices():
    runner = CliRunner()
    env = dict(_MOCK_ENV)

    result = runner.invoke(cli, ["list-voices"], env=env)
    assert result.exit_code == 0, result.output
    assert "mock" in result.output


def test_full_flow_with_length_and_complexity(tmp_path):
    runner = CliRunner()
    env = dict(_MOCK_ENV)
    env["STORYTELLER_OUTPUT_DIR"] = str(tmp_path / "outputs")
    env["STORYTELLER_PROJECT_DIR"] = str(tmp_path / "projects")

    result = runner.invoke(
        cli,
        ["generate", "短篇故事", "--length", "short", "--complexity", "rich"],
        env=env,
    )
    assert result.exit_code == 0, result.output