from fastapi.testclient import TestClient

from storyteller.core.config import Config
from storyteller.web.app import create_app


def _app(tmp_path):
    cfg = Config()
    cfg.set("web.passwords", ["pw"])
    cfg.set("web.secret", "test-secret")
    cfg.set("web.rate_limit_per_min", 0)
    cfg.set("project_dir", str(tmp_path / "stories"))
    cfg.set("tts.providers", ["mock"])
    cfg.set("tts.provider_config.mock", {"type": "mock"})
    return create_app(cfg)


def test_auth_and_options(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        assert client.get("/api/me").json()["authenticated"] is False
        assert client.post("/api/auth", json={"password": "bad"}).status_code == 401
        assert client.post("/api/auth", json={"password": "pw"}).status_code == 204
        assert client.get("/api/me").json()["authenticated"] is True
        body = client.get("/api/config/options").json()
        assert body["tts_providers"] == [{"name": "mock"}]
        assert "api_key" not in str(body)


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
