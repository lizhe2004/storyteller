import json
import unicodedata

from click.testing import CliRunner

from storyteller.cli.main import cli


def _w(line):
    """Display width of a line: CJK wide/fullwidth chars count as 2 columns."""
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
        for ch in line
    )


_MOCK_ENV = {
    "STORYTELLER_LLM_PROVIDERS": "mock",
    "STORYTELLER_LLM_MOCK_TYPE": "mock",
    "STORYTELLER_LLM_DEFAULT_PROVIDER": "mock",
    "STORYTELLER_TTS_PROVIDERS": "mock",
    "STORYTELLER_TTS_MOCK_TYPE": "mock",
    "STORYTELLER_TTS_DEFAULT_PROVIDER": "mock",
    "STORYTELLER_SOUND_PROVIDERS": "mock",
    "STORYTELLER_SOUND_MOCK_TYPE": "mock",
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
        assert "Mock（测试）" in result.output
        assert "narrator_01" in result.output
        assert "男" in result.output and "女" in result.output
        assert "有声阅读" in result.output
        # Table headers present, and the old confusing 类型 column is gone.
        for header in ("名称", "音色ID", "性别", "年龄段", "场景"):
            assert header in result.output
        assert "类型" not in result.output
        # CJK alignment regression: every table line must share one display width.
        table_lines = [
            line for line in result.output.splitlines()
            if line.startswith(("+", "|"))
        ]
        widths = {_w(line) for line in table_lines}
        assert len(widths) == 1, widths
        # Descriptions are inlined under their own voice row: the old
        # post-table footnote block is gone.
        assert "阳光清亮的青年男声" in result.output
        assert "  · " not in result.output
        # On description rows the name column (first cell) stays blank,
        # the text starts at the voice-ID column.
        desc_lines = [
            line for line in result.output.splitlines()
            if "青年男声" in line and "|" in line and "male_01" not in line
        ]
        assert desc_lines
        for line in desc_lines:
            first_cell = line.split("|", 2)[1]
            assert first_cell.strip() == ""


def test_list_voices_json():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["list-voices", "--tts-providers", "mock", "--format", "json"],
            env=_MOCK_ENV,
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert isinstance(data, list) and data
        row = next(v for v in data if v["voice_id"] == "female_01")
        assert row["gender"] == "female"
        assert row["age"] == "middle_aged"
        assert row["category"] == "通用场景"
        assert all("voice_type" not in v for v in data)


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


def test_generate_with_sound_provider_flag():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["generate", "测试故事", "--with-sfx", "--sound-provider", "mock"],
            env=_MOCK_ENV,
        )
        assert result.exit_code == 0, result.output


def test_generate_unknown_sound_provider_fails_before_generation():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["generate", "测试故事", "--sound-provider", "nope"],
            env=_MOCK_ENV,
        )
        assert result.exit_code != 0
        assert "Unknown sound provider" in result.output
        assert "mock" in result.output


def test_continue_accepts_provider_selection_flags():
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Unknown project, but click must accept every flag first
        # (regression: continue used to lack these options).
        result = runner.invoke(
            cli,
            [
                "continue", "proj_does_not_exist",
                "--default-llm-provider", "mock",
                "--default-tts-provider", "mock",
                "--sound-provider", "mock",
            ],
            env=_MOCK_ENV,
        )
        assert result.exit_code != 0
        assert "no such option" not in result.output.lower()


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


def test_make_sound_uses_registry_provider():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["make-sound", "舒缓的雨声", "--sound-provider", "mock"],
            env=_MOCK_ENV,
        )
        assert result.exit_code == 0, result.output
        assert "Generated" in result.output


def test_make_sound_without_configured_provider_errors():
    runner = CliRunner()
    env = {
        "STORYTELLER_LLM_PROVIDERS": "mock",
        "STORYTELLER_TTS_PROVIDERS": "mock",
    }
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli, ["make-sound", "风声"], env=env
        )
        assert result.exit_code != 0
        assert "No sound provider configured" in result.output