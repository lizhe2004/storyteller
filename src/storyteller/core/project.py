from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .exceptions import ProjectError
from .models import (
    Character,
    ProjectState,
    Script,
    ScriptLine,
    SoundEffect,
    VoiceConfig,
)
from .utils import generate_id

_PROJECT_FILE = "project.json"


class ProjectManager:
    """Create, load, save, and list projects.

    A project lives in its own directory under the project root, with the
    state serialized to ``<project_id>/project.json``.
    """

    def __init__(self, project_root):
        self.project_root = Path(project_root)

    # ----- lifecycle -----
    def create_project(self, topic=None, config=None):
        project_id = generate_id("proj_")
        state = ProjectState(
            project_id=project_id,
            state="topic_collected",
            current_step="topic_collected",
            config={"topic": topic} if topic else {},
        )
        if config:
            state.config.update(config)
        self.save_project(state)
        return state

    def save_project(self, state):
        project_dir = self.get_project_dir(state.project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_id": state.project_id,
            "state": state.state,
            "script": _script_to_dict(state.script) if state.script else None,
            "current_step": state.current_step,
            "config": state.config,
            "created_at": _dt_to_str(state.created_at),
            "updated_at": _dt_to_str(state.updated_at),
        }
        (project_dir / _PROJECT_FILE).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_project(self, project_id):
        project_dir = self.get_project_dir(project_id)
        if not project_dir.exists():
            raise ProjectError("Project not found: {}".format(project_id))
        project_file = project_dir / _PROJECT_FILE
        if not project_file.exists():
            raise ProjectError("Project file missing for: {}".format(project_id))
        payload = json.loads(project_file.read_text(encoding="utf-8"))
        return ProjectState(
            project_id=payload["project_id"],
            state=payload.get("state", "initialized"),
            script=_script_from_dict(payload["script"])
            if payload.get("script")
            else None,
            current_step=payload.get("current_step"),
            config=payload.get("config", {}),
            created_at=_str_to_dt(payload.get("created_at")),
            updated_at=_str_to_dt(payload.get("updated_at")),
        )

    def update_state(self, project_id, new_state):
        state = self.load_project(project_id)
        state.state = new_state
        state.current_step = new_state
        state.updated_at = datetime.now()
        self.save_project(state)
        return state

    def delete_project(self, project_id):
        project_dir = self.get_project_dir(project_id)
        if project_dir.exists():
            import shutil

            shutil.rmtree(project_dir)

    # ----- queries -----
    def get_project_dir(self, project_id):
        return self.project_root / project_id

    def list_projects(self):
        if not self.project_root.exists():
            return []
        projects = []
        for entry in sorted(self.project_root.iterdir()):
            if entry.is_dir() and (entry / _PROJECT_FILE).exists():
                try:
                    projects.append(self.load_project(entry.name))
                except ProjectError:
                    continue
        return projects


# ========== serialization helpers ==========
def _dt_to_str(dt):
    return dt.isoformat() if dt else None


def _str_to_dt(value):
    if not value:
        return None
    return datetime.fromisoformat(value)


def _voice_to_dict(vc):
    if vc is None:
        return None
    return {
        "provider": vc.provider,
        "voice_id": vc.voice_id,
        "voice_type": vc.voice_type,
        "language": vc.language,
        "style": vc.style,
        "speed": vc.speed,
        "pitch": vc.pitch,
        "volume": vc.volume,
    }


def _voice_from_dict(data):
    if not data:
        return None
    return VoiceConfig(
        provider=data["provider"],
        voice_id=data["voice_id"],
        voice_type=data["voice_type"],
        language=data.get("language", "zh-CN"),
        style=data.get("style"),
        speed=data.get("speed", 1.0),
        pitch=data.get("pitch", 1.0),
        volume=data.get("volume", 1.0),
    )


def _sound_to_dict(sfx):
    if sfx is None:
        return None
    return {
        "effect_id": sfx.effect_id,
        "name": sfx.name,
        "type": sfx.type,
        "source_path": sfx.source_path,
        "source_type": sfx.source_type,
        "volume": sfx.volume,
        "start_time": sfx.start_time,
        "duration": sfx.duration,
        "fade_in": sfx.fade_in,
        "fade_out": sfx.fade_out,
    }


def _sound_from_dict(data):
    if not data:
        return None
    return SoundEffect(
        effect_id=data["effect_id"],
        name=data["name"],
        type=data["type"],
        source_path=data.get("source_path"),
        source_type=data.get("source_type", "local"),
        volume=data.get("volume", 1.0),
        start_time=data.get("start_time", 0.0),
        duration=data.get("duration"),
        fade_in=data.get("fade_in", 0.0),
        fade_out=data.get("fade_out", 0.0),
    )


def _character_to_dict(char):
    return {
        "id": char.id,
        "name": char.name,
        "description": char.description,
        "voice_config": _voice_to_dict(char.voice_config),
    }


def _character_from_dict(data):
    return Character(
        id=data["id"],
        name=data["name"],
        description=data["description"],
        voice_config=_voice_from_dict(data.get("voice_config")),
    )


def _line_to_dict(line):
    return {
        "line_id": line.line_id,
        "line_type": line.line_type,
        "character_id": line.character_id,
        "text": line.text,
        "voice_config": _voice_to_dict(line.voice_config),
        "audio_path": line.audio_path,
        "sound_effects": [
            _sound_to_dict(s) for s in line.sound_effects
        ],
        "background_music": _sound_to_dict(line.background_music),
        "metadata": line.metadata,
    }


def _line_from_dict(data):
    return ScriptLine(
        line_id=data["line_id"],
        line_type=data["line_type"],
        character_id=data.get("character_id"),
        text=data.get("text", ""),
        voice_config=_voice_from_dict(data.get("voice_config")),
        audio_path=data.get("audio_path"),
        sound_effects=[
            _sound_from_dict(s) for s in data.get("sound_effects", []) or []
        ],
        background_music=_sound_from_dict(data.get("background_music")),
        metadata=data.get("metadata", {}),
    )


def _script_to_dict(script):
    return {
        "script_id": script.script_id,
        "title": script.title,
        "topic": script.topic,
        "characters": [_character_to_dict(c) for c in script.characters],
        "lines": [_line_to_dict(l) for l in script.lines],
        "background_music": _sound_to_dict(script.background_music),
        "sound_effects": [_sound_to_dict(s) for s in script.sound_effects],
        "metadata": script.metadata,
        "created_at": _dt_to_str(script.created_at),
        "updated_at": _dt_to_str(script.updated_at),
    }


def _script_from_dict(data):
    return Script(
        script_id=data["script_id"],
        title=data["title"],
        topic=data["topic"],
        characters=[
            _character_from_dict(c) for c in data.get("characters", []) or []
        ],
        lines=[_line_from_dict(l) for l in data.get("lines", []) or []],
        background_music=_sound_from_dict(data.get("background_music")),
        sound_effects=[
            _sound_from_dict(s) for s in data.get("sound_effects", []) or []
        ],
        metadata=data.get("metadata", {}),
        created_at=_str_to_dt(data.get("created_at")),
        updated_at=_str_to_dt(data.get("updated_at")),
    )
