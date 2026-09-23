from __future__ import annotations

import json
import logging
import re
from time import perf_counter
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
_TITLE_MAX_CHARS = 60
_INVALID_DIR_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
logger = logging.getLogger(__name__)


def slug_title(title):
    """Filesystem-safe title segment used for date-title directories."""
    slug = _INVALID_DIR_CHARS.sub("-", str(title or ""))
    slug = re.sub(r"\s+", " ", slug).strip().strip("- .")
    slug = slug[:_TITLE_MAX_CHARS].strip().strip("- .")
    return slug or "未命名故事"


class ProjectManager:
    """Create, load, save, and list projects.

    A project lives in its own directory under the project root, with the
    state serialized to ``<project_id>/project.json``.
    """

    def __init__(self, project_root):
        self.project_root = Path(project_root)
        # Lazily-built index of project_id -> directories (a duplicated id
        # maps to several dirs); invalidated by rename/delete.
        self._id_index = None

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
        started = perf_counter()
        project_dir = self._dir_for_id(state.project_id)
        if project_dir is None:
            # Brand-new project: its directory does not exist yet.
            project_dir = self.project_root / state.project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_id": state.project_id,
            "state": state.state,
            "script": _script_to_dict(state.script) if state.script else None,
            "current_step": state.current_step,
            "config": state.config,
            "error": state.error,
            "error_at": state.error_at,
            "created_at": _dt_to_str(state.created_at),
            "updated_at": _dt_to_str(state.updated_at),
        }
        (project_dir / _PROJECT_FILE).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "event=project_saved project_id=%s state=%s duration_ms=%d path=%s",
            state.project_id, state.state,
            int((perf_counter() - started) * 1000), project_dir,
        )
        if self._id_index is not None:
            dirs = self._id_index.setdefault(state.project_id, [])
            if project_dir not in dirs:
                dirs.append(project_dir)

    def load_project(self, ref):
        """Load a project by project_id, directory name, or unique prefix."""
        project_dir = self.resolve_project_dir(ref)
        project_file = project_dir / _PROJECT_FILE
        if not project_file.exists():
            raise ProjectError("Project file missing for: {}".format(ref))
        payload = json.loads(project_file.read_text(encoding="utf-8"))
        return ProjectState(
            project_id=payload["project_id"],
            state=payload.get("state", "initialized"),
            script=_script_from_dict(payload["script"])
            if payload.get("script")
            else None,
            current_step=payload.get("current_step"),
            config=payload.get("config", {}),
            error=payload.get("error"),
            error_at=payload.get("error_at"),
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

    def delete_project(self, ref):
        project_dir = self.resolve_project_dir(ref)
        if project_dir.exists():
            import shutil

            shutil.rmtree(project_dir)
            self._id_index = None

    # ----- queries -----
    def get_project_dir(self, project_id):
        """Directory for a project id, following a date-title rename."""
        return self.resolve_project_dir(project_id)

    def _iter_project_dirs(self):
        """Yield directories that contain a project file, sorted by name."""
        if not self.project_root.exists():
            return
        for entry in sorted(self.project_root.iterdir()):
            if entry.is_dir() and (entry / _PROJECT_FILE).is_file():
                yield entry

    def _build_id_index(self):
        """Map every project_id to the dir(s) containing it."""
        index = {}
        for entry in self._iter_project_dirs():
            try:
                payload = json.loads(
                    (entry / _PROJECT_FILE).read_text(encoding="utf-8")
                )
            except (ValueError, OSError):
                continue
            pid = payload.get("project_id")
            if pid:
                index.setdefault(pid, []).append(entry)
        return index

    def _index(self):
        if self._id_index is None:
            self._id_index = self._build_id_index()
        return self._id_index

    def _dir_for_id(self, project_id):
        """The unique directory for an id, or None. Raises on duplicates."""
        dirs = self._index().get(project_id)
        if not dirs:
            return None
        if len(dirs) > 1:
            raise ProjectError(
                "Ambiguous project id '{}' found in: {}".format(
                    project_id,
                    ", ".join(sorted(d.name for d in dirs)),
                )
            )
        return dirs[0]

    def resolve_project_dir(self, ref):
        """Resolve an id, directory name, or unique prefix to a project dir.

        Prefixes match directory names (date-title dirs or legacy proj_ dirs);
        full project ids resolve through an id index. Legacy projects still
        use the id as the directory name.
        """
        ref = str(ref or "").strip()
        if not ref:
            raise ProjectError("Project reference must not be empty")

        direct = self.project_root / ref
        if (direct / _PROJECT_FILE).is_file():
            return direct

        id_dir = self._dir_for_id(ref)
        if id_dir is not None:
            return id_dir

        # Unique id prefix: the id index also accepts a leading prefix.
        id_matches = [
            d for pid, dirs in self._index().items()
            if pid.startswith(ref) for d in dirs
        ]
        if len(id_matches) == 1:
            return id_matches[0]
        if len(id_matches) > 1:
            raise ProjectError(
                "Ambiguous project reference '{}': {}".format(
                    ref,
                    ", ".join(sorted(d.name for d in id_matches)),
                )
            )

        prefix_matches = [
            entry for entry in self._iter_project_dirs()
            if entry.name.startswith(ref)
        ]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        if len(prefix_matches) > 1:
            raise ProjectError(
                "Ambiguous project reference '{}': {}".format(
                    ref,
                    ", ".join(sorted(d.name for d in prefix_matches)),
                )
            )
        raise ProjectError("Project not found: {}".format(ref))

    def rename_for_title(self, state, title=None):
        """Move the project dir to ``<created date>-<title>``.

        The project_id inside project.json stays stable. The move carries
        project.json itself, so no re-save is needed. Returns the new
        directory path.
        """
        title = title if title is not None else (
            state.script.title if state.script else None
        )
        date_part = (state.created_at or datetime.now()).strftime("%Y-%m-%d")
        base = "{}-{}".format(date_part, slug_title(title))
        target = self.project_root / base
        suffix = 2
        while target.exists():
            target = self.project_root / "{}-{}".format(base, suffix)
            suffix += 1

        source = self._try_id_dir(state.project_id)
        if source is None:
            # Already renamed (e.g. resume after the move): nothing to do.
            return self.resolve_project_dir(state.project_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        # Rebuild lazily on next use rather than patch the cached index:
        # invalidation also picks up externally created/duplicated dirs.
        self._id_index = None
        return target

    def _try_id_dir(self, project_id):
        """Legacy/current id-named directory if it exists, else None."""
        candidate = self.project_root / project_id
        return candidate if candidate.is_dir() else None

    def list_project_entries(self):
        """Return ``(dir_name, ProjectState)`` pairs for every project."""
        entries = []
        for entry in self._iter_project_dirs():
            try:
                entries.append((entry.name, self.load_project(entry.name)))
            except ProjectError:
                continue
        return entries

    def list_projects(self):
        return [state for _, state in self.list_project_entries()]


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
        "language": vc.language,
        "style": vc.style,
        "speed": vc.speed,
        "pitch": vc.pitch,
        "volume": vc.volume,
        "name": vc.name,
        "gender": vc.gender,
        "age": list(vc.age or []),
        "category": vc.category,
        "description": vc.description,
    }


def _voice_from_dict(data):
    if not data:
        return None
    return VoiceConfig(
        provider=data["provider"],
        voice_id=data["voice_id"],
        language=data.get("language", "zh-CN"),
        style=data.get("style"),
        speed=data.get("speed", 1.0),
        pitch=data.get("pitch", 1.0),
        volume=data.get("volume", 1.0),
        name=data.get("name"),
        gender=data.get("gender"),
        age=data.get("age"),
        category=data.get("category"),
        description=data.get("description"),
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
        "prompt": sfx.prompt,
        "description": sfx.description,
        "tags": list(sfx.tags or []),
        "anchor": sfx.anchor,
        "generation_history": list(sfx.generation_history or []),
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
        prompt=data.get("prompt"),
        description=data.get("description"),
        tags=list(data.get("tags", []) or []),
        anchor=data.get("anchor"),
        generation_history=list(data.get("generation_history", []) or []),
    )


def _character_to_dict(char):
    return {
        "id": char.id,
        "name": char.name,
        "description": char.description,
        "gender": char.gender,
        "age": char.age,
        "voice_preferences": list(char.voice_preferences or []),
        "voice_config": _voice_to_dict(char.voice_config),
    }


def _character_from_dict(data):
    return Character(
        id=data["id"],
        name=data["name"],
        description=data["description"],
        gender=data.get("gender"),
        age=data.get("age"),
        voice_preferences=list(data.get("voice_preferences", []) or []),
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
        "processing": line.processing,
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
        processing=data.get("processing", {}),
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
