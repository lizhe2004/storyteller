from __future__ import annotations

import json
import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from ..core.utils import generate_id


TERMINAL_STATUSES = {"completed", "failed", "canceled"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _read_json_file(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default
    except (OSError, ValueError):
        return default


def _read_json_dir(directory):
    values = []
    if not directory.is_dir():
        return values
    for path in sorted(directory.glob("*.json")):
        value = _read_json_file(path, None)
        if value is not None:
            values.append(value)
    return values


def _summary_suggestions(summary):
    normalized = summary.get("normalized_result", {})
    values = normalized.get("suggestions", [])
    if isinstance(values, str):
        values = [values]
    enrichment = normalized.get("catalog_enrichment", {})
    if isinstance(enrichment, dict):
        description = enrichment.get("recommended_description")
        if description and description not in values:
            values.append("建议音色库描述：" + str(description))
        tags = enrichment.get("recommended_tags", [])
        if tags:
            values.append("建议新增标签：" + "、".join(str(tag) for tag in tags))
    return values


def _summary_suggestion_records(summary):
    normalized = summary.get("normalized_result", {})
    records = []
    for text in normalized.get("suggestions", []) if isinstance(normalized.get("suggestions", []), list) else [normalized.get("suggestions")]:
        if text:
            category = "performance" if any(word in str(text) for word in ("语速", "音高", "能量", "频", "情绪")) else "usage"
            records.append({"text": str(text), "category": category})
    role_match = normalized.get("role_match", {})
    for text in role_match.get("mismatches", []) if isinstance(role_match, dict) else []:
        records.append({"text": str(text), "category": "role_mismatch"})
    enrichment = normalized.get("catalog_enrichment", {})
    if isinstance(enrichment, dict):
        description = enrichment.get("recommended_description")
        if description:
            records.append({"text": "建议音色库描述：" + str(description), "category": "catalog"})
        tags = enrichment.get("recommended_tags", [])
        if tags:
            records.append({"text": "建议新增标签：" + "、".join(str(tag) for tag in tags), "category": "catalog"})
    return records


def _voice_key(config):
    if not isinstance(config, dict) or not config.get("voice_id"):
        return None
    return "{}:{}".format(config.get("provider", "unknown"), config["voice_id"])


def _sample_id(story_id, line_id, voice_key):
    digest = hashlib.sha1("{}:{}:{}".format(story_id, line_id, voice_key).encode()).hexdigest()[:16]
    return "sample_" + digest


def build_sample_inventory(stories_root, catalog_by_voice=None, limit=10, *, randomize=False, seed=None):
    """Build historical TTS samples by voice, optionally selecting them randomly."""
    limit = max(1, min(int(limit or 10), 20))
    catalog_by_voice = catalog_by_voice or {}
    grouped = {}
    root = Path(stories_root)
    for story_dir in sorted(root.iterdir() if root.exists() else []):
        script_path = story_dir / "story.script.json"
        if not story_dir.is_dir() or not script_path.is_file():
            continue
        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        characters = {c.get("id"): c for c in script.get("characters", [])}
        narrator = characters.get("narrator", {})
        for line in script.get("lines", []):
            character = characters.get(line.get("character_id"), narrator)
            voice = character.get("voice_config") or narrator.get("voice_config")
            key = _voice_key(voice)
            if not key:
                continue
            audio = story_dir / "audio" / "{}.mp3".format(line.get("line_id"))
            if not audio.is_file():
                continue
            sample = {
                "story_id": script.get("project_id") or story_dir.name,
                "story_dir": str(story_dir),
                "audio_path": str(audio),
                "line_id": str(line.get("line_id")),
                "line_type": line.get("line_type"),
                "text": line.get("text", ""),
                "character_id": character.get("id"),
                "character_name": character.get("name"),
                "character_description": character.get("description", ""),
                "voice_provider": voice.get("provider"),
                "voice_id": voice.get("voice_id"),
                "voice_model": voice.get("model") or (catalog_by_voice.get(key) or {}).get("model"),
                "voice_name": voice.get("name") or (catalog_by_voice.get(key) or {}).get("name") or voice.get("voice_id"),
                "voice_key": key,
                "catalog_snapshot": catalog_by_voice.get(key) or {},
            }
            sample["sample_id"] = _sample_id(sample["story_id"], sample["line_id"], key)
            grouped.setdefault(key, []).append(sample)

    result = []
    for key in sorted(grouped):
        items = grouped[key]
        if randomize:
            voice_seed = "{}:{}".format(seed, key)
            rng = random.Random(int(hashlib.sha1(voice_seed.encode()).hexdigest()[:16], 16))
            selected = rng.sample(items, min(limit, len(items)))
            result.extend(selected)
            continue
        # Round-robin stories first, then line order, so one long story cannot
        # consume the entire sample budget for a voice.
        by_story = {}
        for item in items:
            by_story.setdefault(item["story_id"], []).append(item)
        selected = []
        while by_story and len(selected) < limit:
            for story_id in list(sorted(by_story)):
                bucket = by_story[story_id]
                selected.append(bucket.pop(0))
                if not bucket:
                    del by_story[story_id]
                if len(selected) >= limit:
                    break
        result.extend(selected)
    return result


@dataclass
class VoiceAnalysisJob:
    job_id: str
    root: Path
    manifest: dict

    @property
    def directory(self):
        return self.root / self.job_id

    def save(self):
        self.manifest["updated_at"] = _now()
        _write_json(self.directory / "manifest.json", self.manifest)

    def snapshot(self):
        return dict(self.manifest)

    def detail(self):
        samples = []
        sample_file = self.directory / "samples.json"
        if sample_file.is_file():
            try:
                samples = json.loads(sample_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                samples = []
        for sample in samples:
            result_file = self.directory / "sample-results" / (sample["sample_id"] + ".json")
            if result_file.is_file():
                try:
                    sample["result"] = json.loads(result_file.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    sample["result"] = None
        result = self.snapshot()
        result["samples"] = samples
        result["voice_summaries"] = _read_json_dir(self.directory / "voice-summaries")
        result["suggestions"] = _read_json_file(self.directory / "suggestions.json", [])
        return result


class VoiceAnalysisManager:
    def __init__(self, analysis_root, stories_root=None):
        self.root = Path(analysis_root)
        self.stories_root = Path(stories_root) if stories_root else None
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs = {}
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="voice-analysis")
        self._load_jobs()

    def _load_jobs(self):
        for directory in sorted(self.root.iterdir()):
            path = directory / "manifest.json"
            if not directory.is_dir() or not path.is_file():
                continue
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            job_id = manifest.get("job_id") or directory.name
            self.jobs[job_id] = VoiceAnalysisJob(job_id, self.root, manifest)

    def create_job(self, options=None):
        options = dict(options or {})
        job_id = generate_id("analysis_")
        job = VoiceAnalysisJob(job_id, self.root, {
            "job_id": job_id,
            "status": "pending",
            "phase": "pending",
            "sample_limit": max(1, min(int(options.get("sample_limit", 10)), 20)),
            "model_sample": options.get("model_sample", "gemini-3.5-flash-lite"),
            "model_summary": options.get("model_summary", "gemini-3.5-flash-lite"),
            "prompt_version": options.get("prompt_version", "voice-analysis-v1"),
            "analysis_config_version": options.get("analysis_config_version", "v1"),
            "sampling_strategy": options.get("sampling_strategy", "random"),
            "sample_seed": options.get("sample_seed", random.SystemRandom().randrange(2**32)),
            "total": 0, "completed": 0, "failed": 0, "skipped": 0,
            "created_at": _now(), "updated_at": _now(),
        })
        job.directory.mkdir(parents=True, exist_ok=True)
        for name in ("sample-results", "voice-summaries"):
            (job.directory / name).mkdir()
        job.save()
        self.jobs[job_id] = job
        return job

    def get_job(self, job_id):
        job = self.jobs.get(job_id)
        if job is None:
            return None
        if not job.directory.is_dir():
            self.jobs.pop(job_id, None)
            return None
        manifest_path = job.directory / "manifest.json"
        manifest = _read_json_file(manifest_path, None)
        if isinstance(manifest, dict) and manifest.get("updated_at") != job.manifest.get("updated_at"):
            job.manifest = manifest
        return job

    def update_suggestion(self, job_id, suggestion_id, status):
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if status not in {"approved", "rejected", "pending"}:
            raise ValueError(status)
        path = job.directory / "suggestions.json"
        suggestions = _read_json_file(path, [])
        for suggestion in suggestions:
            if suggestion.get("suggestion_id") == suggestion_id:
                suggestion["status"] = status
                suggestion["updated_at"] = _now()
                _write_json(path, suggestions)
                return suggestion
        return None

    def list_jobs(self):
        for job_id in list(self.jobs):
            self.get_job(job_id)
        return [job.snapshot() for job in sorted(self.jobs.values(), key=lambda j: j.manifest.get("created_at", ""), reverse=True)]

    def submit(self, job_id, stories_root, catalog_by_voice, analyzer):
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.manifest.get("status") in {"running", "completed"}:
            return
        job.manifest.update({"status": "running", "phase": "scanning"})
        job.save()
        self.executor.submit(self._run, job, stories_root, catalog_by_voice, analyzer)

    def _run(self, job, stories_root, catalog_by_voice, analyzer):
        try:
            samples = build_sample_inventory(
                stories_root, catalog_by_voice, job.manifest["sample_limit"],
                randomize=job.manifest.get("sampling_strategy") == "random",
                seed=job.manifest.get("sample_seed"),
            )
            job.manifest.update({"phase": "sampling", "total": len(samples)})
            _write_json(job.directory / "samples.json", samples)
            job.save()
            pending = [sample for sample in samples if not (job.directory / "sample-results" / (sample["sample_id"] + ".json")).exists()]
            job.manifest["phase"] = "analyzing_samples"
            job.save()
            if pending and hasattr(analyzer, "analyze_voice"):
                pending_by_voice = {}
                for sample in pending:
                    pending_by_voice.setdefault(sample["voice_key"], []).append(sample)
                for voice_samples in pending_by_voice.values():
                    try:
                        batch = analyzer.analyze_voice(voice_samples, voice_samples[0].get("catalog_snapshot", {}))
                        batch_results = batch["samples"]
                        for sample in voice_samples:
                            result_path = job.directory / "sample-results" / (sample["sample_id"] + ".json")
                            result = batch_results[sample["sample_id"]]
                            result.update({"sample_id": sample["sample_id"], "status": "completed"})
                            _write_json(result_path, result)
                        voice_key = voice_samples[0]["voice_key"]
                        safe_name = voice_key.replace(":", "_").replace("/", "_")
                        summary = dict(batch["summary"])
                        summary.update({"voice_key": voice_key, "status": "completed", "sample_count": len(voice_samples), "catalog_snapshot": voice_samples[0].get("catalog_snapshot", {})})
                        _write_json(job.directory / "voice-summaries" / (safe_name + ".json"), summary)
                        for item in _summary_suggestion_records(summary):
                            suggestions = _read_json_file(job.directory / "suggestions.json", [])
                            suggestions.append({"suggestion_id": generate_id("suggestion_"), "voice_key": voice_key, "status": "pending", **item, "source": "voice_analysis"})
                            _write_json(job.directory / "suggestions.json", suggestions)
                    except Exception as exc:
                        for sample in voice_samples:
                            result_path = job.directory / "sample-results" / (sample["sample_id"] + ".json")
                            _write_json(result_path, {"sample_id": sample["sample_id"], "status": "failed", "error_type": type(exc).__name__, "error_message": str(exc)[:500]})
            elif pending:
                for sample in pending:
                    result_path = job.directory / "sample-results" / (sample["sample_id"] + ".json")
                    try:
                        result = analyzer.analyze_sample(sample)
                        result.update({"sample_id": sample["sample_id"], "status": "completed"})
                        _write_json(result_path, result)
                    except Exception as exc:
                        _write_json(result_path, {"sample_id": sample["sample_id"], "status": "failed", "error_type": type(exc).__name__, "error_message": str(exc)[:500]})
            completed = failed = 0
            for sample in samples:
                result = _read_json_file(job.directory / "sample-results" / (sample["sample_id"] + ".json"), {})
                completed += result.get("status") == "completed"
                failed += result.get("status") == "failed"
            job.manifest.update({"completed": completed, "failed": failed, "current": len(samples)})
            job.save()
            job.manifest.update({"phase": "aggregating_voices"})
            by_voice = {}
            for sample in samples:
                result_file = job.directory / "sample-results" / (sample["sample_id"] + ".json")
                result = _read_json_file(result_file, {})
                if result.get("status") == "completed":
                    by_voice.setdefault(sample["voice_key"], []).append({**sample, **result})
            for voice_key, voice_samples in by_voice.items():
                if hasattr(analyzer, "analyze_voice"):
                    job.manifest["voice_completed"] = sum(1 for path in (job.directory / "voice-summaries").glob("*.json") if path.is_file())
                    continue
                try:
                    summary = analyzer.summarize_voice(voice_samples, voice_samples[0].get("catalog_snapshot", {}))
                    summary.update({"voice_key": voice_key, "status": "completed", "sample_count": len(voice_samples)})
                    safe_name = voice_key.replace(":", "_").replace("/", "_")
                    _write_json(job.directory / "voice-summaries" / (safe_name + ".json"), summary)
                    job.manifest["voice_completed"] = job.manifest.get("voice_completed", 0) + 1
                    normalized = summary.get("normalized_result", {})
                    for item in _summary_suggestion_records(summary):
                        suggestions = _read_json_file(job.directory / "suggestions.json", [])
                        suggestions.append({"suggestion_id": generate_id("suggestion_"), "voice_key": voice_key, "status": "pending", **item, "source": "voice_summary"})
                        _write_json(job.directory / "suggestions.json", suggestions)
                except Exception as exc:
                    job.manifest["voice_failed"] = job.manifest.get("voice_failed", 0) + 1
                    job.manifest["last_error"] = str(exc)[:500]
                job.save()
            job.manifest.update({"status": "completed", "phase": "completed"})
            job.save()
        except Exception as exc:
            job.manifest.update({"status": "failed", "phase": "failed", "error_type": type(exc).__name__, "error_message": str(exc)[:500]})
            job.save()
