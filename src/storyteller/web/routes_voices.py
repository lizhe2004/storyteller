from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from ..core.models import normalize_voice_ages
from ..core.voice_overrides import voice_key
from .auth import require_login


router = APIRouter(prefix="/api/voices", dependencies=[Depends(require_login)])


def _catalog(request):
    return request.app.state.voice_catalog


@router.get("")
def list_voices(
    request: Request,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    return _catalog(request).filter_voices(provider, model, gender, age, page, page_size)


@router.patch("/{voice_key}")
async def update_voice_age(voice_key: str, request: Request):
    catalog = _catalog(request)
    try:
        current = next(item for item in catalog.list_voices() if item["key"] == voice_key)
    except StopIteration:
        raise HTTPException(404, "音色不存在")
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, "请求体必须是 JSON")
    ages = payload.get("age") if isinstance(payload, dict) else None
    if not isinstance(ages, list) or any(not isinstance(age, str) for age in ages):
        raise HTTPException(400, "age 必须是年龄枚举数组")
    normalized = normalize_voice_ages(ages)
    if len(normalized) != len(ages):
        raise HTTPException(400, "包含无效年龄")
    request.app.state.registry.voice_overrides.set_age(voice_key, normalized)
    updated = next(item for item in catalog.list_voices() if item["key"] == voice_key)
    return updated


@router.get("/{voice_key}/clips")
def list_voice_clips(voice_key: str, request: Request):
    try:
        return {"clips": _catalog(request).clips_for_voice(voice_key)}
    except KeyError:
        raise HTTPException(404, "音色不存在")


@router.get("/{voice_key}/clips/{clip_id}/audio")
def voice_clip_audio(voice_key: str, clip_id: str, request: Request):
    try:
        path = _catalog(request).resolve_clip_audio(voice_key, clip_id)
    except KeyError:
        raise HTTPException(404, "音色不存在")
    if path is None:
        raise HTTPException(404, "音频片段不存在")
    return FileResponse(str(Path(path)), media_type="audio/mpeg")
