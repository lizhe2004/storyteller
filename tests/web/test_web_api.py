from fastapi.testclient import TestClient
import shutil
import subprocess

from storyteller.core.config import Config
from storyteller.web.app import create_app
from storyteller.web.jobs import JobParams


def _app(tmp_path):
    cfg = Config()
    cfg.set("web.passwords", ["pw"])
    cfg.set("web.secret", "test-secret")
    cfg.set("web.rate_limit_per_min", 0)
    cfg.set("project_dir", str(tmp_path / "stories"))
    cfg.set("data_dir", str(tmp_path))
    cfg.set("tts.providers", ["mock"])
    cfg.set("tts.provider_config.mock", {"type": "mock"})
    cfg.set("llm.providers", ["openai"])
    cfg.set("llm.default_provider", "openai")
    cfg.set("llm.provider_config.openai", {
        "type": "openai_compatible", "model": "story-model-a",
        "models": "story-model-b, story-model-c",
    })
    return create_app(cfg)


def test_auth_and_options(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        assert client.get("/api/me").json()["authenticated"] is False
        assert client.post("/api/auth", json={"password": "bad"}).status_code == 401
        assert client.post("/api/auth", json={"password": "pw"}).status_code == 204
        assert client.get("/api/me").json()["authenticated"] is True
        body = client.get("/api/config/options").json()
        assert body["tts_providers"] == [{"name": "mock"}]
        assert body["llm_models"] == [
            {"provider": "openai", "model": "story-model-a", "label": "openai / story-model-a", "is_default": True},
            {"provider": "openai", "model": "story-model-b", "label": "openai / story-model-b", "is_default": False},
            {"provider": "openai", "model": "story-model-c", "label": "openai / story-model-c", "is_default": False},
        ]
        assert body["audio_models"] == []
        assert "api_key" not in str(body)


def test_options_audio_models_include_aliyun_catalog(tmp_path):
    cfg = Config()
    cfg.set("web.passwords", ["pw"])
    cfg.set("web.secret", "test-secret")
    cfg.set("web.rate_limit_per_min", 0)
    cfg.set("data_dir", str(tmp_path))
    cfg.set("tts.providers", ["aliyun"])
    cfg.set("llm.providers", ["openai"])
    cfg.set("llm.default_provider", "openai")
    cfg.set("llm.provider_config.openai", {"type": "mock"})
    app = create_app(cfg)

    with TestClient(app) as client:
        assert client.post("/api/auth", json={"password": "pw"}).status_code == 204
        response = client.get("/api/config/options")
        assert response.status_code == 200
        aliyun_models = {
            item["model"]
            for item in response.json()["audio_models"]
            if item["provider"] == "aliyun"
        }
        assert aliyun_models == {
            "qwen-audio-3.0-tts-plus",
            "qwen-audio-3.0-tts-flash",
            "qwen-audio-3.1-tts-flash",
        }


def test_options_audio_models_accept_string_catalog_records(tmp_path, monkeypatch):
    # Older/generated catalogs may expose model names directly instead of
    # voice-record dictionaries; the options endpoint must not return 500.
    import storyteller.web.routes_options as routes_options

    monkeypatch.setattr(
        routes_options,
        "load_voice_catalog",
        lambda: ["qwen-audio-3.0-tts-plus", "qwen-audio-3.1-tts-flash"],
    )
    cfg = Config()
    cfg.set("web.passwords", ["pw"])
    cfg.set("web.secret", "test-secret")
    cfg.set("web.rate_limit_per_min", 0)
    cfg.set("data_dir", str(tmp_path))
    cfg.set("tts.providers", ["aliyun"])
    cfg.set("llm.providers", ["openai"])
    cfg.set("llm.default_provider", "openai")
    cfg.set("llm.provider_config.openai", {"type": "mock"})

    with TestClient(create_app(cfg)) as client:
        assert client.post("/api/auth", json={"password": "pw"}).status_code == 204
        response = client.get("/api/config/options")

    assert response.status_code == 200
    assert response.json()["audio_models"] == [
        {
            "provider": "aliyun",
            "model": "qwen-audio-3.0-tts-plus",
            "label": "aliyun / qwen-audio-3.0-tts-plus",
        },
        {
            "provider": "aliyun",
            "model": "qwen-audio-3.1-tts-flash",
            "label": "aliyun / qwen-audio-3.1-tts-flash",
        },
    ]


def test_options_audio_models_respect_aliyun_whitelist(tmp_path):
    # 后台勾选了模型时，下拉严格等于勾选集合，不再并入整个目录。
    cfg = Config()
    cfg.set("web.passwords", ["pw"])
    cfg.set("web.secret", "test-secret")
    cfg.set("web.rate_limit_per_min", 0)
    cfg.set("data_dir", str(tmp_path))
    cfg.set("tts.providers", ["aliyun"])
    cfg.set(
        "tts.provider_config.aliyun",
        {"models": "qwen-audio-3.0-tts-plus, qwen-audio-3.1-tts-flash"},
    )
    cfg.set("llm.providers", ["openai"])
    cfg.set("llm.default_provider", "openai")
    cfg.set("llm.provider_config.openai", {"type": "mock"})
    app = create_app(cfg)

    with TestClient(app) as client:
        assert client.post("/api/auth", json={"password": "pw"}).status_code == 204
        aliyun_models = {
            item["model"]
            for item in client.get("/api/config/options").json()["audio_models"]
            if item["provider"] == "aliyun"
        }
        assert aliyun_models == {
            "qwen-audio-3.0-tts-plus",
            "qwen-audio-3.1-tts-flash",
        }


def test_first_run_setup_is_one_time_and_persisted(tmp_path):
    cfg = Config()
    cfg.set("data_dir", str(tmp_path))
    cfg.set("web.rate_limit_per_min", 0)
    app = create_app(cfg)
    setup_code = app.state.setup_code
    assert setup_code

    with TestClient(app) as client:
        assert client.get("/api/auth/status").json() == {
            "setup_required": True, "setup_available": True
        }
        assert client.post("/api/auth", json={"password": "unused"}).status_code == 409
        assert client.post("/api/auth/setup", json={
            "code": "wrong", "password": "a sufficiently long password"
        }).status_code == 401
        assert client.post("/api/auth/setup", json={
            "code": setup_code, "password": "1234567"
        }).status_code == 422
        response = client.post("/api/auth/setup", json={
            "code": setup_code, "password": "12345678"
        })
        assert response.status_code == 204
        assert client.get("/api/auth/status").json() == {
            "setup_required": False, "setup_available": False
        }
        assert client.get("/api/me").json()["authenticated"] is True
        assert client.post("/api/auth/setup", json={
            "code": setup_code, "password": "another sufficiently long password"
        }).status_code == 409

    import json
    persisted = json.loads((tmp_path / "config" / "settings.json").read_text())
    stored_password = persisted["web"]["passwords"][0]
    assert stored_password.startswith("pbkdf2_sha256$")
    assert "12345678" not in stored_password

    restarted = create_app(cfg)
    assert restarted.state.setup_code is None
    with TestClient(restarted) as client:
        assert client.get("/api/auth/status").json() == {
            "setup_required": False, "setup_available": False
        }
        assert client.post("/api/auth", json={
            "password": "12345678"
        }).status_code == 204


def test_static_javascript_assets_share_the_assets_directory(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        worklet = client.get("/assets/pcm-ring-buffer-worklet.js")
        assert worklet.status_code == 200
        assert "javascript" in worklet.headers["content-type"]
        assert "registerProcessor('pcm-ring-buffer'" in worklet.text

        old_worklet_path = client.get("/pcm-ring-buffer-worklet.js")
        assert old_worklet_path.status_code == 404

        missing_asset = client.get("/missing-worklet.js")
        assert missing_asset.status_code == 404

        spa_route = client.get("/stories")
        assert spa_route.status_code == 200
        assert "text/html" in spa_route.headers["content-type"]


def test_native_audio_job_streams_mp3_from_pcm_queue(tmp_path):
    if not shutil.which("ffmpeg"):
        import pytest
        pytest.skip("ffmpeg is required for native MP3 streaming")
    app = _app(tmp_path)
    job = app.state.jobs.create(JobParams(topic="native stream", audio_mode="native_mp3"))
    job.emit_bytes(b"\x01\x00" * 24000)
    job.emit({"type": "complete"})

    with TestClient(app) as client:
        client.cookies.set("storyteller_session", app.state.issuer.issue())
        response = client.get(f"/api/streaming-jobs/{job.id}/audio")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.headers["cache-control"] == "no-store"
    assert response.content
    decoded = subprocess.run(
        [shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-i",
         "pipe:0", "-f", "null", "-"], input=response.content,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    assert decoded.returncode == 0, decoded.stderr.decode("utf-8", errors="replace")
