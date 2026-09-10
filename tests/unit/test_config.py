import os

import pytest

from storyteller.core.config import Config


def test_config_defaults():
    config = Config()
    assert config.get("log_level") == "info"
    assert config.get("output_dir") == "./outputs"
    assert config.get("project_dir") == "./projects"


def test_config_get_nested():
    config = Config()
    config.set("a.b.c", "value")
    assert config.get("a.b.c") == "value"


def test_config_get_missing_returns_default():
    config = Config()
    assert config.get("nonexistent", "fallback") == "fallback"
    assert config.get("a.b.missing") is None


def test_config_set_overwrites():
    config = Config()
    config.set("log_level", "debug")
    assert config.get("log_level") == "debug"


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("STORYTELLER_LOG_LEVEL", "debug")
    monkeypatch.setenv("STORYTELLER_OUTPUT_DIR", "/tmp/out")
    monkeypatch.setenv("STORYTELLER_LLM_DEFAULT_PROVIDER", "test-llm")
    config = Config.from_env()
    assert config.get("log_level") == "debug"
    assert config.get("output_dir") == "/tmp/out"
    assert config.get("llm.default_provider") == "test-llm"


def test_config_loads_llm_providers(monkeypatch):
    monkeypatch.setenv("STORYTELLER_LLM_PROVIDERS", "volcengine,openai")
    monkeypatch.setenv("STORYTELLER_LLM_VOLCENGINE_API_KEY", "key123")
    monkeypatch.setenv("STORYTELLER_LLM_VOLCENGINE_MODEL", "doubao")
    config = Config.from_env()
    assert config.get("llm.providers") == ["volcengine", "openai"]
    provider_cfg = config.get("llm.provider_config.volcengine")
    assert provider_cfg["api_key"] == "key123"
    assert provider_cfg["model"] == "doubao"


def test_config_loads_tts_providers(monkeypatch):
    monkeypatch.setenv("STORYTELLER_TTS_PROVIDERS", "volcengine")
    monkeypatch.setenv("STORYTELLER_TTS_DEFAULT_PROVIDER", "volcengine")
    monkeypatch.setenv("STORYTELLER_TTS_VOLCENGINE_API_KEY", "ttskey")
    config = Config.from_env()
    assert config.get("tts.default_provider") == "volcengine"
    assert config.get("tts.provider_config.volcengine.api_key") == "ttskey"


def test_config_loads_openai_compatible_provider(monkeypatch):
    monkeypatch.setenv(
        "STORYTELLER_TTS_OPENAI_COMPATIBLE_CUSTOM_NAME",
        "my-custom-tts",
    )
    monkeypatch.setenv(
        "STORYTELLER_TTS_OPENAI_COMPATIBLE_CUSTOM_API_KEY",
        "customkey",
    )
    monkeypatch.setenv(
        "STORYTELLER_TTS_OPENAI_COMPATIBLE_CUSTOM_BASE_URL",
        "https://custom.example.com/v1",
    )
    config = Config.from_env()
    providers = config.get("tts.providers")
    assert "my-custom-tts" in providers
    custom = config.get("tts.provider_config.my-custom-tts")
    assert custom["type"] == "openai_compatible"
    assert custom["api_key"] == "customkey"
    assert custom["base_url"] == "https://custom.example.com/v1"


def test_config_from_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "STORYTELLER_LOG_LEVEL=warning\n"
        "STORYTELLER_PROJECT_DIR=/tmp/projects\n"
    )
    # Ensure no stray env vars override the file
    monkeypatch.delenv("STORYTELLER_LOG_LEVEL", raising=False)
    config = Config.from_env(str(env_file))
    assert config.get("log_level") == "warning"
    assert config.get("project_dir") == "/tmp/projects"


def test_config_loads_dotenv_from_cwd(tmp_path, monkeypatch):
    """A .env in the current working directory must be discovered."""
    (tmp_path / ".env").write_text(
        "STORYTELLER_TTS_PROVIDERS=mock\n"
        "STORYTELLER_TTS_MOCK_TYPE=mock\n"
        "STORYTELLER_TTS_DEFAULT_PROVIDER=mock\n"
    )
    monkeypatch.chdir(tmp_path)
    # Make sure no inherited env var masks the file
    monkeypatch.delenv("STORYTELLER_TTS_PROVIDERS", raising=False)
    config = Config.from_env()
    assert config.get("tts.providers") == ["mock"]
    assert config.get("tts.provider_config.mock.type") == "mock"
