from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket

from ..core.tts import STREAM_CHANNELS, STREAM_SAMPLE_RATE
from ..core.observability import server_time
from .auth import SESSION_COOKIE
from .jobs import JobParams
from .streaming import StreamOrchestrator

router = APIRouter()
TERMINAL = {"complete", "error", "canceled"}


def _ready(job):
    return {"type": "ready", "job_id": job.id,
            "playback_mode": job.params.audio_mode,
            "server_time": server_time(),
            "audio": {"encoding": "pcm_s16le",
                      "sample_rate": STREAM_SAMPLE_RATE, "channels": STREAM_CHANNELS}}


async def _receive_loop(ws, inbox):
    try:
        while True:
            await inbox.put(await ws.receive_json())
    except Exception:
        await inbox.put({"_closed": True})


async def _job_get(job):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, job.queue.get)


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    state = ws.app.state
    token = ws.query_params.get("token") or ws.cookies.get(SESSION_COOKIE)
    if not state.issuer.verify(token):
        await ws.close(code=1008); return
    host = ws.client.host if ws.client else "?"
    if not state.limiter.allow(host):
        await ws.close(code=1013); return
    await ws.accept()
    inbox = asyncio.Queue()
    receiver = asyncio.create_task(_receive_loop(ws, inbox))
    job = None
    try:
        job_id = ws.query_params.get("job_id")
        if job_id:
            job = state.jobs.get(job_id)
            if job is None:
                await ws.close(code=4404); return
            for event in (_ready(job), {"type": "status", "phase": job.phase,
                         "message": "已重连", "index": job.line_index,
                         "total": job.total}, job.script_preview,
                         job.characters_matched, job.script_ready,
                         job.terminal_event):
                if event is not None:
                    await ws.send_json(event)
                    if event.get("type") in TERMINAL:
                        return
        else:
            first = await asyncio.wait_for(inbox.get(), timeout=120)
            if first.get("type") != "start":
                await ws.close(code=1003); return
            job = state.jobs.create(JobParams(
                topic=first.get("topic", ""), length=first.get("length", "medium"),
                complexity=first.get("complexity", "simple"),
                with_sound=bool(first.get("with_sound", False)),
                tts_providers=first.get("tts_providers"),
                audio_mode=("native_mp3" if first.get("audio_mode") == "native_mp3" else "webaudio")))
            await ws.send_json(_ready(job))
            state.jobs.submit(job, lambda j: StreamOrchestrator(
                state.config, registry=state.registry).run(j))
        old = state.job_viewers.get(job.id)
        state.job_viewers[job.id] = ws
        if old is not None and old is not ws:
            try:
                await old.close(code=1012)
            except Exception:
                pass
        while True:
            job_task = asyncio.create_task(_job_get(job))
            input_task = asyncio.create_task(inbox.get())
            done, pending = await asyncio.wait(
                (job_task, input_task), return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            if state.job_viewers.get(job.id) is not ws:
                return
            if input_task in done:
                message = input_task.result()
                if message.get("type") == "cancel":
                    state.jobs.cancel(job.id)
                if message.get("_closed"):
                    return
            if job_task in done:
                item = job_task.result()
                if "_bytes" in item:
                    await ws.send_bytes(item["_bytes"])
                else:
                    await ws.send_json(item)
                    if item.get("type") in TERMINAL:
                        return
    finally:
        receiver.cancel()
        if job is not None and state.job_viewers.get(job.id) is ws:
            del state.job_viewers[job.id]
