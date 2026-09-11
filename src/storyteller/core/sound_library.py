from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

from .utils import generate_id

_INDEX_FILE = "index.json"
_KINDS = ("sfx", "ambient", "music")
_EXTENSIONS = {"mp3": "mp3", "wav": "wav", "ogg": "ogg", "ogg_opus": "ogg"}

# Generated clips at or below this loudness are treated as failed
# generations: they are discarded instead of cached, so the same prompt can
# regenerate (and retry) later rather than permanently serving silence.
# audio.py reuses this as its "skip this clip" floor for legacy files.
MIN_SOUND_DBFS = -55.0


def normalize_prompt(prompt):
    """Collapse whitespace for cache-key purposes."""
    return re.sub(r"\s+", " ", (prompt or "").strip())


def fingerprint_for(model, prompt, audio_format):
    """Stable cache key: identical model + prompt + format reuse one file."""
    raw = "{}|{}|{}".format(
        model or "", normalize_prompt(prompt), (audio_format or "mp3").lower()
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SoundLibrary:
    """A global, cross-project cache of generated sounds.

    Every sound lives in ``base_dir`` as ``<id>.<ext>`` and is described in
    ``index.json`` (name, description, kind, tags, prompt, fingerprint,
    model, duration...). Re-requesting the same model+prompt+format returns
    the cached file without calling the provider. The metadata fields are
    deliberately rich so a future LLM step can search the catalog and reuse
    sounds instead of generating new ones.
    """

    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.index_path = self.base_dir / _INDEX_FILE
        self._records = None

    # ----- public API -----
    def get_or_create(
        self,
        provider,
        *,
        prompt,
        name,
        kind="sfx",
        description="",
        tags=None,
        audio_format="mp3",
    ):
        """Return (path, record, created); cache hits never call provider."""
        if kind not in _KINDS:
            raise ValueError("kind must be one of {}".format(", ".join(_KINDS)))
        prompt = normalize_prompt(prompt)
        if not prompt:
            raise ValueError("prompt must not be empty")

        records = self._load()
        fingerprint = fingerprint_for(
            getattr(provider, "model", None) or provider.name,
            prompt,
            audio_format,
        )
        existing = self._find_by_fingerprint(records, fingerprint)
        if existing is not None:
            path = self._record_path(existing)
            if path.exists():
                return path, existing, False
            # File was deleted out from under the index; regenerate below.
            records = [r for r in records if r is not existing]

        record_id = generate_id("snd_")
        ext = _EXTENSIONS.get((audio_format or "mp3").lower(), "mp3")
        path = self.base_dir / "{}.{}".format(record_id, ext)

        _, duration = provider.generate(
            prompt, path, audio_format=audio_format
        )

        # Reject a failed generation (near-silence or undecodable output)
        # before it is cached, otherwise the fingerprint would permanently
        # resolve to a useless clip.
        dbfs = _measure_dbfs(path)
        if dbfs is None or dbfs <= MIN_SOUND_DBFS:
            try:
                path.unlink()
            except OSError:
                pass
            level = "unreadable" if dbfs is None else "{:.0f} dBFS".format(dbfs)
            from .exceptions import SoundGenerationError

            raise SoundGenerationError(
                "Generated sound for {!r} was {} and was discarded "
                "(not cached)".format(prompt, level)
            )

        record = {
            "id": record_id,
            "name": name or prompt[:20],
            "description": description or "",
            "kind": kind,
            "tags": list(tags or []),
            "prompt": prompt,
            "fingerprint": fingerprint,
            "path": path.name,
            "format": ext,
            "duration": duration,
            "model": getattr(provider, "model", None) or provider.name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        records.append(record)
        self._write(records)
        return path, record, True

    def all(self):
        return list(self._load())

    def search(self, query, kind=None):
        """Case-insensitive keyword filter over name/description/tags/prompt."""
        terms = [t for t in re.split(r"\s+", (query or "").strip().lower()) if t]
        results = []
        for record in self._load():
            if kind and record.get("kind") != kind:
                continue
            if not terms:
                results.append(record)
                continue
            haystack = " ".join(
                [
                    str(record.get("name", "")),
                    str(record.get("description", "")),
                    str(record.get("prompt", "")),
                    " ".join(record.get("tags", []) or []),
                ]
            ).lower()
            if all(term in haystack for term in terms):
                results.append(record)
        return results

    def path_for(self, record):
        return self._record_path(record)

    # ----- internals -----
    def _load(self):
        if self._records is not None:
            return self._records
        if not self.index_path.exists():
            self._records = []
            return self._records
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            records = data.get("sounds") if isinstance(data, dict) else data
            if not isinstance(records, list):
                records = []
        except (ValueError, OSError):
            # Corrupt or unreadable index: treat as an empty library rather
            # than failing sound generation.
            records = []
        self._records = [r for r in records if isinstance(r, dict)]
        return self._records

    def _write(self, records):
        self.base_dir.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "sounds": records}
        tmp = self.index_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.index_path)
        self._records = records

    @staticmethod
    def _find_by_fingerprint(records, fingerprint):
        for record in records:
            if record.get("fingerprint") == fingerprint:
                return record
        return None

    def _record_path(self, record):
        return self.base_dir / str(record.get("path") or "")


def _measure_dbfs(path):
    """Return mean dBFS of an audio file, or None if it cannot be decoded."""
    try:
        from pydub import AudioSegment

        return AudioSegment.from_file(str(path)).dBFS
    except Exception:
        return None
