from fastapi import FastAPI

from .auth import RateLimiter, TokenIssuer
from .jobs import JobManager
from .routes_auth import router as auth_router
from .routes_options import router as options_router


def create_app(config, registry=None):
    if registry is None:
        from ..providers.registry import ProviderRegistry
        from ..providers.bootstrap import register_providers_from_config
        registry = ProviderRegistry(config)
        register_providers_from_config(config, registry)
    app = FastAPI(title="storyteller web")
    app.state.config = config
    app.state.registry = registry
    app.state.issuer = TokenIssuer(config.get("web.secret"), config.get("web.token_ttl_days"))
    app.state.limiter = RateLimiter(config.get("web.rate_limit_per_min"))
    app.state.jobs = JobManager(config.get("web.concurrency"))
    app.state.job_viewers = {}
    app.include_router(auth_router)
    app.include_router(options_router)
    from .routes_stories import router as stories_router
    from .routes_ws import router as ws_router
    app.include_router(stories_router)
    app.include_router(ws_router)
    static = __import__("pathlib").Path(__file__).parent / "static"
    if static.is_dir():
        from fastapi.staticfiles import StaticFiles
        assets = static / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")
        app.mount("/", StaticFiles(directory=str(static), html=True), name="spa")
    return app
