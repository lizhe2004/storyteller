import json
import time

import pytest
from fastapi.testclient import TestClient

from storyteller.core.config import Config
from storyteller.providers.mock.llm import MockLLMProvider
from storyteller.providers.mock.tts import MockTTSProvider
from storyteller.web.app import create_app
from storyteller.web.auth import SESSION_COOKIE
from storyteller.web.jobs import JobParams


@pytest.fixture
def settings_app(tmp_path):
    config = Config()
    config.set("data_dir", str(tmp_path))
    config.set("web.passwords", ["login-password"])
    config.set("web.secret", "environment-web-secret")
    config.set("web.rate_limit_per_min", 0)
    config.set("web.host", "environment.example.test")
    config.set("llm.providers", ["mock"])
    config.set("llm.default_provider", "mock")
    config.set(
        "llm.provider_config.mock",
        {"type": "mock", "api_key": "environment-llm-key"},
    )
    config.set("tts.providers", ["mock"])
    config.set(
        "tts.provider_config.mock",
        {"type": "mock", "api_key": "environment-tts-key"},
    )
    return create_app(config)


@pytest.fixture
def client(settings_app):
    with TestClient(settings_app) as test_client:
        test_client.cookies.set(
            SESSION_COOKIE, settings_app.state.issuer.issue()
        )
        yield test_client


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/settings", None),
        ("patch", "/api/settings", {"web": {"port": 9001}}),
        ("post", "/api/settings/test/llm", {"provider": "mock"}),
        ("post", "/api/settings/test/tts", {"provider": "mock"}),
        ("post", "/api/settings/models/llm", {"provider": "mock"}),
        ("post", "/api/settings/models/tts", {"provider": "mock"}),
        ("post", "/api/settings/reset", {"paths": ["web.host"]}),
        ("get", "/api/settings/history", None),
    ],
)
def test_settings_endpoints_require_login(settings_app, method, path, body):
    with TestClient(settings_app) as unauthenticated:
        response = unauthenticated.request(method, path, json=body)

    assert response.status_code == 401


def test_get_settings_returns_groups_sources_and_redacted_secrets(client):
    response = client.get("/api/settings")

    assert response.status_code == 200
    body = response.json()
    assert {"web", "llm", "tts", "sound", "sources"} <= set(body)
    assert body["web"]["host"] == "environment.example.test"
    assert body["sources"]["web"]["host"] == "environment"
    assert body["sources"]["sound"]["enabled"] == "default"
    assert body["web"]["secret"] == {
        "configured": True,
        "masked": "********cret",
    }
    assert body["web"]["passwords"] == {
        "configured": True,
        "count": 1,
        "masked": "********",
    }
    assert body["llm"]["provider_config"]["mock"]["api_key"] == {
        "configured": True,
        "masked": "********-key",
    }
    schemas = body["provider_schemas"]
    assert schemas["llm"]["providers"]["mock"] == "mock"
    assert schemas["llm"]["types"]["openai_compatible"]["fields"] == [
        "api_key", "model", "models", "base_url"
    ]
    assert schemas["tts"]["types"]["aliyun"]["fields"] == [
        "api_key", "models", "workspace_id"
    ]
    assert schemas["tts"]["types"]["volcengine"]["fields"] == [
        "api_key", "resource_id", "models"
    ]
    assert schemas["sound"]["types"]["volcengine"]["fields"] == [
        "api_key", "model"
    ]
    rendered = json.dumps(body, ensure_ascii=False)
    assert "login-password" not in rendered
    assert "environment-web-secret" not in rendered
    assert "environment-llm-key" not in rendered


def test_patch_accepts_whitelisted_partial_update_and_new_jobs_use_it(
    client, settings_app, tmp_path
):
    response = client.patch(
        "/api/settings",
        json={
            "web": {"concurrency": 3},
            "llm": {
                "provider_config": {
                    "mock": {"model": "new-model"}
                }
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["version"]
    assert body["updated_at"].endswith("Z")
    assert body["effective_for"] == "new_jobs"
    assert body["settings"]["web"]["concurrency"] == 3
    persisted = json.loads(
        (tmp_path / "config" / "settings.json").read_text(encoding="utf-8")
    )
    assert persisted["web"]["concurrency"] == 3
    job = settings_app.state.jobs.create(JobParams(topic="new snapshot"))
    assert (
        job.config_snapshot.to_config().get(
            "llm.provider_config.mock.model"
        )
        == "new-model"
    )


def test_provider_schema_tracks_new_openai_compatible_provider(client):
    response = client.patch(
        "/api/settings",
        json={
            "llm": {
                "providers": ["writer"],
                "provider_config": {
                    "writer": {
                        "type": "openai_compatible",
                        "api_key": "writer-key",
                        "base_url": "https://llm.example/v1",
                        "model": "writer-model",
                    }
                },
            }
        },
    )

    assert response.status_code == 200
    schemas = response.json()["settings"]["provider_schemas"]["llm"]
    assert schemas["providers"]["writer"] == "openai_compatible"
    assert schemas["types"][schemas["providers"]["writer"]]["fields"] == [
        "api_key", "model", "models", "base_url"
    ]


def test_provider_schema_resolves_implicit_custom_tts_to_volcengine(client):
    response = client.patch(
        "/api/settings",
        json={
            "tts": {
                "providers": ["custom-voice"],
                "provider_config": {"custom-voice": {"api_key": "voice-key"}},
            }
        },
    )

    assert response.status_code == 200
    schemas = response.json()["settings"]["provider_schemas"]["tts"]
    assert schemas["providers"]["custom-voice"] == "volcengine"


def test_web_settings_update_refreshes_auth_runtime_objects(client, settings_app):
    old_cookie = settings_app.state.issuer.issue()
    response = client.patch(
        "/api/settings",
        json={
            "web": {
                "passwords": ["new-login-password"],
                "secret": "new-web-secret",
                "token_ttl_days": 7,
                "rate_limit_per_min": 3,
            }
        },
    )
    assert response.status_code == 200

    with TestClient(settings_app) as fresh_client:
        assert fresh_client.post(
            "/api/auth", json={"password": "new-login-password"}
        ).status_code == 204
        assert fresh_client.post(
            "/api/auth", json={"password": "login-password"}
        ).status_code == 401

    with TestClient(settings_app) as old_client:
        old_client.cookies.set(SESSION_COOKIE, old_cookie)
        assert old_client.get("/api/me").json() == {"authenticated": False}
    assert settings_app.state.config.get("web.token_ttl_days") == 7
    assert settings_app.state.limiter.per_minute == 3


def test_settings_save_keeps_session_with_ephemeral_secret(tmp_path):
    # Without a configured web.secret the signing key is ephemeral, but a
    # settings save must not rotate it and force re-login.
    config = Config()
    config.set("data_dir", str(tmp_path))
    config.set("web.passwords", ["login-password"])
    config.set("llm.providers", ["mock"])
    config.set("llm.default_provider", "mock")
    config.set("tts.providers", ["mock"])
    app = create_app(config)

    with TestClient(app) as test_client:
        test_client.cookies.set(SESSION_COOKIE, app.state.issuer.issue())
        assert test_client.get("/api/me").json() == {"authenticated": True}

        response = test_client.patch(
            "/api/settings", json={"web": {"token_ttl_days": 7}}
        )
        assert response.status_code == 200

        assert test_client.get("/api/me").json() == {"authenticated": True}


def test_patch_accepts_aliyun_workspace_and_model_allowlist(client, settings_app):
    response = client.patch(
        "/api/settings",
        json={
            "tts": {
                "provider_config": {
                    "mock": {
                        "models": "qwen-audio-3.0-tts-plus",
                        "workspace_id": "workspace-123",
                    }
                }
            }
        },
    )

    assert response.status_code == 200
    persisted = settings_app.state.runtime_settings.snapshot().to_config()
    assert persisted.get("tts.provider_config.mock.models") == (
        "qwen-audio-3.0-tts-plus"
    )
    assert persisted.get("tts.provider_config.mock.workspace_id") == (
        "workspace-123"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"database": {"url": "example"}},
        {"web": {"unknown": "value"}},
        {"llm": {"provider_config": {"mock": {"token": "value"}}}},
        {"sound": {"default_provider": "mock"}},
        {"web": {"port": "9001"}},
        {"sound": {"enabled": "yes"}},
    ],
)
def test_patch_rejects_unknown_fields_and_wrong_types(client, payload):
    response = client.patch("/api/settings", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"llm": {"providers": ["volcengine", "openai"]}},
        {"llm": {"providers": []}},
        {"sound": {"providers": ["volcengine", "mock"]}},
        {"sound": {"enabled": True, "providers": []}},
        {"tts": {"default_provider": "mock"}},
    ],
)
def test_patch_rejects_unsupported_provider_selection_controls(client, payload):
    response = client.patch("/api/settings", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"web": {"host": "admin.example.test"}},
        {"web": {"port": 9001}},
    ],
)
def test_patch_rejects_deployment_managed_web_fields(client, payload):
    response = client.patch("/api/settings", json=payload)

    assert response.status_code == 422


def test_patch_does_not_echo_secret_and_empty_secret_keeps_existing(
    client, settings_app, tmp_path
):
    secret = "admin-full-secret-value"

    first = client.patch(
        "/api/settings",
        json={
            "web": {"secret": secret},
            "llm": {
                "provider_config": {"mock": {"api_key": secret}}
            },
        },
    )
    client.cookies.set(SESSION_COOKIE, settings_app.state.issuer.issue())
    second = client.patch(
        "/api/settings",
        json={
            "web": {"secret": ""},
            "llm": {"provider_config": {"mock": {"api_key": ""}}},
        },
    )

    assert first.status_code == second.status_code == 200
    assert secret not in first.text
    assert secret not in second.text
    persisted = json.loads(
        (tmp_path / "config" / "settings.json").read_text(encoding="utf-8")
    )
    assert persisted["web"]["secret"] == secret
    assert persisted["llm"]["provider_config"]["mock"]["api_key"] == secret


def test_reset_removes_override_and_restores_environment_value(client):
    updated = client.patch(
        "/api/settings",
        json={"web": {"rate_limit_per_min": 99}},
    )
    assert updated.status_code == 200

    response = client.post(
        "/api/settings/reset", json={"paths": ["web.rate_limit_per_min"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["settings"]["web"]["rate_limit_per_min"] == 0
    assert (
        body["settings"]["sources"]["web"]["rate_limit_per_min"]
        == "environment"
    )


@pytest.mark.parametrize("path", ["web.host", "web.port"])
def test_reset_rejects_deployment_managed_web_fields(client, path):
    response = client.post("/api/settings/reset", json={"paths": [path]})

    assert response.status_code == 422


@pytest.mark.parametrize("kind", ["llm", "tts"])
def test_provider_connection_test_succeeds_without_persisting(
    client, tmp_path, kind
):
    settings_path = tmp_path / "config" / "settings.json"
    assert not settings_path.exists()

    response = client.post(
        "/api/settings/test/{}".format(kind),
        json={
            "provider": "mock",
            "config": {"type": "mock", "api_key": "temporary-key"},
            "timeout_seconds": 1.0,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "provider": "mock",
        "message": "连接成功",
    }
    assert not settings_path.exists()
    assert "temporary-key" not in response.text


@pytest.mark.parametrize("kind", ["llm", "tts"])
def test_provider_connection_test_times_out_without_persisting(
    client, tmp_path, monkeypatch, kind
):
    def slow_call(*args, **kwargs):
        time.sleep(0.1)
        return "late"

    target = MockLLMProvider if kind == "llm" else MockTTSProvider
    method = "chat" if kind == "llm" else "synthesize"
    monkeypatch.setattr(target, method, slow_call)

    response = client.post(
        "/api/settings/test/{}".format(kind),
        json={
            "provider": "mock",
            "config": {"type": "mock", "api_key": "timeout-secret"},
            "timeout_seconds": 0.01,
        },
    )

    assert response.status_code == 504
    assert "超时" in response.json()["detail"]
    assert "timeout-secret" not in response.text
    assert not (tmp_path / "config" / "settings.json").exists()


@pytest.mark.parametrize("kind", ["llm", "tts"])
def test_provider_connection_test_sanitizes_provider_errors(
    client, tmp_path, monkeypatch, kind
):
    secret = "provider-error-secret"

    def fail_call(*args, **kwargs):
        raise RuntimeError("upstream rejected {}".format(secret))

    target = MockLLMProvider if kind == "llm" else MockTTSProvider
    method = "chat" if kind == "llm" else "synthesize"
    monkeypatch.setattr(target, method, fail_call)

    response = client.post(
        "/api/settings/test/{}".format(kind),
        json={
            "provider": "mock",
            "config": {"type": "mock", "api_key": secret},
            "timeout_seconds": 1.0,
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "连接测试失败，请检查供应商配置和网络连接"
    assert secret not in response.text


@pytest.mark.parametrize("kind", ["llm", "tts"])
def test_model_fetch_rejects_providers_without_listing(client, kind):
    response = client.post(
        "/api/settings/models/{}".format(kind),
        json={
            "provider": "mock",
            "config": {"type": "mock"},
            "timeout_seconds": 1.0,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "该服务不支持拉取模型列表"


@pytest.mark.parametrize("kind", ["llm", "tts"])
def test_model_fetch_succeeds_without_persisting(
    client, tmp_path, monkeypatch, kind
):
    target = MockLLMProvider if kind == "llm" else MockTTSProvider
    monkeypatch.setattr(
        target, "list_models", lambda self: ["m-b", "m-a"], raising=False
    )

    response = client.post(
        "/api/settings/models/{}".format(kind),
        json={
            "provider": "mock",
            "config": {"type": "mock", "api_key": "fetch-secret"},
            "timeout_seconds": 1.0,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "provider": "mock",
        "models": [
            {"id": "m-b", "retiring": False},
            {"id": "m-a", "retiring": False},
        ],
    }
    assert "fetch-secret" not in response.text
    assert not (tmp_path / "config" / "settings.json").exists()


@pytest.mark.parametrize("kind", ["llm", "tts"])
def test_model_fetch_times_out(client, monkeypatch, kind):
    def slow_list(self):
        time.sleep(0.1)
        return ["late"]

    target = MockLLMProvider if kind == "llm" else MockTTSProvider
    monkeypatch.setattr(target, "list_models", slow_list, raising=False)

    response = client.post(
        "/api/settings/models/{}".format(kind),
        json={
            "provider": "mock",
            "config": {"type": "mock"},
            "timeout_seconds": 0.01,
        },
    )

    assert response.status_code == 504
    assert "超时" in response.json()["detail"]


@pytest.mark.parametrize("kind", ["llm", "tts"])
def test_model_fetch_sanitizes_provider_errors(client, monkeypatch, kind):
    secret = "model-fetch-secret"

    def fail_list(self):
        raise RuntimeError("upstream rejected {}".format(secret))

    target = MockLLMProvider if kind == "llm" else MockTTSProvider
    monkeypatch.setattr(target, "list_models", fail_list, raising=False)

    response = client.post(
        "/api/settings/models/{}".format(kind),
        json={
            "provider": "mock",
            "config": {"type": "mock", "api_key": secret},
            "timeout_seconds": 1.0,
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "拉取模型列表失败，请检查供应商配置和网络连接"
    assert secret not in response.text


def test_history_contains_no_sensitive_values(client, settings_app, tmp_path):
    secret = "never-record-this-secret"
    response = client.patch(
        "/api/settings",
        json={
            "web": {"secret": secret},
            "tts": {
                "provider_config": {"mock": {"api_key": secret}}
            },
        },
    )
    assert response.status_code == 200
    client.cookies.set(SESSION_COOKIE, settings_app.state.issuer.issue())

    history = client.get("/api/settings/history")

    assert history.status_code == 200
    body = history.json()
    assert body["history"][0]["operation"] == "update"
    assert set(body["history"][0]["changed_paths"]) == {
        "web.secret",
        "tts.provider_config.mock.api_key",
    }
    rendered = json.dumps(body, ensure_ascii=False)
    persisted = (tmp_path / "config" / "history.json").read_text(
        encoding="utf-8"
    )
    assert secret not in rendered
    assert secret not in persisted
