from __future__ import annotations

import click

from ..core.config import Config
from ..core.pipeline import Pipeline
from ..providers.bootstrap import register_providers_from_config


LENGTHS = ["short", "medium", "long"]
LENGTH_LABELS = {"short": "短篇", "medium": "中篇", "long": "长篇"}

COMPLEXITIES = ["simple", "medium", "rich"]
COMPLEXITY_LABELS = {"simple": "简单", "medium": "中等", "rich": "丰富"}

OUTPUT_FORMATS = ["mp3", "wav"]


def parse_choice(text, options, default_index):
    """Parse a user choice into an option value.

    Accepts a 1-based number, an exact option string, or empty (default).
    """
    stripped = (text or "").strip()
    if not stripped:
        return options[default_index]
    if stripped.isdigit():
        idx = int(stripped) - 1
        if 0 <= idx < len(options):
            return options[idx]
        return options[default_index]
    if stripped in options:
        return stripped
    return options[default_index]


def parse_yes_no(text, default=True):
    """Parse a yes/no answer. Empty returns default; garbage returns default."""
    stripped = (text or "").strip().lower()
    if not stripped:
        return default
    if stripped in ("y", "yes"):
        return True
    if stripped in ("n", "no"):
        return False
    return default


def run_wizard(config=None):
    """Run the full interactive wizard, returning a populated pipeline + options."""
    config = config or Config.from_env()
    _apply_common(config)

    click.echo("🎬 Storyteller - 音频故事生成器")
    click.echo("（直接回车使用默认值）\n")

    topic = click.prompt("请输入故事主题", default="")
    while not topic.strip():
        click.echo("主题不能为空，请重新输入。")
        topic = click.prompt("请输入故事主题", default="")

    length = _prompt_length()
    complexity = _prompt_complexity()
    output_format = _prompt_format()

    click.echo("\n确认配置：")
    click.echo("  主题: {}".format(topic))
    click.echo("  长度: {}".format(LENGTH_LABELS[length]))
    click.echo("  复杂度: {}".format(COMPLEXITY_LABELS[complexity]))
    click.echo("  格式: {}".format(output_format))

    pipeline = _build_pipeline(config)
    tts_providers = _prompt_voice_mode(pipeline, config)

    return pipeline, topic, length, complexity, output_format, tts_providers


def _apply_common(config):
    pass


def _prompt_length():
    click.echo("\n选择故事长度：")
    for i, opt in enumerate(LENGTHS, start=1):
        click.echo("  [{}] {}".format(i, LENGTH_LABELS[opt]))
    return parse_choice(click.prompt("请选择", default="2"), LENGTHS, 1)


def _prompt_complexity():
    click.echo("\n选择剧本复杂度：")
    for i, opt in enumerate(COMPLEXITIES, start=1):
        click.echo("  [{}] {}".format(i, COMPLEXITY_LABELS[opt]))
    return parse_choice(
        click.prompt("请选择", default="1"), COMPLEXITIES, 0
    )


def _prompt_format():
    click.echo("\n选择输出格式：")
    for i, opt in enumerate(OUTPUT_FORMATS, start=1):
        click.echo("  [{}] {}".format(i, opt))
    return parse_choice(
        click.prompt("请选择", default="1"), OUTPUT_FORMATS, 0
    )


def _prompt_voice_mode(pipeline, config):
    click.echo("\n角色声音配置方式：")
    click.echo("  [1] 自动匹配（推荐）")
    click.echo("  [2] 稍后手动选择")
    choice = click.prompt("请选择", default="1")
    if parse_choice(choice, ["auto", "manual"], 0) == "auto":
        return None
    # Manual mode not yet wired; treated as auto for now.
    return None


def _build_pipeline(config):
    pipeline = Pipeline(config)
    register_providers_from_config(config, pipeline.registry)
    return pipeline


if __name__ == "__main__":
    run_wizard()