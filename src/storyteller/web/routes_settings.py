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
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

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
    "type", "api_key", "model", "endpoint", "base_url", "resource_id"
}
_DIRECT_FIELDS = {
    "web": {
        "passwords", "secret", "token_ttl_days", "concurrency",
        "rate_limit_per_min", "filler_voice",
    },
    "llm": {"providers", "default_provider"},
    "tts": {"providers", "default_provider"},
    "sound": {"enabled", "dir", "providers", "default_provider"},
}


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderConfigPatch(_StrictModel):
    type: Optional[StrictStr] = None
    api_key: Optional[StrictStr] = None
    model: Optional[StrictStr] = None
    endpoint: Optional[StrictStr] = None
    base_url: Optional[StrictStr] = None
    resource_id: Optional[StrictStr] = None


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


class TTSSettingsPatch(_StrictModel):
    providers: Optional[List[StrictStr]] = None
    default_provider: Optional[StrictStr] = None
    provider_config: Optional[Dict[StrictStr, ProviderConfigPatch]] = None


class SoundSettingsPatch(ProviderGroupPatch):
    enabled: Optional[StrictBool] = None
    dir: Optional[StrictStr] = None


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
        "settings": request.app.state.runtime_settings.public_snapshot(),
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
    return request.app.state.runtime_settings.public_snapshot()


@router.patch("")
def patch_settings(body: SettingsPatch, request: Request):
    before = request.app.state.runtime_settings.snapshot()
    patch = body.model_dump(exclude_unset=True)
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
