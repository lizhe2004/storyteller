from __future__ import annotations

import re
import queue
import shutil
import subprocess
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from ..core.exceptions import ProjectError
from ..core.project import ProjectManager
from .auth import SESSION_COOKIE

router = APIRouter()
LINE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _pm(request):
    return ProjectManager(request.app.state.config.get("project_dir"))


def _auth(request):
    if not request.app.state.issuer.verify(request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(401, "未登录")


def _resolve(request, ref):
    try:
        return _pm(request).resolve_project_dir(ref)
    except ProjectError as exc:
        raise HTTPException(400 if "Ambiguous" in str(exc) else 404, str(exc))


@router.get("/api/stories")
def list_stories(request: Request):
    _auth(request)
    result = []
    for dirname, state in _pm(request).list_project_entries():
        result.append({"id": state.project_id, "dir_name": dirname,
                       "title": state.script.title if state.script else None,
                       "state": state.state,
                       "duration_ms": None,
                       "created_at": state.created_at.isoformat() if state.created_at else None})
    result.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return {"stories": result}


def _line_duration(directory, line_id):
    path = directory / "audio" / (line_id + ".mp3")
    if not path.is_file():
        return None
    try:
        from pydub import AudioSegment
        return len(AudioSegment.from_file(str(path)))
    except Exception:
        return None


@router.get("/api/stories/{ref}")
def story_detail(ref: str, request: Request):
    _auth(request)
    directory = _resolve(request, ref)
    state = _pm(request).load_project(directory.name)
    if not state.script:
        raise HTTPException(404, "剧本尚未生成")
    names = {c.id: c.name for c in state.script.characters}
    return {"id": state.project_id, "title": state.script.title,
            "topic": state.script.topic, "state": state.state,
            "characters": [{"id": c.id, "name": c.name} for c in state.script.characters],
            "lines": [{"line_id": l.line_id, "line_type": l.line_type,
                       "speaker": names.get(l.character_id) or l.line_type,
                       "text": l.text,
                       "duration_ms": _line_duration(directory, l.line_id)}
                      for l in state.script.lines]}


@router.get("/api/stories/{ref}/audio")
def story_audio(ref: str, request: Request):
    _auth(request)
    directory = _resolve(request, ref)
    audio = next((p for p in sorted(directory.glob("story.*"))
                  if p.suffix.lower() in (".mp3", ".wav", ".ogg", ".m4a")), None)
    if not audio:
        raise HTTPException(404, "音频尚未生成")
    return FileResponse(str(audio))


@router.get("/api/streaming-jobs/{job_id}/audio")
def streaming_job_audio(job_id: str, request: Request):
    """Encode the job's ordered PCM frames into one progressive MP3 response."""
    _auth(request)
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "播放任务不存在或已过期")
    if job.params.audio_mode != "native_mp3":
        raise HTTPException(409, "此任务未启用原生音频播放")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise HTTPException(503, "服务器未安装 ffmpeg，无法提供 MP3 实时流")

    def encoded_audio():
        process = subprocess.Popen(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "s16le",
             "-ar", "24000", "-ac", "1", "-i", "pipe:0", "-vn",
             "-codec:a", "libmp3lame", "-b:a", "64k", "-flush_packets", "1",
             "-f", "mp3", "pipe:1"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        stop_writer = threading.Event()

        def write_pcm():
            try:
                assert process.stdin is not None
                while not stop_writer.is_set():
                    try:
                        pcm = job.audio_queue.get(timeout=0.25)
                    except queue.Empty:
                        if job.audio_stream_closed:
                            break
                        continue
                    if pcm is None:
                        break
                    process.stdin.write(pcm)
                    process.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            finally:
                try:
                    process.stdin.close()
                except (BrokenPipeError, OSError, ValueError):
                    pass

        writer = threading.Thread(target=write_pcm, name="storyteller-mp3-stream", daemon=True)
        writer.start()
        try:
            assert process.stdout is not None
            while True:
                chunk = process.stdout.read(4096)
                if not chunk:
                    break
                yield chunk
            writer.join(timeout=1)
        finally:
            stop_writer.set()
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=3)
            process.stdout.close()

    return StreamingResponse(
        encoded_audio(), media_type="audio/mpeg",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/api/stories/{ref}/segments/{segment}")
def story_segment(ref: str, segment: str, request: Request):
    _auth(request)
    line_id = segment[:-4] if segment.endswith(".mp3") else segment
    if not LINE_ID.fullmatch(line_id):
        raise HTTPException(400, "非法的行 id")
    path = _resolve(request, ref) / "audio" / (line_id + ".mp3")
    if not path.is_file():
        raise HTTPException(404, "分段不存在")
    return FileResponse(str(path))
