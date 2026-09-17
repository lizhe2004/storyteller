from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from ..core.runtime_settings import RuntimeSettingsStore
from .auth import RateLimiter, TokenIssuer
from .jobs import JobManager
from .routes_auth import router as auth_router
from .routes_options import router as options_router
from .routes_settings import router as settings_router


def create_app(config, registry=None):
    runtime_settings = RuntimeSettingsStore(config.get("data_dir"), config)
    runtime_config = runtime_settings.snapshot().to_config()
    if registry is None:
        from ..providers.registry import ProviderRegistry
        from ..providers.bootstrap import register_providers_from_config
        registry = ProviderRegistry(runtime_config)
        register_providers_from_config(runtime_config, registry)
    app = FastAPI(title="storyteller web")
    app.state.config = runtime_config
    app.state.runtime_settings = runtime_settings
    app.state.registry = registry
    app.state.issuer = TokenIssuer(runtime_config.get("web.secret"), runtime_config.get("web.token_ttl_days"))
    app.state.limiter = RateLimiter(runtime_config.get("web.rate_limit_per_min"))
    app.state.jobs = JobManager(
        runtime_config.get("web.concurrency"),
        config_snapshot_provider=runtime_settings.snapshot,
    )

    def refresh_runtime_config():
        current = runtime_settings.snapshot().to_config()
        app.state.config = current
        app.state.issuer = TokenIssuer(
            current.get("web.secret"), current.get("web.token_ttl_days")
        )
        app.state.limiter.reconfigure(current.get("web.rate_limit_per_min"))
        app.state.jobs.reconfigure(current.get("web.concurrency"))
        if registry is None:
            from ..providers.registry import ProviderRegistry
            from ..providers.bootstrap import register_providers_from_config
            refreshed = ProviderRegistry(current)
            register_providers_from_config(current, refreshed)
            app.state.registry = refreshed
        return current

    app.state.refresh_runtime_config = refresh_runtime_config
    app.state.job_viewers = {}
    app.state.voice_analysis = __import__("storyteller.web.voice_analysis", fromlist=["VoiceAnalysisManager"]).VoiceAnalysisManager(
        __import__("pathlib").Path(runtime_config.get("data_dir") or ".storyteller") / "voice-analysis",
        __import__("pathlib").Path(runtime_config.get("data_dir") or ".storyteller") / "stories",
    )
    app.include_router(auth_router)
    app.include_router(options_router)
    app.include_router(settings_router)
    from .routes_stories import router as stories_router
    from .routes_ws import router as ws_router
    from .routes_voice_analysis import router as voice_analysis_router, ws_router as voice_analysis_ws_router
    app.include_router(stories_router)
    app.include_router(ws_router)
    app.include_router(voice_analysis_router)
    app.include_router(voice_analysis_ws_router)
    static = __import__("pathlib").Path(__file__).parent / "static"
    if static.is_dir():
        from fastapi.staticfiles import StaticFiles
        assets = static / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")
        @app.get("/{path:path}")
        async def spa_fallback(path: str):
            # Root-level public files (for example the AudioWorklet module)
            # must be served as files instead of falling through to index.html.
            if path:
                root = static.resolve()
                candidate = (static / path).resolve()
                try:
                    candidate.relative_to(root)
                except ValueError:
                    raise HTTPException(status_code=404)
                if candidate.is_file():
                    return FileResponse(str(candidate))
                # Returning index.html for a missing script hides deployment
                # mistakes behind a confusing strict-MIME module error.
                if candidate.suffix:
                    raise HTTPException(status_code=404)
            # Vue Router uses history mode; extensionless routes load the SPA
            # shell so direct links and browser refreshes continue to work.
            return FileResponse(str(static / "index.html"))
        app.mount("/", StaticFiles(directory=str(static), html=True), name="spa")
    return app
