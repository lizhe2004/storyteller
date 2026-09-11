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
    env["STORYTELLER_DATA_DIR"] = str(tmp_path / "data")

    result = runner.invoke(
        cli,
        ["generate", "一只在公园里迷路的小猫"],
        env=env,
    )
    assert result.exit_code == 0, result.output

    # Final audio, segments and state all live under one per-project folder.
    stories = tmp_path / "data" / "stories"
    assert stories.exists()
    project_dirs = [p for p in stories.iterdir() if p.is_dir()]
    assert project_dirs
    project_dir = project_dirs[0]
    assert (project_dir / "story.mp3").exists()
    assert (project_dir / "audio").is_dir()
    assert (project_dir / "project.json").exists()


def test_full_flow_continue_project(tmp_path):
    runner = CliRunner()
    env = dict(_MOCK_ENV)
    env["STORYTELLER_DATA_DIR"] = str(tmp_path / "data")

    # First, generate
    result = runner.invoke(
        cli, ["generate", "测试故事"], env=env
    )
    assert result.exit_code == 0, result.output

    # Extract project_id from the per-project directory
    project_dirs = [
        p for p in (tmp_path / "data" / "stories").iterdir() if p.is_dir()
    ]
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
    env["STORYTELLER_DATA_DIR"] = str(tmp_path / "data")

    result = runner.invoke(
        cli, ["generate", "dry-run测试", "--dry-run"], env=env
    )
    assert result.exit_code == 0, result.output
    assert "Dry-run" in result.output


def test_full_flow_list_projects(tmp_path):
    runner = CliRunner()
    env = dict(_MOCK_ENV)
    env["STORYTELLER_DATA_DIR"] = str(tmp_path / "data")

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
    assert "Mock（测试）" in result.output


def test_full_flow_with_length_and_complexity(tmp_path):
    runner = CliRunner()
    env = dict(_MOCK_ENV)
    env["STORYTELLER_DATA_DIR"] = str(tmp_path / "data")

    result = runner.invoke(
        cli,
        ["generate", "短篇故事", "--length", "short", "--complexity", "rich"],
        env=env,
    )
    assert result.exit_code == 0, result.output