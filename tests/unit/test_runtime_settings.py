import json

import pytest

from storyteller.core.config import Config
from storyteller.core.runtime_settings import RuntimeSettingsStore


def _env_config():
    config = Config()
    config.set("web.host", "env.example.test")
    config.set("web.secret", "environment-secret")
    config.set("llm.default_provider", "env-llm")
    config.set("llm.provider_config.env-llm.api_key", "env-api-key")
    return config


def test_saved_settings_override_environment_values(tmp_path):
    settings_path = tmp_path / "config" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps({"web": {"host": "admin.example.test"}}),
        encoding="utf-8",
    )

    store = RuntimeSettingsStore(tmp_path, _env_config())

    assert store.snapshot().to_config().get("web.host") == "admin.example.test"
    assert store.public_snapshot()["sources"]["web"]["host"] == "admin"


def test_fields_without_saved_override_keep_environment_values(tmp_path):
    store = RuntimeSettingsStore(tmp_path, _env_config())

    config = store.update({"web": {"port": 9001}}).to_config()

    assert config.get("llm.default_provider") == "env-llm"
    assert config.get("web.host") == "env.example.test"


def test_fields_without_environment_or_saved_value_keep_defaults(tmp_path):
    store = RuntimeSettingsStore(tmp_path, Config())

    config = store.snapshot().to_config()

    assert config.get("web.port") == 8000
    assert config.get("sound.enabled") is False
    assert store.public_snapshot()["sources"]["web"]["port"] == "default"


def test_public_snapshot_redacts_all_sensitive_values(tmp_path):
    store = RuntimeSettingsStore(tmp_path, _env_config())
    store.update(
        {
            "web": {
                "passwords": ["first-password", "second-password"],
                "secret": "admin-web-secret",
            },
            "tts": {
                "provider_config": {
                    "voice": {"api_key": "admin-tts-api-key"}
                }
            },
        }
    )

    public = store.public_snapshot()
    rendered = json.dumps(public, ensure_ascii=False)

    for secret in (
        "first-password",
        "second-password",
        "admin-web-secret",
        "admin-tts-api-key",
        "environment-secret",
        "env-api-key",
    ):
        assert secret not in rendered
    assert public["web"]["secret"] == {
        "configured": True,
        "masked": "********cret",
    }
    assert public["web"]["passwords"] == {
        "configured": True,
        "count": 2,
        "masked": "********",
    }
    assert public["tts"]["provider_config"]["voice"]["api_key"] == {
        "configured": True,
        "masked": "********-key",
    }


def test_empty_sensitive_update_preserves_value_until_explicit_reset(tmp_path):
    store = RuntimeSettingsStore(tmp_path, _env_config())
    store.update(
        {
            "web": {"secret": "saved-secret"},
            "llm": {
                "provider_config": {
                    "env-llm": {"api_key": "saved-api-key"}
                }
            },
        }
    )

    snapshot = store.update(
        {
            "web": {"secret": ""},
            "llm": {
                "provider_config": {"env-llm": {"api_key": None}}
            },
        }
    )

    assert snapshot.to_config().get("web.secret") == "saved-secret"
    assert (
        snapshot.to_config().get("llm.provider_config.env-llm.api_key")
        == "saved-api-key"
    )

    reset = store.reset(
        ["web.secret", "llm.provider_config.env-llm.api_key"]
    ).to_config()
    assert reset.get("web.secret") == "environment-secret"
    assert reset.get("llm.provider_config.env-llm.api_key") == "env-api-key"
    persisted = json.loads(
        (tmp_path / "config" / "settings.json").read_text(encoding="utf-8")
    )
    assert "secret" not in persisted.get("web", {})
    assert "api_key" not in (
        persisted.get("llm", {})
        .get("provider_config", {})
        .get("env-llm", {})
    )


def test_failed_atomic_replace_keeps_previous_file_and_snapshot(
    tmp_path, monkeypatch
):
    store = RuntimeSettingsStore(tmp_path, _env_config())
    store.update({"web": {"port": 9001}})
    settings_path = tmp_path / "config" / "settings.json"
    original = settings_path.read_bytes()

    def fail_replace(source, destination):
        assert source != destination
        assert source.exists()
        raise OSError("replace failed")

    monkeypatch.setattr(
        "storyteller.core.runtime_settings.os.replace", fail_replace
    )

    with pytest.raises(OSError, match="replace failed"):
        store.update({"web": {"port": 9002}})

    assert settings_path.read_bytes() == original
    assert store.snapshot().to_config().get("web.port") == 9001
    assert list(settings_path.parent.glob(".settings-*.tmp")) == []


def test_corrupt_settings_fall_back_to_environment_with_config_error(tmp_path):
    settings_path = tmp_path / "config" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text('{"web":', encoding="utf-8")

    store = RuntimeSettingsStore(tmp_path, _env_config())

    assert store.snapshot().to_config().get("web.host") == "env.example.test"
    public = store.public_snapshot()
    assert public["config_error"]
    assert "settings.json" in public["config_error"]


def test_update_rejects_unknown_top_level_group_without_writing(tmp_path):
    store = RuntimeSettingsStore(tmp_path, _env_config())

    with pytest.raises(ValueError, match="top-level"):
        store.update({"database": {"url": "example"}})

    assert not (tmp_path / "config" / "settings.json").exists()
