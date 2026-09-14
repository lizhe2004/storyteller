"""Runtime configuration overlays backed by an atomically written JSON file."""

import json
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple

from storyteller.core.config import Config


_GROUPS = ("web", "llm", "tts", "sound")
_SENSITIVE_NAMES = {
    "api_key",
    "apikey",
    "password",
    "passwords",
    "secret",
    "web_secret",
    "access_password",
}
_SKIP = object()


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _deep_merge(base: Dict[str, Any], overlay: Mapping[str, Any]) -> Dict[str, Any]:
    result = Config._deep_copy(base)
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = _thaw(value)
    return result


def _path_exists(values: Mapping[str, Any], path: Tuple[str, ...]) -> bool:
    current: Any = values
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    return True


def _value_at(values: Mapping[str, Any], path: Tuple[str, ...]) -> Any:
    current: Any = values
    for part in path:
        current = current[part]
    return current


def _is_sensitive(path: Tuple[str, ...]) -> bool:
    if not path:
        return False
    normalized = path[-1].lower().replace("-", "_")
    return normalized in _SENSITIVE_NAMES


def _without_empty_sensitive(
    value: Any, path: Tuple[str, ...] = ()
) -> Any:
    if _is_sensitive(path) and value in (None, "", []):
        return _SKIP
    if not isinstance(value, dict):
        return Config._deep_copy(value)
    result = {}
    for key, item in value.items():
        filtered = _without_empty_sensitive(item, path + (key,))
        if filtered is not _SKIP:
            result[key] = filtered
    return result


def _remove_path(values: Dict[str, Any], path: Tuple[str, ...]) -> bool:
    if not path or path[0] not in values:
        return False
    if len(path) == 1:
        del values[path[0]]
        return True
    child = values.get(path[0])
    if not isinstance(child, dict):
        return False
    removed = _remove_path(child, path[1:])
    if removed and not child:
        del values[path[0]]
    return removed


def _mask(value: Any) -> Dict[str, Any]:
    if isinstance(value, (list, tuple)):
        return {
            "configured": bool(value),
            "count": len(value),
            "masked": "********" if value else None,
        }
    configured = value not in (None, "")
    if not configured:
        return {"configured": False, "masked": None}
    text = str(value)
    suffix = text[-4:] if len(text) > 4 else ""
    return {"configured": True, "masked": "********" + suffix}


def _redact(value: Any, path: Tuple[str, ...] = ()) -> Any:
    if _is_sensitive(path):
        return _mask(value)
    if isinstance(value, Mapping):
        return {
            key: _redact(item, path + (key,))
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [_redact(item, path) for item in value]
    return value


def _source_tree(
    values: Mapping[str, Any],
    overrides: Mapping[str, Any],
    defaults: Mapping[str, Any],
    path: Tuple[str, ...] = (),
) -> Any:
    if isinstance(values, Mapping):
        return {
            key: _source_tree(item, overrides, defaults, path + (key,))
            for key, item in values.items()
        }
    if _path_exists(overrides, path):
        return "admin"
    if not _path_exists(defaults, path):
        return "environment"
    return "default" if _value_at(defaults, path) == values else "environment"


@dataclass(frozen=True)
class RuntimeSettingsSnapshot:
    """An immutable point-in-time view of merged runtime settings."""

    values: Mapping[str, Any]
    sources: Mapping[str, Any]
    config_error: Optional[str] = None

    def to_config(self) -> Config:
        """Return a mutable Config isolated from this snapshot."""
        return Config.from_dict(_thaw(self.values))


class RuntimeSettingsStore:
    """Load and persist administrator overrides for runtime configuration."""

    def __init__(self, data_dir: Any, env_config: Config):
        if not isinstance(env_config, Config):
            raise TypeError("env_config must be a Config")
        self._settings_path = Path(data_dir) / "config" / "settings.json"
        self._base_values = env_config.to_dict()
        self._lock = threading.RLock()
        self._overrides, self._config_error = self._load()
        self._snapshot = self._build_snapshot()

    def snapshot(self) -> RuntimeSettingsSnapshot:
        with self._lock:
            return self._snapshot

    def public_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            snapshot = self._snapshot
            result = {
                group: _redact(snapshot.values[group], (group,))
                for group in _GROUPS
            }
            result["sources"] = _thaw(snapshot.sources)
            result["config_error"] = snapshot.config_error
            return result

    def update(self, patch: dict) -> RuntimeSettingsSnapshot:
        self._validate(patch)
        filtered = _without_empty_sensitive(patch)
        with self._lock:
            overrides = _deep_merge(self._overrides, filtered)
            self._write(overrides)
            self._overrides = overrides
            self._config_error = None
            self._snapshot = self._build_snapshot()
            return self._snapshot

    def reset(self, paths: List[str]) -> RuntimeSettingsSnapshot:
        if not isinstance(paths, list):
            raise TypeError("paths must be a list")
        parsed = []
        for path in paths:
            if not isinstance(path, str) or not path or ".." in path:
                raise ValueError("reset paths must be non-empty dotted strings")
            parts = tuple(path.split("."))
            if parts[0] not in _GROUPS:
                raise ValueError("reset path must start with a settings group")
            parsed.append(parts)

        with self._lock:
            overrides = Config._deep_copy(self._overrides)
            for parts in parsed:
                _remove_path(overrides, parts)
            self._write(overrides)
            self._overrides = overrides
            self._config_error = None
            self._snapshot = self._build_snapshot()
            return self._snapshot

    def _load(self) -> Tuple[Dict[str, Any], Optional[str]]:
        if not self._settings_path.exists():
            return {}, None
        try:
            with self._settings_path.open("r", encoding="utf-8") as handle:
                values = json.load(handle)
            self._validate(values)
            return values, None
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            error = "Unable to load {}: {}".format(
                self._settings_path.name, exc
            )
            return {}, error

    @staticmethod
    def _validate(values: Any) -> None:
        if not isinstance(values, dict):
            raise TypeError("settings patch must be a dict")
        unknown = sorted(set(values) - set(_GROUPS))
        if unknown:
            raise ValueError(
                "unknown top-level settings group: {}".format(", ".join(unknown))
            )
        for group, value in values.items():
            if not isinstance(value, dict):
                raise TypeError("settings group {} must be a dict".format(group))
        try:
            json.dumps(values, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("settings values must be valid JSON") from exc

    def _build_snapshot(self) -> RuntimeSettingsSnapshot:
        merged = _deep_merge(self._base_values, self._overrides)
        default_values = Config().to_dict()
        grouped_values = {group: merged[group] for group in _GROUPS}
        grouped_overrides = {
            group: self._overrides[group]
            for group in _GROUPS
            if group in self._overrides
        }
        grouped_defaults = {
            group: default_values[group] for group in _GROUPS
        }
        sources = _source_tree(
            grouped_values, grouped_overrides, grouped_defaults
        )
        return RuntimeSettingsSnapshot(
            values=_freeze(merged),
            sources=_freeze(sources),
            config_error=self._config_error,
        )

    def _write(self, values: Dict[str, Any]) -> None:
        directory = self._settings_path.parent
        directory.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=".settings-", suffix=".tmp", dir=str(directory)
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    values,
                    handle,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._settings_path)
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
