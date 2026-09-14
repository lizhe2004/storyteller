from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse

from ..providers.gemini import GeminiAudioAnalyzer
from .auth import SESSION_COOKIE
from .voice_analysis import VoiceAnalysisManager

router = APIRouter(prefix="/api/voice-analysis")
ws_router = APIRouter()


def _manager(request):
    return request.app.state.voice_analysis


def _catalog(request):
    result = {}
    for provider in request.app.state.registry.list_tts_names():
        for voice in request.app.state.registry.list_tts_voices([provider]):
            result["{}:{}".format(voice.provider, voice.voice_id)] = {
                "provider": voice.provider, "voice_id": voice.voice_id,
                "name": voice.name, "gender": voice.gender, "age": voice.age,
                "category": voice.category, "description": voice.description,
                "model": getattr(voice, "model", None), "tags": getattr(voice, "tags", []),
            }
    return result


@router.get("/jobs")
def list_jobs(request: Request):
    return {"jobs": _manager(request).list_jobs()}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    job = _manager(request).get_job(job_id)
    if job is None:
        raise HTTPException(404, "分析任务不存在")
    return job.detail()


@router.get("/jobs/{job_id}/samples/{sample_id}/audio")
def sample_audio(job_id: str, sample_id: str, request: Request):
    job = _manager(request).get_job(job_id)
    if job is None:
        raise HTTPException(404, "分析任务不存在")
    for sample in job.detail().get("samples", []):
        if sample.get("sample_id") == sample_id:
            path = Path(sample.get("audio_path", ""))
            if path.is_file():
                return FileResponse(str(path), media_type="audio/mpeg")
            raise HTTPException(404, "样本音频不存在")
    raise HTTPException(404, "分析样本不存在")


@router.post("/jobs")
async def create_job(request: Request):
    options = await request.json()
    manager = _manager(request)
    job = manager.create_job(options)
    data_dir = Path(request.app.state.config.get("data_dir") or ".storyteller")
    analyzer = GeminiAudioAnalyzer(model_sample=job.manifest["model_sample"], model_summary=job.manifest["model_summary"])
    manager.submit(job.job_id, data_dir / "stories", _catalog(request), analyzer)
    return job.snapshot()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request):
    job = _manager(request).get_job(job_id)
    if job is None:
        raise HTTPException(404, "分析任务不存在")
    job.manifest.update({"status": "canceled", "phase": "canceled"})
    job.save()
    return job.snapshot()


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: str, request: Request):
    job = _manager(request).get_job(job_id)
    if job is None:
        raise HTTPException(404, "分析任务不存在")
    data_dir = Path(request.app.state.config.get("data_dir") or ".storyteller")
    analyzer = GeminiAudioAnalyzer(model_sample=job.manifest["model_sample"], model_summary=job.manifest["model_summary"])
    _manager(request).submit(job_id, data_dir / "stories", _catalog(request), analyzer)
    return job.snapshot()


@router.post("/jobs/{job_id}/suggestions/{suggestion_id}/approve")
def approve_suggestion(job_id: str, suggestion_id: str, request: Request):
    try:
        suggestion = _manager(request).update_suggestion(job_id, suggestion_id, "approved")
    except KeyError:
        raise HTTPException(404, "分析任务不存在")
    if suggestion is None:
        raise HTTPException(404, "修改建议不存在")
    return suggestion


@router.post("/jobs/{job_id}/suggestions/{suggestion_id}/reject")
def reject_suggestion(job_id: str, suggestion_id: str, request: Request):
    try:
        suggestion = _manager(request).update_suggestion(job_id, suggestion_id, "rejected")
    except KeyError:
        raise HTTPException(404, "分析任务不存在")
    if suggestion is None:
        raise HTTPException(404, "修改建议不存在")
    return suggestion


@ws_router.websocket("/ws/voice-analysis")
async def voice_analysis_ws(ws: WebSocket):
    state = ws.app.state
    token = ws.query_params.get("token") or ws.cookies.get(SESSION_COOKIE)
    if not state.issuer.verify(token):
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        message = await asyncio.wait_for(ws.receive_json(), timeout=30)
        job_ids = message.get("job_ids", []) if message.get("type") == "subscribe" else []
        await ws.send_json({"type": "ready", "job_ids": job_ids})
        while job_ids:
            snapshots = []
            for job_id in job_ids:
                job = state.voice_analysis.get_job(job_id)
                if job:
                    snapshot = job.snapshot()
                    snapshots.append(snapshot)
                    await ws.send_json({"type": "progress", "job_id": job_id, **snapshot})
            if snapshots and all(s.get("status") in {"completed", "failed", "canceled"} for s in snapshots):
                return
            await asyncio.sleep(1)
    except Exception:
        return
