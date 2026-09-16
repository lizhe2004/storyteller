import os

import pytest

from storyteller.core.config import Config


def test_config_defaults():
    config = Config()
    assert config.get("log_level") == "info"
    assert config.get("data_dir") == "./.storyteller"
    # All artifact dirs are derived from the single data root.
    assert config.get("project_dir") == "./.storyteller/stories"
    assert config.get("output_dir") == "./.storyteller/stories"
    assert config.get("sound.dir") == "./.storyteller/sounds"


def test_tts_scheduler_defaults_and_model_override_are_configurable():
    """Removing scheduler defaults or model-specific nesting must break lookup."""
    config = Config()
    assert config.get("tts.scheduler.default_max_concurrent_sessions") == 1
    assert config.get("tts.scheduler.default_max_text_chunks_per_second") is None
    assert config.get("tts.scheduler.default_queue_size") == 16
    assert config.get("tts.scheduler.default_queue_timeout_seconds") is None

    config.set(
        "tts.scheduler.limits.aliyun.qwen-plus",
        {"max_concurrent_sessions": 3, "queue_size": 4},
    )
    assert config.get(
        "tts.scheduler.limits.aliyun.qwen-plus.max_concurrent_sessions"
    ) == 3
    assert config.get("tts.scheduler.limits.aliyun.qwen-plus.queue_size") == 4


def test_tts_scheduler_defaults_from_env(monkeypatch):
    monkeypatch.setenv("STORYTELLER_TTS_SCHEDULER_MAX_CONCURRENT_SESSIONS", "3")
    monkeypatch.setenv("STORYTELLER_TTS_SCHEDULER_MAX_TEXT_CHUNKS_PER_SECOND", "2.5")
    monkeypatch.setenv("STORYTELLER_TTS_SCHEDULER_QUEUE_SIZE", "32")
    monkeypatch.setenv("STORYTELLER_TTS_SCHEDULER_QUEUE_TIMEOUT_SECONDS", "8")
    config = Config.from_env()
    assert config.get("tts.scheduler.default_max_concurrent_sessions") == 3
    assert config.get("tts.scheduler.default_max_text_chunks_per_second") == 2.5
    assert config.get("tts.scheduler.default_queue_size") == 32
    assert config.get("tts.scheduler.default_queue_timeout_seconds") == 8.0


def test_tts_scheduler_blank_qps_stays_unlimited(monkeypatch):
    monkeypatch.delenv(
        "STORYTELLER_TTS_SCHEDULER_MAX_TEXT_CHUNKS_PER_SECOND", raising=False
    )
    config = Config.from_env()
    assert config.get("tts.scheduler.default_max_text_chunks_per_second") is None


def test_tts_scheduler_provider_limits_from_env(monkeypatch):
    monkeypatch.setenv(
        "STORYTELLER_TTS_SCHEDULER_LIMITS_ALIYUN_MAX_CONCURRENT_SESSIONS", "2"
    )
    monkeypatch.setenv("STORYTELLER_TTS_SCHEDULER_LIMITS_ALIYUN_QUEUE_SIZE", "8")
    config = Config.from_env()
    assert config.get("tts.scheduler.provider_limits.aliyun") == {
        "max_concurrent_sessions": 2,
        "queue_size": 8,
    }


def test_tts_scheduler_provider_limits_env_tolerates_underscored_provider(monkeypatch):
    monkeypatch.setenv(
        "STORYTELLER_TTS_SCHEDULER_LIMITS_MY_TTS_QUEUE_TIMEOUT_SECONDS", "1.5"
    )
    config = Config.from_env()
    assert config.get(
        "tts.scheduler.provider_limits.my_tts.queue_timeout_seconds"
    ) == 1.5


def test_aliyun_workspace_id_from_env(monkeypatch):
    monkeypatch.setenv(
        "STORYTELLER_TTS_ALIYUN_WORKSPACE_ID", "workspace-123"
    )
    config = Config.from_env()

    assert config.get(
        "tts.provider_config.aliyun.workspace_id"
    ) == "workspace-123"


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
    assert config.get("llm.default_provider") is None


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
    monkeypatch.setenv("STORYTELLER_TTS_VOLCENGINE_API_KEY", "ttskey")
    config = Config.from_env()
    assert config.get("tts.providers") == ["volcengine"]
    assert config.get("tts.provider_config.volcengine.api_key") == "ttskey"


def test_volcengine_endpoint_env_is_not_loaded(monkeypatch):
    monkeypatch.setenv(
        "STORYTELLER_LLM_VOLCENGINE_ENDPOINT", "https://custom.example/llm"
    )
    monkeypatch.setenv(
        "STORYTELLER_TTS_VOLCENGINE_ENDPOINT", "https://custom.example/tts"
    )
    config = Config.from_env()
    assert config.get("llm.provider_config.volcengine.endpoint") is None
    assert config.get("tts.provider_config.volcengine.endpoint") is None


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
    )
    monkeypatch.chdir(tmp_path)
    # Make sure no inherited env var masks the file
    monkeypatch.delenv("STORYTELLER_TTS_PROVIDERS", raising=False)
    config = Config.from_env()
    assert config.get("tts.providers") == ["mock"]
    assert config.get("tts.provider_config.mock.type") == "mock"


def test_tts_provider_auto_discovered_without_providers_list(monkeypatch):
    # Configuring per-provider vars is enough to become selectable;
    # no STORYTELLER_TTS_PROVIDERS edit required.
    monkeypatch.delenv("STORYTELLER_TTS_ALIYUN_TYPE", raising=False)
    monkeypatch.setenv("STORYTELLER_TTS_ALIYUN_API_KEY", "dashscope-key")
    config = Config.from_env()
    assert config.get("tts.providers") == ["aliyun"]
    assert config.get("tts.provider_config.aliyun.type") is None
    assert config.get("tts.provider_config.aliyun.api_key") == "dashscope-key"


def test_explicit_tts_provider_list_excludes_other_configured_providers(monkeypatch):
    """An explicit TTS list is an allowlist, not a display order."""
    monkeypatch.setenv("STORYTELLER_TTS_PROVIDERS", "volcengine")
    monkeypatch.setenv("STORYTELLER_TTS_VOLCENGINE_API_KEY", "vkey")
    monkeypatch.setenv("STORYTELLER_TTS_MOCK_API_KEY", "unused")
    monkeypatch.setenv("STORYTELLER_TTS_ALIYUN_API_KEY", "akey")
    monkeypatch.setenv(
        "STORYTELLER_TTS_OPENAI_COMPATIBLE_CUSTOM_NAME", "custom-tts"
    )
    monkeypatch.setenv(
        "STORYTELLER_TTS_OPENAI_COMPATIBLE_CUSTOM_API_KEY", "custom-key"
    )
    config = Config.from_env()
    assert config.get("tts.providers") == ["volcengine"]
    assert config.get("tts.provider_config.aliyun") is None
    assert config.get("tts.provider_config.mock") is None
    assert config.get("tts.provider_config.custom-tts") is None


def test_llm_auto_discovery_parity(monkeypatch):
    monkeypatch.setenv("STORYTELLER_LLM_VOLCENGINE_API_KEY", "llm-key")
    config = Config.from_env()
    assert config.get("llm.providers") == ["volcengine"]
    assert config.get("llm.provider_config.volcengine.api_key") == "llm-key"


def test_sound_group_loads_providers_default_and_config(monkeypatch):
    monkeypatch.setenv("STORYTELLER_SOUND_PROVIDERS", "volcengine")
    monkeypatch.setenv("STORYTELLER_SOUND_DEFAULT_PROVIDER", "should-be-ignored")
    monkeypatch.setenv("STORYTELLER_SOUND_VOLCENGINE_API_KEY", "sound-key")
    monkeypatch.setenv("STORYTELLER_SOUND_VOLCENGINE_MODEL", "seed-audio-1.0")
    monkeypatch.setenv(
        "STORYTELLER_SOUND_VOLCENGINE_ENDPOINT", "https://should-be-ignored"
    )
    config = Config.from_env()
    assert config.get("sound.providers") == ["volcengine"]
    assert config.get("sound.default_provider") is None
    assert config.get("sound.provider_config.volcengine.api_key") == "sound-key"
    assert config.get("sound.provider_config.volcengine.model") == "seed-audio-1.0"
    assert config.get("sound.provider_config.volcengine.endpoint") is None


def test_sound_reserved_names_are_not_providers(monkeypatch):
    monkeypatch.setenv("STORYTELLER_SOUND_ENABLED", "true")
    monkeypatch.setenv("STORYTELLER_SOUND_DIR", "/tmp/sounds")
    config = Config.from_env()
    assert config.get("sound.providers") == []
    assert config.get("sound.enabled") is True
    assert config.get("sound.dir") == "/tmp/sounds"


def test_legacy_sfx_vars_are_no_longer_read(monkeypatch):
    monkeypatch.setenv("STORYTELLER_SFX_VOLCENGINE_API_KEY", "old-key")
    monkeypatch.setenv("STORYTELLER_SFX_VOLCENGINE_MODEL", "old-model")
    config = Config.from_env()
    assert config.get("sound.providers") == []
    assert config.get("sound.provider_config.volcengine") is None
