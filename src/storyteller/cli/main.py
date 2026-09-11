from __future__ import annotations

import click

from ..core.config import Config
from ..core.pipeline import Pipeline
from ..providers.bootstrap import register_providers_from_config


def _display_width(text):
    """Approx. terminal cell width: CJK chars count as 2 columns."""
    import unicodedata
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
        for ch in str(text)
    )


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """storyteller - 把故事主题变成带角色声音的音频故事。"""
    if ctx.invoked_subcommand is None:
        ctx.invoke(wizard)


@cli.command()
def wizard():
    """交互式向导模式（无参数运行时的默认入口）。"""
    from .interactive import run_wizard

    (
        pipeline, topic, length, complexity, output_format,
        tts_providers, with_sfx, sound_provider,
    ) = run_wizard()
    if with_sfx:
        pipeline.config.set("sound.enabled", True)
    if sound_provider:
        pipeline.config.set("sound.default_provider", sound_provider)
    kwargs = {"output_format": output_format}
    if tts_providers:
        kwargs["tts_providers"] = tts_providers
    try:
        output_path = pipeline.run(
            topic, length=length, complexity=complexity, **kwargs
        )
    except Exception as exc:
        raise click.ClickException(str(exc))
    click.echo("Done! Output: {}".format(output_path))


# ========== 通用选项 ==========
_common_options = [
    click.option(
        "--data-dir",
        default=None,
        help="生成物根目录（默认 ./.storyteller，含 stories/ 与 sounds/）",
    ),
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
    if kwargs.get("data_dir"):
        config.set("data_dir", kwargs["data_dir"])
        config.resolve_paths()
    if kwargs.get("log_level"):
        config.set("log_level", kwargs["log_level"])
    if kwargs.get("progress"):
        config.set("progress_level", kwargs["progress"])
    if kwargs.get("strict_mode"):
        config.set("strict_mode", True)
    if kwargs.get("output_format"):
        config.set("output_format", kwargs["output_format"])
    if kwargs.get("voice_matcher"):
        config.set("voice_matcher", kwargs["voice_matcher"])
    if kwargs.get("with_sfx"):
        config.set("sound.enabled", True)
    if kwargs.get("sound_dir"):
        config.set("sound.dir", kwargs["sound_dir"])
    return config


def _build_pipeline(**options):
    config = Config.from_env()
    _apply_options(config, **options)

    # Provider overrides from CLI
    if options.get("default_llm_provider"):
        config.set("llm.default_provider", options["default_llm_provider"])
    if options.get("default_tts_provider"):
        config.set("tts.default_provider", options["default_tts_provider"])
    if options.get("sound_provider"):
        config.set("sound.default_provider", options["sound_provider"])

    pipeline = Pipeline(config)
    register_providers_from_config(config, pipeline.registry)

    requested_sound = options.get("sound_provider")
    if requested_sound is not None:
        available = pipeline.registry.list_sound_names()
        if requested_sound not in available:
            raise click.ClickException(
                "Unknown sound provider: {}. Configured sound providers: "
                "{}. Set STORYTELLER_SOUND_<NAME>_API_KEY to configure one."
                .format(requested_sound, ", ".join(available) or "(none)")
            )
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
@click.option(
    "--data-dir",
    default=None,
    help="生成物根目录（默认 ./.storyteller，含 stories/ 与 sounds/）",
)
@click.option("--log-level", default=None)
@click.option("--progress", type=click.Choice(["quiet", "simple", "detailed"]), default=None)
@click.option("--strict-mode", is_flag=True)
@click.option(
    "--voice-matcher",
    type=click.Choice(["llm", "rule"]),
    default=None,
    help="音色匹配方式：llm 语义匹配（默认）或 rule 规则匹配",
)
@click.option(
    "--with-sfx",
    is_flag=True,
    help="生成音效与背景音乐并自动混音（seed-audio，结果缓存到音效库）",
)
@click.option("--sound-dir", default=None, help="音效库目录（默认 <data-dir>/sounds）")
@click.option(
    "--sound-provider",
    default=None,
    help="本次运行使用的音效 provider（覆盖环境默认）",
)
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
        script, script_path = pipeline.draft_script(
            topic, length=length, complexity=complexity
        )
        click.echo("Dry-run 剧本生成完成：{}".format(script.title))
        click.echo("剧本已保存：{}".format(script_path))
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


# ========== continue ==========
@cli.command(name="continue")
@click.argument("project_id")
@click.option("--output-format", "-f", default=None)
@click.option("--tts-providers", default=None)
@click.option("--voice-ids", default=None)
@click.option(
    "--data-dir",
    default=None,
    help="生成物根目录（默认 ./.storyteller，含 stories/ 与 sounds/）",
)
@click.option("--strict-mode", is_flag=True)
@click.option(
    "--voice-matcher",
    type=click.Choice(["llm", "rule"]),
    default=None,
    help="音色匹配方式：llm 语义匹配（默认）或 rule 规则匹配",
)
@click.option(
    "--with-sfx",
    is_flag=True,
    help="生成音效与背景音乐并自动混音（seed-audio，结果缓存到音效库）",
)
@click.option("--sound-dir", default=None, help="音效库目录（默认 <data-dir>/sounds）")
@click.option("--default-llm-provider", default=None, help="默认LLM provider")
@click.option("--default-tts-provider", default=None, help="默认TTS provider")
@click.option(
    "--sound-provider",
    default=None,
    help="本次运行使用的音效 provider（覆盖环境默认）",
)
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
@click.option(
    "--data-dir",
    default=None,
    help="生成物根目录（默认 ./.storyteller）",
)
def list_projects(data_dir):
    """列出所有项目。"""
    from ..core.project import ProjectManager

    config = Config.from_env()
    if data_dir:
        config.set("data_dir", data_dir)
        config.resolve_paths()
    root = config.get("project_dir")
    manager = ProjectManager(root)
    projects = manager.list_projects()
    if not projects:
        click.echo("没有找到项目。")
        return
    for state in projects:
        status = click.style(state.state, fg="green" if state.state == "completed" else "yellow")
        click.echo("{}  [{}]  {}".format(state.project_id, status, state.config.get("topic", "")))


# ========== list-voices ==========
_AGE_CN = {
    "child": "儿童", "teen": "少年", "young_adult": "青年",
    "middle_aged": "中年", "senior": "老年",
}
_GENDER_CN = {"male": "男", "female": "女"}


@cli.command(name="list-voices")
@click.option("--tts-providers", default=None, help="要查询的provider，逗号分隔")
@click.option(
    "--format", "output_format",
    type=click.Choice(["table", "json"]), default="table",
    help="输出格式：table 表格（默认）或 json",
)
def list_voices(tts_providers, output_format):
    """列出所有可用的TTS音色。"""
    pipeline = _build_pipeline()
    providers = None
    if tts_providers:
        providers = [p.strip() for p in tts_providers.split(",") if p.strip()]
    else:
        providers = pipeline.registry.list_tts_names()

    try:
        voices = pipeline.registry.list_tts_voices(providers)
    except Exception as exc:
        raise click.ClickException(str(exc))

    if not voices:
        click.echo("没有可用的音色。请检查配置。")
        return

    if output_format == "json":
        import json as _json
        click.echo(_json.dumps(
            [_voice_row(v) for v in voices], ensure_ascii=False, indent=2
        ))
        return

    by_provider = {}
    for v in voices:
        by_provider.setdefault(v.provider, []).append(v)

    for provider_name in providers:
        pv = by_provider.get(provider_name)
        if not pv:
            continue
        tts = pipeline.registry.get_tts(provider_name)
        header = getattr(tts, "display_name", provider_name)
        desc = getattr(tts, "display_description", "")
        click.echo("【{}】{}（{} 个音色）".format(
            header, "  " + desc if desc else "", len(pv)))
        _print_voice_table(pv)
        click.echo()


def _voice_row(v):
    return {
        "provider": v.provider,
        "voice_id": v.voice_id,
        "name": v.name,
        "gender": v.gender,
        "age": v.age,
        "category": v.category,
        "description": v.description,
        "language": v.language,
    }


def _wrap_by_width(text, width):
    """Greedy wrap by terminal display width (CJK chars count as 2)."""
    lines = []
    current = ""
    current_w = 0
    for ch in str(text):
        ch_w = _display_width(ch)
        if current_w + ch_w > width:
            lines.append(current)
            current, current_w = ch, ch_w
        else:
            current += ch
            current_w += ch_w
    lines.append(current)
    # Avoid orphan runs (<=2 display cols, e.g. one CJK char) on the last line.
    if len(lines) > 1 and _display_width(lines[-1]) <= 2:
        tail = lines[-2][-2:]
        lines[-2] = lines[-2][:-2]
        lines[-1] = tail + lines[-1]
    return lines


def _print_voice_table(voices):
    headers = ["名称", "音色ID", "性别", "年龄段", "场景"]
    rows = [
        (
            [
                v.name or "-",
                v.voice_id,
                _GENDER_CN.get(v.gender, "中性"),
                _AGE_CN.get(v.age, "-"),
                v.category or "-",
            ],
            v.description or "",
        )
        for v in voices
    ]
    widths = [_display_width(h) for h in headers]
    for cells, _ in rows:
        for i, cell in enumerate(cells):
            widths[i] = max(widths[i], _display_width(cell))

    def border():
        return "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def fmt(cells):
        return "|" + "|".join(
            " {} ".format(cells[i] + " " * (widths[i] - _display_width(cells[i])))
            for i in range(len(cells))
        ) + "|"

    # Description rows leave the name cell blank and merge the remaining
    # four columns into one text area.
    desc_width = sum(widths[1:]) + 2 * len(widths[1:]) + 3 - 2

    def fmt_desc(text):
        return (
            "|"
            + " " * (widths[0] + 2)
            + "| "
            + text + " " * (desc_width - _display_width(text))
            + " |"
        )

    click.echo(border())
    click.echo(fmt(headers))
    click.echo(border())
    for cells, description in rows:
        click.echo(fmt(cells))
        if description:
            for line in _wrap_by_width(description, desc_width):
                click.echo(fmt_desc(line))
        click.echo(border())


# Note: The continue command is registered with name="continue" above.


# ========== make-sound ==========
@cli.command(name="make-sound")
@click.argument("prompt")
@click.option("--name", default=None, help="音效名称（默认取提示词开头）")
@click.option(
    "--kind",
    type=click.Choice(["sfx", "ambient", "music"]),
    default="sfx",
    help="类型：sfx 短促音效 / ambient 环境声 / music 音乐",
)
@click.option("--description", default="", help="这条音效的描述（便于检索复用）")
@click.option("--tags", default="", help="逗号分隔的标签")
@click.option("--format", "audio_format", default="mp3", help="输出格式 mp3/wav")
@click.option("--sound-dir", default=None, help="音效库目录（默认 <data-dir>/sounds）")
@click.option(
    "--sound-provider",
    default=None,
    help="使用的音效 provider（默认取 STORYTELLER_SOUND_DEFAULT_PROVIDER）",
)
def make_sound(prompt, name, kind, description, tags, audio_format,
               sound_dir, sound_provider):
    """用文字提示生成/复用一个音效，写入全局音效库。"""
    config = Config.from_env()
    if sound_dir:
        config.set("sound.dir", sound_dir)

    from ..core.sound_library import SoundLibrary
    from ..providers.registry import ProviderRegistry

    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)

    chosen = sound_provider or config.get("sound.default_provider")
    available = registry.list_sound_names()
    if chosen is None and available:
        chosen = available[0]
    if chosen is None or chosen not in available:
        raise click.ClickException(
            "No sound provider configured: set "
            "STORYTELLER_SOUND_<NAME>_API_KEY (or pass --sound-provider)."
        )

    library = SoundLibrary(
        config.get("sound.dir") or "./.storyteller/sounds"
    )
    try:
        provider = registry.get_sound(chosen)
        path, record, created = library.get_or_create(
            provider,
            prompt=prompt,
            name=name or prompt[:12],
            kind=kind,
            description=description,
            tags=[t.strip() for t in tags.split(",") if t.strip()],
            audio_format=audio_format,
        )
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(str(exc))

    if created:
        click.echo("Generated: {}".format(path))
    else:
        click.echo("Cache hit (no API call): {}".format(path))
    click.echo("Name: {}  kind: {}".format(record["name"], record["kind"]))


# ========== list-sounds ==========
@cli.command(name="list-sounds")
@click.argument("query", required=False, default=None)
@click.option(
    "--kind",
    type=click.Choice(["sfx", "ambient", "music"]),
    default=None,
    help="只列出指定类型",
)
@click.option("--sound-dir", default=None, help="音效库目录（默认 <data-dir>/sounds）")
def list_sounds(query, kind, sound_dir):
    """列出音效库中的音效，可按关键字检索。"""
    from ..core.sound_library import SoundLibrary

    config = Config.from_env()
    root = sound_dir or config.get("sound.dir") or "./.storyteller/sounds"
    library = SoundLibrary(root)
    records = library.search(query, kind=kind) if (query or kind) else library.all()
    if not records:
        click.echo("音效库为空或没有匹配项：{}".format(root))
        return
    for record in records:
        click.echo(
            "{}  [{}]  {}  —  {}".format(
                record.get("id"),
                record.get("kind"),
                record.get("name"),
                record.get("description") or record.get("prompt", ""),
            )
        )
        click.echo("    {}".format(library.path_for(record)))


if __name__ == "__main__":
    cli()