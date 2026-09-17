import click


@click.command("web")
@click.option("--host", default=None)
@click.option("--port", default=None, type=int)
def web_command(host, port):
    from ..core.config import Config
    cfg = Config.from_env()
    try:
        import uvicorn
    except ImportError:
        raise click.ClickException('缺少 web 依赖，请运行 pip install -e ".[web]"')
    try:
        from .app import create_app
    except ImportError:
        raise click.ClickException(
            '缺少 web 依赖，请运行 pip install -e ".[web]"')
    uvicorn.Server(uvicorn.Config(
        create_app(cfg), host=host or cfg.get("web.host"),
        port=port or cfg.get("web.port"))).run()
