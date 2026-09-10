import os
from pathlib import Path
from typing import Any, Optional

from dotenv import find_dotenv, load_dotenv


class Config:
    """Hierarchical configuration manager backed by a nested dict."""

    DEFAULTS = {
        "log_level": "info",
        "output_dir": "./outputs",
        "project_dir": "./projects",
        "output_format": "mp3",
        "progress_level": "simple",
        "strict_mode": False,
        "llm": {
            "providers": [],
            "default_provider": None,
            "provider_config": {},
        },
        "tts": {
            "providers": [],
            "default_provider": None,
            "provider_config": {},
        },
    }

    def __init__(self):
        self._config = self._deep_copy(self.DEFAULTS)

    @staticmethod
    def _deep_copy(obj):
        if isinstance(obj, dict):
            return {k: Config._deep_copy(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [Config._deep_copy(v) for v in obj]
        return obj

    @classmethod
    def from_env(cls, env_file=None):
        """Load configuration from a .env file (optional) and environment.

        The .env file is searched starting from the current working
        directory (where the CLI is invoked), not the package location.
        """
        if env_file:
            load_dotenv(env_file)
        else:
            # usecwd=True makes dotenv walk up from the shell's CWD.
            load_dotenv(find_dotenv(usecwd=True))

        config = cls()

        # Global settings
        config.set("log_level", os.getenv("STORYTELLER_LOG_LEVEL", "info"))
        config.set(
            "output_dir", os.getenv("STORYTELLER_OUTPUT_DIR", "./outputs")
        )
        config.set(
            "project_dir", os.getenv("STORYTELLER_PROJECT_DIR", "./projects")
        )

        cls._load_provider_group(config, "llm")
        cls._load_provider_group(config, "tts")
        cls._load_openai_compatible_tts(config)

        return config

    @staticmethod
    def _load_provider_group(config, kind):
        """Load the provider list, default provider, and per-provider config."""
        providers_env = os.getenv(
            "STORYTELLER_{}_PROVIDERS".format(kind.upper()), ""
        )
        providers = [p.strip() for p in providers_env.split(",") if p.strip()]
        config.set("{}.providers".format(kind), providers)

        default = os.getenv(
            "STORYTELLER_{}_DEFAULT_PROVIDER".format(kind.upper())
        )
        config.set("{}.default_provider".format(kind), default)

        for provider in providers:
            prefix = "STORYTELLER_{}_{}_".format(kind.upper(), provider.upper())
            provider_config = {}
            for key in ("type", "api_key", "model", "endpoint", "base_url"):
                value = os.getenv(prefix + key.upper())
                if value:
                    provider_config[key] = value
            if provider_config:
                config.set(
                    "{}.provider_config.{}".format(kind, provider),
                    provider_config,
                )

    @staticmethod
    def _load_openai_compatible_tts(config):
        """Register OpenAI-compatible TTS providers declared via numbered envs."""
        marker = "STORYTELLER_TTS_OPENAI_COMPATIBLE_"
        for env_key, env_value in os.environ.items():
            if not env_key.startswith(marker) or not env_key.endswith("_NAME"):
                continue
            suffix = env_key[len(marker):-len("_NAME")]
            provider_name = env_value
            provider_config = {"type": "openai_compatible"}
            for sub_key in ("API_KEY", "BASE_URL", "MODEL"):
                value = os.getenv("{}{}_{}".format(marker, suffix, sub_key))
                if value:
                    provider_config[sub_key.lower()] = value

            providers = config.get("tts.providers", [])
            if provider_name not in providers:
                providers.append(provider_name)
                config.set("tts.providers", providers)
            config.set(
                "tts.provider_config.{}".format(provider_name), provider_config
            )

    def get(self, key, default=None):
        """Get a value by dot-separated path; returns default if missing."""
        current = self._config
        for part in key.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    def set(self, key, value):
        """Set a value by dot-separated path, creating intermediate dicts."""
        parts = key.split(".")
        current = self._config
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
