from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import (
    BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr,
    field_validator,
)

from ..providers.bootstrap import register_providers_from_config
from ..providers.registry import ProviderRegistry
from .auth import require_login


logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/settings", dependencies=[Depends(require_login)]
)
_HISTORY_LOCK = threading.RLock()
_HISTORY_LIMIT = 100
_PROVIDER_FIELDS = {
    "type", "api_key", "model", "models", "endpoint", "base_url",
    "resource_id", "workspace_id"
}
_DIRECT_FIELDS = {
    "web": {
        "passwords", "secret", "token_ttl_days", "concurrency",
        "rate_limit_per_min", "filler_voice",
    },
    "llm": {"providers", "default_provider"},
    "tts": {"providers", "default_provider"},
    "sound": {"enabled", "dir", "providers"},
}
_PROVIDER_FORM_TYPES = {
    "llm": {
        "volcengine": {
            "label": "火山引擎方舟",
            "fields": ["api_key", "model"],
        },
        "openai_compatible": {
            "label": "OpenAI 兼容服务",
            "fields": ["api_key", "model", "base_url"],
        },
        "mock": {"label": "模拟服务", "fields": []},
    },
    "tts": {
        "aliyun": {
            "label": "阿里云百炼",
            "fields": ["api_key", "models", "workspace_id"],
        },
        "volcengine": {
            "label": "火山引擎语音",
            "fields": ["api_key", "resource_id"],
        },
        "openai_compatible": {
            "label": "OpenAI 兼容服务",
            "fields": ["api_key", "model", "base_url"],
        },
        "mock": {"label": "模拟服务", "fields": []},
    },
    "sound": {
        "volcengine": {
            "label": "火山引擎音效",
            "fields": ["api_key", "model"],
        },
        "mock": {"label": "模拟服务", "fields": []},
    },
}
_CUSTOM_PROVIDER_TYPES = {
    "llm": ["openai_compatible", "mock"],
    "tts": ["volcengine", "aliyun", "openai_compatible", "mock"],
    "sound": ["mock"],
}
_FIXED_PROVIDER_NAMES = {
    "llm": [],
    "tts": ["aliyun", "volcengine"],
    "sound": ["volcengine"],
}


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderConfigPatch(_StrictModel):
    type: Optional[StrictStr] = None
    api_key: Optional[StrictStr] = None
    model: Optional[StrictStr] = None
    models: Optional[StrictStr] = None
    endpoint: Optional[StrictStr] = None
    base_url: Optional[StrictStr] = None
    resource_id: Optional[StrictStr] = None
    workspace_id: Optional[StrictStr] = None


class WebSettingsPatch(_StrictModel):
    passwords: Optional[List[StrictStr]] = None
    secret: Optional[StrictStr] = None
    token_ttl_days: Optional[StrictInt] = None
    concurrency: Optional[StrictInt] = None
    rate_limit_per_min: Optional[StrictInt] = None
    filler_voice: Optional[StrictStr] = None


class ProviderGroupPatch(_StrictModel):
    providers: Optional[List[StrictStr]] = None
    default_provider: Optional[StrictStr] = None
    provider_config: Optional[Dict[StrictStr, ProviderConfigPatch]] = None

    @field_validator("providers")
    @classmethod
    def llm_requires_exactly_one_provider(cls, value):
        if value is not None and len(value) != 1:
            raise ValueError("LLM settings require exactly one provider")
        return value


class TTSSettingsPatch(_StrictModel):
    providers: Optional[List[StrictStr]] = None
    default_provider: Optional[StrictStr] = None
    provider_config: Optional[Dict[StrictStr, ProviderConfigPatch]] = None

    @field_validator("default_provider")
    @classmethod
    def tts_default_is_not_configurable(cls, value):
        if value is not None:
            raise ValueError("TTS providers form a voice pool; no default is used")
        return value


class SoundSettingsPatch(_StrictModel):
    providers: Optional[List[StrictStr]] = None
    provider_config: Optional[Dict[StrictStr, ProviderConfigPatch]] = None
    enabled: Optional[StrictBool] = None
    dir: Optional[StrictStr] = None

    @field_validator("providers")
    @classmethod
    def sound_has_at_most_one_provider(cls, value):
        if value is not None and len(value) > 1:
            raise ValueError("Sound settings support one provider")
        return value


class SettingsPatch(_StrictModel):
    web: Optional[WebSettingsPatch] = None
    llm: Optional[ProviderGroupPatch] = None
    tts: Optional[TTSSettingsPatch] = None
    sound: Optional[SoundSettingsPatch] = None


class ResetRequest(_StrictModel):
    paths: List[StrictStr]


class ProviderTestRequest(_StrictModel):
    provider: StrictStr
    config: ProviderConfigPatch = Field(default_factory=ProviderConfigPatch)
    timeout_seconds: float = Field(default=10.0, gt=0, le=30, strict=True)
    voice_id: Optional[StrictStr] = None


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _resolved_provider_form_type(group, name, provider_config):
    provider_type = provider_config.get("type")
    normalized_name = name.lower()
    if group == "llm":
        if provider_type in ("openai_compatible", "mock"):
            return provider_type
        return "volcengine" if normalized_name == "volcengine" else None
    if group == "tts":
        if normalized_name in ("aliyun", "volcengine"):
            return normalized_name
        if provider_type in ("aliyun", "volcengine", "openai_compatible", "mock"):
            return provider_type
        # Provider bootstrap defaults untyped/unknown TTS names to Volcengine.
        return "volcengine"
    if group == "sound":
        if provider_type == "mock":
            return "mock"
        if normalized_name == "volcengine" and provider_type in (None, "volcengine"):
            return "volcengine"
    return None


def _provider_schemas(public_settings):
    schemas = {}
    for group, types in _PROVIDER_FORM_TYPES.items():
        config_group = public_settings[group]
        provider_types = {}
        for name in config_group.get("providers", []):
            provider_config = config_group.get("provider_config", {}).get(name, {})
            provider_types[name] = _resolved_provider_form_type(
                group, name, provider_config
            )
        schemas[group] = {
            "types": types,
            "providers": provider_types,
            "custom_types": _CUSTOM_PROVIDER_TYPES[group],
            "fixed_names": _FIXED_PROVIDER_NAMES[group],
        }
    return schemas


def _public_settings(request):
    settings = request.app.state.runtime_settings.public_snapshot()
    settings["provider_schemas"] = _provider_schemas(settings)
    return settings


def _history_path(request: Request):
    data_dir = request.app.state.config.get("data_dir") or ".storyteller"
    return Path(data_dir) / "config" / "history.json"


def _read_history(path: Path):
    if not path.is_file():
        return []
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return values if isinstance(values, list) else []


def _write_history(path: Path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, name = tempfile.mkstemp(
        prefix=".history-", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                values[-_HISTORY_LIMIT:], handle, ensure_ascii=False,
                indent=2, sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _append_history(request: Request, operation: str, changed_paths):
    entry = {
        "version": uuid.uuid4().hex,
        "updated_at": _utc_now(),
        "operation": operation,
        "changed_paths": sorted(changed_paths),
    }
    path = _history_path(request)
    with _HISTORY_LOCK:
        history = _read_history(path)
        history.append(entry)
        _write_history(path, history)
    return entry


def _changed_paths(before, after, prefix=()):
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        changed = []
        for key in sorted(set(before) | set(after)):
            path = prefix + (key,)
            if key not in before or key not in after:
                changed.append(".".join(path))
            else:
                changed.extend(_changed_paths(before[key], after[key], path))
        return changed
    return [] if before == after else [".".join(prefix)]


def _mutation_response(request, entry):
    return {
        "version": entry["version"],
        "updated_at": entry["updated_at"],
        "effective_for": "new_jobs",
        "message": "保存成功；配置对新任务生效，运行中任务不受影响",
        "settings": _public_settings(request),
    }


def _valid_reset_path(path):
    parts = path.split(".")
    if len(parts) == 2:
        return parts[0] in _DIRECT_FIELDS and parts[1] in _DIRECT_FIELDS[parts[0]]
    return (
        len(parts) == 4
        and parts[0] in {"llm", "tts", "sound"}
        and parts[1] == "provider_config"
        and bool(parts[2])
        and parts[3] in _PROVIDER_FIELDS
    )


def _temporary_config(request: Request, kind: str, body: ProviderTestRequest):
    config = request.app.state.runtime_settings.snapshot().to_config()
    name = body.provider
    current = config.get("{}.provider_config.{}".format(kind, name), {}) or {}
    temporary = body.config.model_dump(exclude_unset=True)
    if temporary.get("api_key") in (None, ""):
        temporary.pop("api_key", None)
    merged = dict(current)
    merged.update(temporary)
    config.set("{}.provider_config.{}".format(kind, name), merged)
    providers = list(config.get("{}.providers".format(kind), []) or [])
    if name not in providers:
        providers.append(name)
        config.set("{}.providers".format(kind), providers)
    return config


def _run_provider_test(kind, config, body):
    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)
    if kind == "llm":
        provider = registry.get_llm(body.provider)
        provider.chat(
            [{"role": "user", "content": "Reply with OK."}],
            temperature=0,
            max_tokens=4,
        )
        return

    provider = registry.get_tts(body.provider)
    voices = provider.list_voices()
    if body.voice_id:
        voice = next(
            (item for item in voices if item.voice_id == body.voice_id), None
        )
        if voice is None:
            raise ValueError("unknown voice")
    else:
        voice = voices[0] if voices else None
    if voice is None:
        raise ValueError("provider has no voices")
    fd, name = tempfile.mkstemp(prefix="storyteller-tts-test-", suffix=".wav")
    os.close(fd)
    output_path = Path(name)
    try:
        provider.synthesize("连接测试", voice, output_path)
    finally:
        try:
            output_path.unlink()
        except FileNotFoundError:
            pass


async def _test_connection(request, kind, body):
    config = _temporary_config(request, kind, body)
    loop = asyncio.get_running_loop()
    call = partial(_run_provider_test, kind, config, body)
    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, call), timeout=body.timeout_seconds
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="连接测试超时")
    except Exception as exc:
        logger.warning(
            "provider connection test failed: kind=%s provider=%s error_type=%s",
            kind, body.provider, type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="连接测试失败，请检查供应商配置和网络连接",
        )
    return {"ok": True, "provider": body.provider, "message": "连接成功"}


@router.get("")
def get_settings(request: Request):
    return _public_settings(request)


@router.patch("")
def patch_settings(body: SettingsPatch, request: Request):
    before = request.app.state.runtime_settings.snapshot()
    patch = body.model_dump(exclude_unset=True)
    sound_patch = patch.get("sound")
    if sound_patch is not None:
        current_sound = before.values.get("sound", {})
        sound_enabled = sound_patch.get(
            "enabled", current_sound.get("enabled", False)
        )
        sound_providers = sound_patch.get(
            "providers", current_sound.get("providers", [])
        )
        if sound_enabled and not sound_providers:
            raise HTTPException(
                status_code=422,
                detail="启用音效时必须配置一个服务",
            )
    after = request.app.state.runtime_settings.update(patch)
    request.app.state.refresh_runtime_config()
    entry = _append_history(
        request, "update", _changed_paths(before.values, after.values)
    )
    return _mutation_response(request, entry)


@router.post("/reset")
def reset_settings(body: ResetRequest, request: Request):
    invalid = [path for path in body.paths if not _valid_reset_path(path)]
    if invalid:
        raise HTTPException(status_code=422, detail="包含不可重置的配置路径")
    before = request.app.state.runtime_settings.snapshot()
    after = request.app.state.runtime_settings.reset(body.paths)
    request.app.state.refresh_runtime_config()
    entry = _append_history(
        request, "reset", _changed_paths(before.values, after.values)
    )
    return _mutation_response(request, entry)


@router.post("/test/llm")
async def test_llm(body: ProviderTestRequest, request: Request):
    return await _test_connection(request, "llm", body)


@router.post("/test/tts")
async def test_tts(body: ProviderTestRequest, request: Request):
    return await _test_connection(request, "tts", body)


@router.get("/history")
def get_history(request: Request):
    with _HISTORY_LOCK:
        history = _read_history(_history_path(request))
    return {"history": list(reversed(history[-_HISTORY_LIMIT:]))}
