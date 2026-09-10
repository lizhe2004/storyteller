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


def test_wizard_full_flow():
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Input sequence: topic, length, complexity, format, voice-mode
        user_input = "\n".join(
            [
                "小猫迷路了",  # topic
                "2",           # length: medium
                "1",           # complexity: simple
                "1",           # format: mp3
                "1",           # voice mode: auto
            ]
        ) + "\n"
        result = runner.invoke(
            cli, [], input=user_input, env=_MOCK_ENV
        )
        assert result.exit_code == 0, result.output
        assert "Done" in result.output


def test_wizard_rejects_empty_topic():
    runner = CliRunner()
    with runner.isolated_filesystem():
        # First topic empty, then a real topic
        user_input = "\n".join(
            [
                "",            # empty topic (rejected)
                "太空",        # valid topic
                "2",
                "1",
                "1",
                "1",
            ]
        ) + "\n"
        result = runner.invoke(
            cli, [], input=user_input, env=_MOCK_ENV
        )
        assert result.exit_code == 0, result.output
        assert "不能为空" in result.output