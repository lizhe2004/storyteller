from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path

from .models import VoiceConfig, normalize_voice_ages


_AGE_ORDER = {
    "child": 0,
    "teen": 1,
    "young_adult": 2,
    "middle_aged": 3,
    "senior": 4,
}


def voice_key(voice: VoiceConfig) -> str:
    return "{}|{}|{}".format(
        voice.provider,
        voice.model or "unknown",
        voice.voice_id,
    )


def _ordered_ages(value):
    ages = normalize_voice_ages(value)
    return sorted(ages, key=lambda age: _AGE_ORDER[age])


class VoiceOverrideStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._overrides = self._load()

    def _load(self):
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def get_age(self, key: str):
        entry = self._overrides.get(key)
        if not isinstance(entry, dict) or "age" not in entry:
            return None
        return _ordered_ages(entry.get("age"))

    def set_age(self, key: str, ages):
        normalized = _ordered_ages(ages)
        self._overrides[key] = {
            "age": normalized,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()
        return normalized

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=".voice-overrides-", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self._overrides, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, str(self.path))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def apply(self, voices):
        result = []
        for voice in voices:
            ages = self.get_age(voice_key(voice))
            result.append(replace(voice, age=ages) if ages is not None else voice)
        return result
