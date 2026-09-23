"""Catalog story-generated voice clips for the voice management UI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..core.voice_overrides import voice_key


_AGE_ORDER = {"child": 0, "teen": 1, "young_adult": 2, "middle_aged": 3, "senior": 4}


class VoiceClipCatalog:
    def __init__(self, registry, project_manager):
        self.registry = registry
        self.project_manager = project_manager

    def _voices(self):
        return list(self.registry.list_tts_voices() or [])

    def _voice_map(self):
        voices = self._voices()
        return {voice_key(voice): voice for voice in voices}, voices

    def _project_entries(self):
        """Load projects defensively; one damaged project must not block the catalog."""
        root = self.project_manager.project_root
        if not root.exists():
            return []
        entries = []
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or not (entry / "project.json").is_file():
                continue
            try:
                entries.append((entry.name, self.project_manager.load_project(entry.name)))
            except Exception:
                continue
        return entries

    @staticmethod
    def _created_at(state):
        value = state.created_at or state.updated_at
        return value.isoformat() if isinstance(value, datetime) else ""

    @staticmethod
    def _safe_audio_path(project_dir, line):
        root = Path(project_dir).resolve()
        candidates = []
        if line.audio_path:
            configured = Path(line.audio_path)
            candidates.append(
                configured if configured.is_absolute() else root / configured
            )
        candidates.append(root / "audio" / (str(line.line_id) + ".mp3"))
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
                resolved.relative_to(root)
            except (OSError, ValueError):
                continue
            if resolved.is_file() and resolved.suffix.lower() == ".mp3":
                return resolved
        return None

    def _collect(self):
        voice_map, voices = self._voice_map()
        clips = {voice_key(voice): [] for voice in voices}

        for directory_name, state in self._project_entries():
            if not state.script:
                continue
            try:
                project_dir = self.project_manager.project_root / directory_name
                project_dir = project_dir.resolve()
                project_dir.relative_to(self.project_manager.project_root.resolve())
            except (OSError, ValueError):
                continue
            characters = {
                character.id: character.name
                for character in state.script.characters or []
            }
            for line in state.script.lines or []:
                line_voice = line.voice_config
                if line_voice is None:
                    continue
                key = voice_key(line_voice)
                if line_voice.model is None:
                    matches = [
                        catalog_key for catalog_key, catalog_voice in voice_map.items()
                        if catalog_voice.provider == line_voice.provider
                        and catalog_voice.voice_id == line_voice.voice_id
                    ]
                    if len(matches) == 1:
                        key = matches[0]
                if key not in clips:
                    continue
                audio_path = self._safe_audio_path(project_dir, line)
                if audio_path is None:
                    continue
                clip_id = "{}:{}".format(state.project_id, line.line_id)
                clips[key].append({
                    "clip_id": clip_id,
                    "project_id": state.project_id,
                    "story_title": state.script.title,
                    "character_name": characters.get(line.character_id) or "旁白",
                    "text": line.text,
                    "created_at": self._created_at(state),
                    "duration_ms": None,
                    "audio_url_id": clip_id,
                    "_audio_path": audio_path,
                })

        for values in clips.values():
            values.sort(key=lambda clip: clip["created_at"], reverse=True)
        return voice_map, clips

    @staticmethod
    def _public_clip(clip):
        return {key: value for key, value in clip.items() if not key.startswith("_")}

    @staticmethod
    def _public_voice(voice, clips):
        values = clips.get(voice_key(voice), [])
        return {
            "key": voice_key(voice),
            "provider": voice.provider,
            "model": voice.model,
            "voice_id": voice.voice_id,
            "name": voice.name,
            "gender": voice.gender,
            "age": list(voice.age or []),
            "category": voice.category,
            "description": voice.description,
            "clip_count": len(values),
            "has_clips": bool(values),
        }

    def list_voices(self):
        voice_map, clips = self._collect()
        return [self._public_voice(voice, clips) for voice in voice_map.values()]

    def filter_voices(
        self, provider=None, model=None, gender=None, age=None, page=1, page_size=50
    ):
        records = self.list_voices()
        filters = {
            "providers": sorted({record["provider"] for record in records if record["provider"]}),
            "models": sorted({record["model"] for record in records if record["model"]}),
            "genders": sorted({record["gender"] for record in records if record["gender"]}),
            "ages": sorted(
                {item for record in records for item in record["age"]},
                key=lambda item: (_AGE_ORDER.get(item, 999), item),
            ),
        }
        if provider:
            records = [record for record in records if record["provider"] == provider]
        if model:
            records = [record for record in records if record["model"] == model]
        if gender:
            records = [record for record in records if record["gender"] == gender]
        if age:
            records = [record for record in records if age in record["age"]]
        page = max(1, int(page))
        page_size = min(200, max(1, int(page_size)))
        start = (page - 1) * page_size
        return {
            "voices": records[start:start + page_size],
            "total": len(records),
            "page": page,
            "page_size": page_size,
            "filters": filters,
        }

    def clips_for_voice(self, key):
        voice_map, clips = self._collect()
        if key not in voice_map:
            raise KeyError(key)
        return [self._public_clip(clip) for clip in clips[key]]

    def resolve_clip_audio(self, key, clip_id):
        voice_map, clips = self._collect()
        if key not in voice_map:
            raise KeyError(key)
        if not clip_id or "/" in str(clip_id) or "\\" in str(clip_id):
            return None
        for clip in clips[key]:
            if clip["clip_id"] == clip_id:
                return clip["_audio_path"]
        return None
