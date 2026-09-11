from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
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


_UNSAFE_NAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_sound_name(name, fallback="sound"):
    """Turn a cue name into a cross-platform filename stem (no extension)."""
    text = re.sub(r"\s+", " ", str(name or "")).strip(" .")
    text = _UNSAFE_NAME_RE.sub("_", text)
    return text or fallback


def unique_path(directory, stem, ext):
    """Return directory/<stem>.<ext>, appending -2/-3... when it exists."""
    directory = Path(directory)
    candidate = directory / "{}.{}".format(stem, ext)
    counter = 2
    while candidate.exists():
        candidate = directory / "{}-{}.{}".format(stem, counter, ext)
        counter += 1
    return candidate


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
    def find(self, provider, prompt, audio_format="mp3"):
        """Return the cached record for model+prompt+format, or None.

        A record whose library file was deleted is treated as a miss.
        """
        prompt = normalize_prompt(prompt)
        if not prompt:
            raise ValueError("prompt must not be empty")
        fingerprint = fingerprint_for(
            getattr(provider, "model", None) or provider.name,
            prompt,
            audio_format,
        )
        record = self._find_by_fingerprint(self._load(), fingerprint)
        if record is not None and self._record_path(record).exists():
            return record
        return None

    def admit(
        self,
        source_path,
        provider,
        *,
        prompt,
        name,
        kind="sfx",
        description="",
        tags=None,
        audio_format="mp3",
        duration=None,
    ):
        """Gate an already-generated clip and COPY it into the library.

        The source file is never deleted: a near-silent or unreadable clip
        raises SoundGenerationError (message names the source path) and stays
        on disk for inspection.
        """
        if kind not in _KINDS:
            raise ValueError("kind must be one of {}".format(", ".join(_KINDS)))
        prompt = normalize_prompt(prompt)
        if not prompt:
            raise ValueError("prompt must not be empty")
        source = Path(source_path)
        ext = _EXTENSIONS.get((audio_format or "mp3").lower(), "mp3")

        dbfs = _measure_dbfs(source)
        if dbfs is None or dbfs <= MIN_SOUND_DBFS:
            level = "unreadable" if dbfs is None else "{:.0f} dBFS".format(dbfs)
            from .exceptions import SoundGenerationError

            raise SoundGenerationError(
                "Generated sound for {!r} was {} and was not admitted to "
                "the library (raw clip kept at {})".format(
                    prompt, level, source
                )
            )

        fingerprint = fingerprint_for(
            getattr(provider, "model", None) or provider.name,
            prompt,
            audio_format,
        )
        record_id = generate_id("snd_")
        dest = self.base_dir / "{}.{}".format(record_id, ext)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

        record = {
            "id": record_id,
            "name": name or prompt[:20],
            "description": description or "",
            "kind": kind,
            "tags": list(tags or []),
            "prompt": prompt,
            "fingerprint": fingerprint,
            "path": dest.name,
            "format": ext,
            "duration": duration,
            "model": getattr(provider, "model", None) or provider.name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        records = self._load()
        records.append(record)
        self._write(records)
        return record

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
