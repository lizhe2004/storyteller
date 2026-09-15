import os
from pathlib import Path
from typing import Any, Optional

from dotenv import find_dotenv, load_dotenv


class Config:
    """Hierarchical configuration manager backed by a nested dict."""

    DEFAULTS = {
        "log_level": "info",
        # Single root for every generated artifact. Per-story files live under
        # <data_dir>/stories/<project_id>/; the shared sound library under
        # <data_dir>/sounds/. The three specific dirs below override this
        # individually when explicitly configured (env or CLI).
        "data_dir": "./.storyteller",
        "output_dir": None,
        "project_dir": None,
        "output_format": "mp3",
        "progress_level": "simple",
        "strict_mode": False,
        "voice_matcher": "llm",
        "llm": {
            "providers": [],
            "default_provider": None,
            "provider_config": {},
        },
        "tts": {
            "providers": [],
            "provider_config": {},
            "scheduler": {
                "default_max_concurrent_sessions": 1,
                "default_max_text_chunks_per_second": None,
                "default_queue_size": 16,
                "default_queue_timeout_seconds": 5.0,
                "limits": {},
                "provider_limits": {},
            },
        },
        "sound": {
            "enabled": False,
            "dir": None,
            "providers": [],
            "default_provider": None,
            "provider_config": {},
        },
        "web": {
            "passwords": [],
            "secret": None,
            "token_ttl_days": 30,
            "host": "127.0.0.1",
            "port": 8000,
            "concurrency": 2,
            "rate_limit_per_min": 10,
            "filler_voice": None,
        },
    }

    def __init__(self):
        self._config = self._deep_copy(self.DEFAULTS)

    @classmethod
    def from_dict(cls, values):
        """Build a config from an isolated copy of nested values."""
        if not isinstance(values, dict):
            raise TypeError("config values must be a dict")
        config = cls()
        config._config = cls._deep_copy(values)
        return config

    def to_dict(self):
        """Return an isolated copy of the raw configuration values."""
        return self._deep_copy(self._config)

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
        data_dir = os.getenv("STORYTELLER_DATA_DIR")
        if data_dir:
            config.set("data_dir", data_dir)
        # Explicit per-location overrides win over the derived defaults.
        if os.getenv("STORYTELLER_OUTPUT_DIR"):
            config.set(
                "output_dir", os.getenv("STORYTELLER_OUTPUT_DIR")
            )
        if os.getenv("STORYTELLER_PROJECT_DIR"):
            config.set(
                "project_dir", os.getenv("STORYTELLER_PROJECT_DIR")
            )
        config.set(
            "voice_matcher",
            os.getenv("STORYTELLER_VOICE_MATCHER", "llm"),
        )

        cls._load_provider_group(config, "llm")
        cls._load_provider_group(config, "tts")
        cls._load_tts_scheduler(config)
        cls._load_openai_compatible_tts(config)
        cls._load_provider_group(config, "sound")
        cls._load_sound(config)
        cls._load_web(config)

        # Artifact dirs are derived lazily in get() from data_dir, so an
        # explicit --data-dir / STORYTELLER_DATA_DIR stays authoritative.
        return config

    @staticmethod
    def _load_web(config):
        raw = os.getenv("STORYTELLER_WEB_PASSWORDS", "")
        config.set("web.passwords", [p.strip() for p in raw.split(",") if p.strip()])
        config.set("web.secret", os.getenv("STORYTELLER_WEB_SECRET") or None)
        config.set("web.filler_voice", os.getenv("STORYTELLER_WEB_FILLER_VOICE") or None)
        for env_key, cfg_key, default in (
            ("STORYTELLER_WEB_TOKEN_TTL_DAYS", "web.token_ttl_days", 30),
            ("STORYTELLER_WEB_PORT", "web.port", 8000),
            ("STORYTELLER_WEB_CONCURRENCY", "web.concurrency", 2),
            ("STORYTELLER_WEB_RATE_LIMIT_PER_MIN", "web.rate_limit_per_min", 10),
        ):
            value = os.getenv(env_key)
            config.set(cfg_key, int(value) if value else default)
        config.set("web.host", os.getenv("STORYTELLER_WEB_HOST", "127.0.0.1"))

    def resolve_paths(self):
        """Materialize the artifact directories from the single data root.

        Normally directories are derived lazily in :meth:`get`, so changing
        ``data_dir`` later just works. This method exists for callers that
        want the resolved values stored explicitly. Locations configured
        explicitly (env/CLI) are never overwritten.
        """
        for key, parts in (
            ("project_dir", ("stories",)),
            ("output_dir", ("stories",)),
            ("sound.dir", ("sounds",)),
        ):
            if not self._raw_get(key):
                self.set(key, self._derive(*parts))

    def _derive(self, *parts):
        import os

        return os.path.join(self.get("data_dir") or "./.storyteller", *parts)

    @staticmethod
    def _load_sound(config):
        enabled = os.getenv("STORYTELLER_SOUND_ENABLED", "").strip().lower()
        if enabled in ("1", "true", "yes", "on"):
            config.set("sound.enabled", True)
        sound_dir = os.getenv("STORYTELLER_SOUND_DIR")
        if sound_dir:
            config.set("sound.dir", sound_dir)

    # Per-provider config keys shared by the llm/tts/sound groups.
    _PROVIDER_CONFIG_KEYS = (
        "type", "api_key", "model", "endpoint", "base_url", "resource_id",
        "models",
    )

    @staticmethod
    def _load_provider_group(config, kind):
        """Load one provider group (llm/tts/sound).

        Names in STORYTELLER_<KIND>_PROVIDERS come first (default enablement
        and ordering). Any other name with a per-provider env var is
        auto-discovered and appended in sorted order, so configuring a key
        is enough to make a provider CLI-selectable without editing the
        PROVIDERS list.
        """
        upper = kind.upper()
        group_prefix = "STORYTELLER_{}_".format(upper)

        providers_env = os.getenv(group_prefix + "PROVIDERS", "")
        providers = [p.strip() for p in providers_env.split(",") if p.strip()]

        if kind != "tts":
            config.set(
                "{}.default_provider".format(kind),
                os.getenv(group_prefix + "DEFAULT_PROVIDER"),
            )

        # The suffix allowlist alone excludes reserved names (PROVIDERS,
        # DEFAULT_PROVIDER, ENABLED, DIR all lack a recognised suffix).
        discovered = set()
        for env_key in os.environ:
            if not env_key.startswith(group_prefix):
                continue
            rest = env_key[len(group_prefix):]
            if kind == "tts" and rest.startswith("OPENAI_COMPATIBLE"):
                continue
            parts = rest.split("_", 1)
            if len(parts) != 2:
                continue
            name, suffix = parts
            if not name or suffix.lower() not in Config._PROVIDER_CONFIG_KEYS:
                continue
            discovered.add(name.lower())

        seen = {p.lower() for p in providers}
        for name in sorted(discovered):
            if name not in seen:
                providers.append(name)
                seen.add(name)
        config.set("{}.providers".format(kind), providers)

        for provider in providers:
            provider_prefix = "STORYTELLER_{}_{}_".format(
                upper, provider.upper()
            )
            provider_config = {}
            for key in Config._PROVIDER_CONFIG_KEYS:
                value = os.getenv(provider_prefix + key.upper())
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

    # Realtime TTS scheduler knobs (web streaming only). Each FIELD token below
    # is matched as a whole suffix, so a per-provider env like
    # STORYTELLER_TTS_SCHEDULER_LIMITS_MY_TTS_QUEUE_SIZE parses as provider
    # "my_tts" + field QUEUE_SIZE even when the provider name has underscores.
    _SCHEDULER_FIELDS = (
        ("MAX_CONCURRENT_SESSIONS", "max_concurrent_sessions"),
        ("MAX_TEXT_CHUNKS_PER_SECOND", "max_text_chunks_per_second"),
        ("QUEUE_SIZE", "queue_size"),
        ("QUEUE_TIMEOUT_SECONDS", "queue_timeout_seconds"),
    )

    @staticmethod
    def _coerce_scheduler(raw, field):
        try:
            if field == "max_text_chunks_per_second":
                # Blank/0/negative means "no rate limit".
                value = float(raw)
                return value if value > 0 else None
            if field in ("max_concurrent_sessions", "queue_size"):
                return int(raw)
            return float(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _load_tts_scheduler(config):
        for suffix, field in Config._SCHEDULER_FIELDS:
            raw = os.getenv("STORYTELLER_TTS_SCHEDULER_" + suffix)
            if raw is None or raw.strip() == "":
                continue
            value = Config._coerce_scheduler(raw, field)
            if value is not None:
                config.set("tts.scheduler.default_" + field, value)

        prefix = "STORYTELLER_TTS_SCHEDULER_LIMITS_"
        for env_key, raw in os.environ.items():
            if not env_key.startswith(prefix) or not raw:
                continue
            body = env_key[len(prefix):]
            for suffix, field in Config._SCHEDULER_FIELDS:
                token = "_" + suffix
                if not body.endswith(token):
                    continue
                provider = body[:-len(token)].lower()
                value = Config._coerce_scheduler(raw, field)
                if provider and value is not None:
                    key = "tts.scheduler.provider_limits." + provider
                    overrides = config.get(key) or {}
                    overrides[field] = value
                    config.set(key, overrides)
                break

    # Keys derived from data_dir when left unset (None). An explicitly set
    # value always wins; None means "follow the data root".
    _DERIVED_DIRS = {
        "project_dir": ("stories",),
        "output_dir": ("stories",),
        "sound.dir": ("sounds",),
    }

    def get(self, key, default=None):
        """Get a value by dot-separated path; derives dirs from data_dir."""
        if key in self._DERIVED_DIRS:
            value = self._raw_get(key)
            if value:
                return value
            return self._derive(*self._DERIVED_DIRS[key])
        return self._raw_get(key, default)

    def _raw_get(self, key, default=None):
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
