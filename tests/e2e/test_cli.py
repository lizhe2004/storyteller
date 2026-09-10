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


def test_list_voices_shows_mock():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["list-voices", "--tts-providers", "mock"],
            env=_MOCK_ENV,
        )
        assert result.exit_code == 0, result.output
        assert "mock" in result.output
        assert "narrator_01" in result.output


def test_generate_with_mock_succeeds():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["generate", "测试故事"],
            env=_MOCK_ENV,
        )
        assert result.exit_code == 0, result.output
        assert "Done" in result.output


def test_generate_dry_run():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["generate", "测试故事", "--dry-run"],
            env=_MOCK_ENV,
        )
        assert result.exit_code == 0, result.output
        assert "Dry-run" in result.output


def test_list_projects_empty():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["list-projects"])
        assert result.exit_code == 0
        assert isinstance(result.output, str)


def test_unknown_command_fails():
    runner = CliRunner()
    result = runner.invoke(cli, ["nonsense"])
    assert result.exit_code != 0