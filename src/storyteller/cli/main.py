from __future__ import annotations

import click

from ..core.config import Config
from ..core.pipeline import Pipeline
from ..providers.bootstrap import register_providers_from_config


@click.group()
def cli():
    """storyteller - 把故事主题变成带角色声音的音频故事。"""


# ========== 通用选项 ==========
_common_options = [
    click.option("--output-dir", "-o", default=None, help="输出目录"),
    click.option("--project-dir", default=None, help="项目保存目录"),
    click.option("--log-level", default=None, help="日志级别 debug/info/warn/error"),
    click.option(
        "--progress",
        type=click.Choice(["quiet", "simple", "detailed"]),
        default=None,
        help="进度显示级别",
    ),
    click.option("--strict-mode", is_flag=True, help="严格模式（出错立即停止）"),
]


def _apply_options(config, **kwargs):
    """Fold CLI options into the config object."""
    if kwargs.get("output_dir"):
        config.set("output_dir", kwargs["output_dir"])
    if kwargs.get("project_dir"):
        config.set("project_dir", kwargs["project_dir"])
    if kwargs.get("log_level"):
        config.set("log_level", kwargs["log_level"])
    if kwargs.get("progress"):
        config.set("progress_level", kwargs["progress"])
    if kwargs.get("strict_mode"):
        config.set("strict_mode", True)
    if kwargs.get("output_format"):
        config.set("output_format", kwargs["output_format"])
    return config


def _build_pipeline(**options):
    config = Config.from_env()
    _apply_options(config, **options)

    # Provider overrides from CLI
    if options.get("default_llm_provider"):
        config.set("llm.default_provider", options["default_llm_provider"])
    if options.get("default_tts_provider"):
        config.set("tts.default_provider", options["default_tts_provider"])

    pipeline = Pipeline(config)
    register_providers_from_config(config, pipeline.registry)
    return pipeline


# ========== generate ==========
@cli.command()
@click.argument("topic")
@click.option("--length", "-l", type=click.Choice(["short", "medium", "long"]), default="medium")
@click.option("--complexity", "-c", type=click.Choice(["simple", "medium", "rich"]), default="simple")
@click.option("--output-format", "-f", default=None, help="输出格式 mp3/wav/ogg")
@click.option("--tts-providers", default=None, help="可用的TTS provider列表，逗号分隔")
@click.option("--voice-ids", default=None, help="限制使用的音色ID列表，逗号分隔")
@click.option("--default-llm-provider", default=None, help="默认LLM provider")
@click.option("--default-tts-provider", default=None, help="默认TTS provider")
@click.option("--dry-run", is_flag=True, help="只生成剧本，不生成音频")
@click.option("--output-dir", "-o", default=None)
@click.option("--project-dir", default=None)
@click.option("--log-level", default=None)
@click.option("--progress", type=click.Choice(["quiet", "simple", "detailed"]), default=None)
@click.option("--strict-mode", is_flag=True)
def generate(
    topic,
    length,
    complexity,
    output_format,
    tts_providers,
    voice_ids,
    default_llm_provider,
    default_tts_provider,
    dry_run,
    **options,
):
    """根据主题生成音频故事。"""
    pipeline = _build_pipeline(
        output_format=output_format,
        default_llm_provider=default_llm_provider,
        default_tts_provider=default_tts_provider,
        **options,
    )

    kwargs = {}
    if tts_providers:
        kwargs["tts_providers"] = [p.strip() for p in tts_providers.split(",") if p.strip()]
    if voice_ids:
        kwargs["voice_ids"] = {v.strip() for v in voice_ids.split(",") if v.strip()}

    if dry_run:
        script = _dry_run_script(pipeline, topic, length, complexity)
        click.echo("Dry-run 剧本生成完成：{}".format(script.title))
        return

    try:
        output_path = pipeline.run(
            topic,
            length=length,
            complexity=complexity,
            **kwargs,
        )
    except Exception as exc:
        raise click.ClickException(str(exc))

    click.echo("Done! Output: {}".format(output_path))


def _dry_run_script(pipeline, topic, length, complexity):
    from ..core.story_generator import StoryGenerator

    llm = pipeline._get_default_llm()
    generator = StoryGenerator(llm)
    return generator.generate_script(topic, length, complexity)


# ========== continue ==========
@cli.command()
@click.argument("project_id")
@click.option("--output-format", "-f", default=None)
@click.option("--tts-providers", default=None)
@click.option("--voice-ids", default=None)
@click.option("--output-dir", "-o", default=None)
@click.option("--project-dir", default=None)
@click.option("--strict-mode", is_flag=True)
def continue_(project_id, **options):
    """从断点继续一个项目。"""
    pipeline = _build_pipeline(**options)
    kwargs = {}
    if options.get("tts_providers"):
        kwargs["tts_providers"] = [p.strip() for p in options["tts_providers"].split(",") if p.strip()]
    if options.get("voice_ids"):
        kwargs["voice_ids"] = {v.strip() for v in options["voice_ids"].split(",") if v.strip()}
    if options.get("output_format"):
        kwargs["output_format"] = options["output_format"]

    try:
        output_path = pipeline.resume(project_id, **kwargs)
    except Exception as exc:
        raise click.ClickException(str(exc))

    click.echo("Done! Output: {}".format(output_path))


# ========== list-projects ==========
@cli.command()
@click.option("--project-dir", default=None)
def list_projects(project_dir):
    """列出所有项目。"""
    from ..core.project import ProjectManager

    config = Config.from_env()
    root = project_dir or config.get("project_dir") or "./projects"
    manager = ProjectManager(root)
    projects = manager.list_projects()
    if not projects:
        click.echo("没有找到项目。")
        return
    for state in projects:
        status = click.style(state.state, fg="green" if state.state == "completed" else "yellow")
        click.echo("{}  [{}]  {}".format(state.project_id, status, state.config.get("topic", "")))


# ========== list-voices ==========
@cli.command()
@click.option("--tts-providers", default=None, help="要查询的provider，逗号分隔")
def list_voices(tts_providers):
    """列出所有可用的TTS音色。"""
    pipeline = _build_pipeline()
    providers = None
    if tts_providers:
        providers = [p.strip() for p in tts_providers.split(",") if p.strip()]

    try:
        voices = pipeline.registry.list_tts_voices(providers)
    except Exception as exc:
        raise click.ClickException(str(exc))

    if not voices:
        click.echo("没有可用的音色。请检查配置。")
        return

    by_provider = {}
    for voice in voices:
        by_provider.setdefault(voice.provider, []).append(voice)

    for provider, pv in by_provider.items():
        click.echo("[{}]".format(provider))
        for voice in pv:
            click.echo("  {}  ({})".format(voice.voice_id, voice.voice_type))


# Alias continue_ to `continue` (reserved word in Python)
continue_.name = "continue"


if __name__ == "__main__":
    cli()