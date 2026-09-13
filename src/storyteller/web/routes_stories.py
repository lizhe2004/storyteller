from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

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
