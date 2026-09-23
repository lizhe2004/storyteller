from __future__ import annotations

from collections import deque
from pathlib import Path
import logging
import os
import tempfile
import threading
import time

from ..core.exceptions import LLMError, TTSError
from ..core.pipeline import Pipeline, human_time
from ..core.story_generator import StoryGenerator, _script_from_json
from ..core.tts import CHUNK_AUDIO, STREAM_SAMPLE_RATE
from ..core.voice_matcher import VoiceMatcher
from .fillers import cached_start_notice, choose_host_voice, start_notice_text
from .routes_options import configured_models
from .tts_chunks import audio_file_to_standard_pcm, iter_pcm_frames, pcm_duration_ms, pcm_to_mp3_file
from .tts_scheduler import TTSScheduler
from ..core.observability import (
    _safe_exception_message,
    log_event,
    timed_event,
    with_context,
)

logger = logging.getLogger(__name__)


def _emit_stream_warning(job, message, *, event, phase=None, line_id=None, exc=None):
    """Send a client warning and persist the same incident in structured logs."""
    fields = {
        "phase": phase or job.phase,
        "line_id": line_id,
        "message": message,
    }
    if exc is not None:
        fields.update({
            "error_type": type(exc).__name__,
            "exception_message": _safe_exception_message(exc),
        })
    log_event(
        logger,
        logging.WARNING,
        event,
        context={
            "job_id": job.id,
            "project_id": job.project_id,
        },
        **fields,
    )
    payload = {"type": "warning", "message": message}
    if line_id is not None:
        payload["line_id"] = line_id
    job.emit(payload)


def _script_preview_event(preview):
    characters = preview.get("characters") or []
    names = {c.get("id"): c.get("name") for c in characters}
    lines = []
    for line in preview.get("lines") or []:
        line = dict(line)
        line["speaker"] = names.get(line.get("character_id")) or (
            "旁白" if line.get("line_type") == "narration" else "未知角色"
        )
        lines.append(line)
    return {
        "type": "script_preview",
        "title": preview.get("title") or "",
        "opening": preview.get("opening") or "",
        "total": len(lines),
        "characters": characters,
        "lines": lines,
    }


def _characters_matched_event(script, registry=None):
    return {
        "type": "characters_matched",
        "characters": [
            {
                "id": character.id,
                "name": character.name,
                "description": character.description,
                "gender": character.gender,
                "age": character.age,
                "voice": (
                    {
                        "provider": character.voice_config.provider,
                        "model": (
                            registry.get_tts_model(character.voice_config)
                            if registry is not None else None
                        ),
                        "voice_id": character.voice_config.voice_id,
                        "name": character.voice_config.name,
                        "gender": character.voice_config.gender,
                        "age": list(character.voice_config.age),
                        "category": character.voice_config.category,
                        "description": character.voice_config.description,
                    }
                    if character.voice_config else None
                ),
            }
            for character in script.characters
        ],
    }


class _AudioPump:
    """Drain one scheduled session on a dedicated reader without blocking text input."""

    def __init__(self, session, lease, on_first_audio=None):
        self.session = session
        self.lease = lease
        self.on_first_audio = on_first_audio
        self.pcm = bytearray()
        self.error = None
        self.started = False
        self._thread = threading.Thread(target=self._drain, name="web-tts-audio", daemon=True)

    def start(self):
        self._thread.start()

    def finish(self):
        self.session.finish()
        self._thread.join()
        if self.error is not None:
            raise self.error
        return bytes(self.pcm)

    def cancel(self):
        try:
            self.lease.abort()
            self.session.cancel()
        finally:
            self._thread.join(timeout=1)

    def _drain(self):
        try:
            for chunk in self.session.iter_audio():
                if chunk.kind != CHUNK_AUDIO:
                    continue
                if len(chunk.data) % 2:
                    raise ValueError("PCM frame must have even byte length")
                if not self.started:
                    self.started = True
                    if self.on_first_audio is not None:
                        self.on_first_audio()
                self.lease.publish(chunk.data)
                self.pcm.extend(chunk.data)
        except Exception as exc:  # surfaced by finish() in the orchestration thread
            self.error = exc


class _IncrementalLineCoordinator:
    """Turn streamed line text into buffered, independently finalized TTS clips."""

    def __init__(self, orchestrator, job, publisher, scheduler, names):
        self.orchestrator = orchestrator
        self.job = job
        self.publisher = publisher
        self.scheduler = scheduler
        self.names = names
        self._states = {}
        self._voices = {}
        self._provisional_char_voice_map = {}
        self._provisional_narrator_voice = None
        self._lock = threading.Lock()

    def on_delta(self, index, raw_line, suffix):
        with self._lock:
            state = self._states.get(index)
            if state is None:
                state = {
                    "text": "", "complete": False, "voice": None,
                    "raw_line": dict(raw_line),
                    "condition": threading.Condition(threading.Lock()),
                    "pcm": None, "error": None, "thread": None,
                }
                self._states[index] = state
                self.publisher.add_phase(("line", index + 1), live=True)
                provisional_voice = self._provisional_voice_for_raw_line_locked(raw_line)
                if provisional_voice is not None:
                    self._voices[index] = provisional_voice
                self.job.emit({
                    "type": "line_start", "line_id": str(raw_line.get("line_id") or index + 1),
                    "index": index + 1, "total": self.job.total,
                    "speaker": self.names.get(raw_line.get("character_id"))
                    or ("旁白" if raw_line.get("line_type") == "narration" else "未知角色"),
                    "text": str(raw_line.get("text") or ""), "has_sound": False,
                })
            else:
                state["raw_line"] = dict(raw_line)
            condition = state["condition"]
        with condition:
            state["text"] += suffix
            condition.notify_all()
        self.job.emit({"type": "line_text_delta", "line_id": str(raw_line.get("line_id") or index + 1),
                       "index": index + 1, "text": suffix})
        self._maybe_start(index)

    def on_complete(self, index, raw_line):
        state = self._states.get(index)
        if state is None:
            return
        with state["condition"]:
            state["complete"] = True
            state["condition"].notify_all()
        self._maybe_start(index)

    def apply_final_line_voices(self, script, char_map, narrator):
        with self._lock:
            for index, line in enumerate(script.lines):
                self._voices[index] = self.orchestrator.pipeline.voice_for_line(
                    line, char_map, narrator
                )
        for index in list(self._states):
            self._maybe_start(index)

    def set_provisional_voice_context(self, script):
        """Store matched voices for lines that arrive during script streaming."""
        char_map = {
            character.id: character.voice_config
            for character in script.characters
            if character.voice_config
        }
        narrator = self.orchestrator.pipeline._find_narrator_voice(script, char_map)
        with self._lock:
            self._provisional_char_voice_map = char_map
            self._provisional_narrator_voice = narrator
            for index, state in self._states.items():
                voice = self._provisional_voice_for_raw_line_locked(state["raw_line"])
                if voice is not None:
                    self._voices[index] = voice
        for index in list(self._states):
            self._maybe_start(index)

    def _provisional_voice_for_raw_line_locked(self, raw_line):
        voice = None
        if raw_line.get("line_type") == "dialogue":
            voice = self._provisional_char_voice_map.get(raw_line.get("character_id"))
        return voice or self._provisional_narrator_voice

    def _maybe_start(self, index):
        with self._lock:
            state = self._states.get(index)
            voice = self._voices.get(index)
            if state is None or voice is None or state["thread"] is not None:
                return
            state["voice"] = voice
            state["thread"] = threading.Thread(
                target=self._run, args=(index, state),
                name="line-tts-{}".format(index + 1), daemon=True,
            )
            state["thread"].start()

    def _run(self, index, state):
        pump = lease = None
        try:
            lease = self.publisher.lease(("line", index + 1))
            pump = _AudioPump(
                self.orchestrator._open_session(
                    self.scheduler, state["voice"], phase="line",
                    line_id=str(state["raw_line"].get("line_id") or index + 1),
                ), lease
            )
            pump.start()
            sent = 0
            condition = state["condition"]
            while True:
                with condition:
                    while len(state["text"]) == sent and not state["complete"]:
                        condition.wait()
                    text = state["text"][sent:]
                    complete = state["complete"]
                if text:
                    pump.session.send_text(text)
                    sent += len(text)
                if complete and sent == len(state["text"]):
                    pcm = pump.finish()
                    if not pcm:
                        raise TTSError("实时 TTS 没有返回音频")
                    state["pcm"] = pcm
                    lease.commit()
                    return
        except Exception as exc:
            if pump is not None and pump.pcm:
                state["pcm"] = bytes(pump.pcm)
            state["error"] = exc
            if pump is not None:
                pump.cancel()
            elif lease is not None:
                lease.abort()
        finally:
            with state["condition"]:
                state["condition"].notify_all()

    def get(self, index):
        return self._states.get(index)

    def wait(self, index):
        state = self._states.get(index)
        if state is None:
            return None, None
        thread = state["thread"]
        if thread is not None:
            thread.join()
        return state["pcm"], state["error"]


class _AudioLease:
    """A generation-scoped producer handle for one ordered audio phase."""

    def __init__(self, publisher, key, generation):
        self._publisher = publisher
        self._key = key
        self._generation = generation

    def publish(self, data):
        self._publisher.publish(self, data)

    def commit(self):
        self._publisher.commit(self)

    def abort(self):
        self._publisher.abort(self)


class _OrderedAudioPublisher:
    """Ordered PCM publication for opening/notice/line phases.

    Live phases stream each frame as soon as their turn reaches the ordered
    publisher; once a byte is out it cannot be reclaimed. A phase that has not
    reached the cursor still buffers frames so opening, notice, and lines stay
    in order. Failed live phases must not publish a second whole-line fallback
    after partial audio has already reached the client.
    """

    def __init__(self, job, phases, live_phases=("opening",)):
        self._job = job
        self._phases = list(phases)
        self._live = set(live_phases)
        self._tracks = {
            key: {"generation": 0, "state": "waiting", "frames": deque(),
                  "live": key in self._live, "published_frames": 0,
                  "published_bytes": 0}
            for key in self._phases
        }
        self._cursor = 0
        self._cancelled = False
        self._lock = threading.Lock()

    def lease(self, key):
        with self._lock:
            track = self._track(key)
            if self._cancelled or self._job.cancel_event.is_set():
                self._cancel_locked()
                raise TTSError("音频发布已取消")
            if track["state"] in ("open", "committed", "released", "skipped"):
                raise TTSError("音频阶段不可重新打开")
            track["generation"] += 1
            track["state"] = "open"
            track["frames"].clear()
            return _AudioLease(self, key, track["generation"])

    def add_phase(self, key, *, live=False):
        with self._lock:
            if key in self._tracks:
                raise TTSError("重复的音频阶段")
            self._phases.append(key)
            self._tracks[key] = {"generation": 0, "state": "waiting",
                                 "frames": deque(), "live": live or key in self._live,
                                 "published_frames": 0, "published_bytes": 0}

    def publish(self, lease, data):
        if len(data) % 2:
            raise ValueError("PCM frame must have even byte length")
        with self._lock:
            track = self._valid_track(lease)
            index = self._phases.index(lease._key)
            if index < self._cursor:
                raise TTSError("音频阶段已经发布")
            if track["live"] and index == self._cursor:
                self._emit_frame_locked(lease._key, track, data)
            else:
                track["frames"].append(data)

    def commit(self, lease):
        with self._lock:
            self._valid_track(lease)
            track = self._track(lease._key)
            track["state"] = "committed"
            self._drain_locked()
            if track["state"] == "released" and track["published_frames"]:
                fields = {
                    "phase": "line" if isinstance(lease._key, tuple) else lease._key,
                    "audio_frame_count": track["published_frames"],
                    "audio_bytes": track["published_bytes"],
                    "message": "TTS音频已完成发送到WebSocket",
                }
                if isinstance(lease._key, tuple):
                    fields["line_id"] = str(lease._key[1])
                log_event(
                    logger, logging.INFO, "tts_audio_published",
                    context={"job_id": getattr(self._job, "id", None),
                             "project_id": getattr(self._job, "project_id", None)},
                    **fields,
                )

    def abort(self, lease):
        with self._lock:
            if self._cancelled:
                return
            track = self._tracks.get(lease._key)
            if track is None or track["generation"] != lease._generation:
                return
            track["frames"].clear()  # live bytes already on the wire are not reclaimed
            if track["live"] and track["published_frames"]:
                track["state"] = "skipped"
                self._drain_locked()
            else:
                # No bytes reached the client yet, so the caller may reopen
                # this phase and use a whole-file fallback.
                track["state"] = "aborted"

    def skip(self, key):
        """Finish a phase without new audio, allowing the following phase to publish."""
        with self._lock:
            track = self._track(key)
            if track["state"] == "released":
                return
            track["generation"] += 1
            track["frames"].clear()
            track["state"] = "skipped"
            self._drain_locked()

    def cancel(self):
        with self._lock:
            self._cancel_locked()

    def _track(self, key):
        try:
            return self._tracks[key]
        except KeyError as exc:
            raise TTSError("未知音频阶段") from exc

    def _valid_track(self, lease):
        if self._cancelled or self._job.cancel_event.is_set():
            self._cancel_locked()
            raise TTSError("音频发布已取消")
        track = self._track(lease._key)
        if track["generation"] != lease._generation or track["state"] != "open":
            raise TTSError("音频生产者已终止")
        return track

    def _drain_locked(self):
        while self._cursor < len(self._phases):
            track = self._tracks[self._phases[self._cursor]]
            if track["state"] == "open":
                if not track["live"]:
                    return  # buffered phase emits atomically at commit
                # Live head: hand over buffered frames and keep streaming.
                while track["frames"]:
                    self._emit_frame_locked(
                        self._phases[self._cursor], track, track["frames"].popleft()
                    )
                return
            if track["state"] not in ("committed", "skipped"):
                return
            while track["frames"]:
                self._emit_frame_locked(
                    self._phases[self._cursor], track, track["frames"].popleft()
                )
            track["state"] = "released"
            self._cursor += 1

    def _emit_frame_locked(self, key, track, data):
        self._job.emit_bytes(data)
        track["published_frames"] += 1
        track["published_bytes"] += len(data)
        if track["published_frames"] == 1:
            phase = "line" if isinstance(key, tuple) else key
            fields = {
                "phase": phase,
                "audio_bytes": len(data),
                "frame_index": 1,
                "message": "TTS音频首帧已发送到WebSocket",
            }
            if isinstance(key, tuple):
                fields["line_id"] = str(key[1])
            log_event(
                logger, logging.INFO, "tts_audio_frame_published",
                context={"job_id": getattr(self._job, "id", None),
                         "project_id": getattr(self._job, "project_id", None)},
                **fields,
            )

    def _cancel_locked(self):
        self._cancelled = True
        for track in self._tracks.values():
            track["generation"] += 1
            track["frames"].clear()
            if track["state"] != "released":
                track["state"] = "skipped"


class StreamOrchestrator:
    def __init__(self, config, projects=None, registry=None):
        self._configure(config, projects=projects, registry=registry)

    def _configure(self, config, projects=None, registry=None):
        self.config = config
        self.pipeline = Pipeline(config, project_manager=projects)
        if registry is None:
            from ..providers.bootstrap import register_providers_from_config
            register_providers_from_config(config, self.pipeline.registry)
            registry = self.pipeline.registry
        else:
            self.pipeline.registry = registry
        self.registry = registry
        self.projects = self.pipeline.projects
        from ..core.utils import setup_logging
        setup_logging(
            self.config.get("log_level") or "info",
            log_dir=Path(self.config.get("data_dir") or "./.storyteller") / "logs",
        )

    def _send_pcm_file(self, lease, path):
        pcm = audio_file_to_standard_pcm(path)
        for frame in iter_pcm_frames(pcm):
            lease.publish(frame)
        return pcm

    def _llm_name(self):
        names = self.registry.list_llm_names()
        default = self.config.get("llm.default_provider")
        if default in names:
            return default
        if len(names) == 1:
            return names[0]
        if len(names) > 1:
            raise LLMError(
                "Multiple LLM providers are configured; set "
                "STORYTELLER_LLM_PROVIDER or select one in Web settings"
            )
        return None

    def _open_session(self, scheduler, voice, *, directives=None, context=None,
                      phase=None, line_id=None):
        return scheduler.open(
            voice.provider,
            self.registry.get_tts_model(voice),
            voice,
            directives=directives,
            context=context,
            phase=phase,
            line_id=line_id,
        )

    def _fallback_opening_http(self, job, publisher, host, text):
        """Whole-file TTS fallback for an opening whose realtime stream gave no audio.

        Used only when zero opening bytes were played, so the full text can be
        synthesized once without overlapping speech. Returns PCM bytes, or None
        after emitting a warning.
        """
        if not host:
            _emit_stream_warning(
                job, "无可用主持人音色，跳过开场",
                event="opening_voice_unavailable", phase="opening",
            )
            return None
        if not text:
            return None
        _, voice = host
        tmp_path = None
        lease = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".mp3", prefix="opening-")
            os.close(fd)
            self.registry.get_tts(voice.provider).synthesize(text, voice, tmp_path)
            job.emit({"type": "opening_audio_start"})
            lease = publisher.lease("opening")
            pcm = self._send_pcm_file(lease, tmp_path)
            if not pcm:
                raise TTSError("开场兜底语音没有返回音频")
            lease.commit()
            return pcm
        except Exception as exc:
            if lease is not None:
                lease.abort()
            _emit_stream_warning(
                job, "开场语音不可用：{}".format(exc),
                event="opening_fallback_failed", phase="opening", exc=exc,
            )
            return None
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _play_start_notice(
        self, job, scheduler, host, publisher, *, emit_event=True,
        release_event=None,
    ):
        text = start_notice_text()
        if emit_event:
            job.emit({"type": "start_notice", "text": text})
        if not host:
            _emit_stream_warning(
                job, "无可用主持人音色，跳过开播提示",
                event="start_notice_voice_unavailable", phase="start_notice",
            )
            publisher.skip("start_notice")
            return
        _, voice = host
        pump = None
        lease = None
        try:
            lease = publisher.lease("start_notice")
            pump = _AudioPump(
                self._open_session(scheduler, voice, phase="start_notice"), lease
            )
            pump.start()
            pump.session.send_text(text)
            pcm = pump.finish()
            if not pcm:
                raise TTSError("实时 TTS 没有返回音频")
            if release_event is not None:
                release_event.wait()
            lease.commit()
            return
        except Exception as exc:
            if pump is not None:
                pump.cancel()
            elif lease is not None:
                lease.abort()
            _emit_stream_warning(
                job, "开播提示实时语音失败：{}".format(exc),
                event="start_notice_realtime_failed", phase="start_notice", exc=exc,
            )
        fallback = None
        try:
            clip = cached_start_notice(
                self.registry, host,
                Path(self.config.get("data_dir") or ".storyteller") / "web_cache",
            )
            if clip:
                fallback = publisher.lease("start_notice")
                self._send_pcm_file(fallback, clip.mp3_path)
                if release_event is not None:
                    release_event.wait()
                fallback.commit()
                return
        except Exception as exc:
            if fallback is not None:
                fallback.abort()
            _emit_stream_warning(
                job, "开播提示不可用：{}".format(exc),
                event="start_notice_fallback_failed", phase="start_notice", exc=exc,
            )
        publisher.skip("start_notice")

    def run(self, job):
        self._active_state = None
        try:
            if job.config_snapshot is not None:
                config = job.config_snapshot.to_config()
                has_model_override = self._apply_job_model_overrides(config, job)
                self._configure(
                    config,
                    projects=self.projects,
                    registry=None if has_model_override else self.registry,
                )
            elif job.params.llm_model or job.params.tts_model:
                # Refuse to mutate the shared orchestrator config: without a
                # per-job snapshot the model choice would leak into other jobs.
                raise LLMError("缺少任务配置快照，无法应用本次模型选择")
            self._run(job)
        except Exception as exc:
            job.phase = "failed"
            logger.exception(
                "Web streaming job failed: job_id=%s project_id=%s phase=%s",
                job.id, job.project_id, job.phase,
            )
            if self._active_state is not None:
                self._active_state.state = "failed"
                self._active_state.error = str(exc)
                self._active_state.error_at = human_time()
                self.projects.save_project(self._active_state)
            job.emit({"type": "error", "message": str(exc)})

    def _apply_job_model_overrides(self, config, job):
        """Apply per-job model choices to the immutable job configuration."""
        changed = False
        llm_selection = job.params.llm_model
        if llm_selection:
            if isinstance(llm_selection, dict):
                provider = str(llm_selection.get("provider") or "").strip()
                model = str(llm_selection.get("model") or "").strip()
            else:
                provider = str(config.get("llm.default_provider") or "").strip()
                model = str(llm_selection).strip()
            providers = config.get("llm.providers", []) or []
            if not provider and len(providers) == 1:
                provider = str(providers[0])
            if provider not in providers or not model:
                raise LLMError("本次选择的大模型不可用")
            candidates = configured_models(
                config, "llm", provider, include_fallback=False
            )
            if candidates and model not in candidates:
                raise LLMError("本次选择的大模型不在可选模型清单中")
            config.set("llm.default_provider", provider)
            config.set("llm.provider_config.{}.model".format(provider), model)
            changed = True

        audio_selection = job.params.tts_model
        if audio_selection:
            if isinstance(audio_selection, dict):
                selections = [audio_selection]
            elif isinstance(audio_selection, list):
                selections = audio_selection
            else:
                raise TTSError("本次选择的音频模型格式无效")
            providers = config.get("tts.providers", []) or []
            grouped = {}
            for selection in selections:
                if not isinstance(selection, dict):
                    raise TTSError("本次选择的音频模型格式无效")
                provider = str(selection.get("provider") or "").strip()
                model = str(selection.get("model") or "").strip()
                if provider not in providers or not model:
                    raise TTSError("本次选择的音频模型不可用")
                grouped.setdefault(provider, []).append(model)
            if not grouped:
                raise TTSError("本次选择的音频模型不可用")
            for provider, models in grouped.items():
                unique_models = list(dict.fromkeys(models))
                candidates = configured_models(config, "tts", provider)
                if candidates and any(model not in candidates for model in unique_models):
                    raise TTSError("本次选择的音频模型不在可选模型清单中")
                provider_path = "tts.provider_config.{}".format(provider)
                if provider.lower() in ("aliyun", "volcengine"):
                    config.set(
                        "{}.models".format(provider_path),
                        ", ".join(unique_models),
                    )
                    if provider.lower() == "volcengine":
                        config.set(
                            "{}.resource_id_override".format(provider_path),
                            unique_models[0] if len(unique_models) == 1 else None,
                        )
                else:
                    config.set("{}.model".format(provider_path), unique_models[0])
            changed = True
        return changed

    def _run(self, job):
        params = job.params
        job_logger = with_context(logger, job_id=job.id)
        log_event(
            job_logger, logging.INFO, "job_started", topic=params.topic,
            llm_model=params.llm_model, tts_model=params.tts_model,
        )
        tts_names = params.tts_providers or self.config.get("tts.providers") or self.registry.list_tts_names()
        llm_name = self._llm_name()
        if not tts_names or not llm_name:
            raise TTSError("没有可用的 TTS 或 LLM provider")
        state = self.projects.create_project(
            topic=params.topic,
            config={"topic": params.topic, "length": params.length,
                    "complexity": params.complexity,
                    "llm_model": params.llm_model,
                    "tts_model": params.tts_model},
        )
        self._active_state = state
        job.project_id = state.project_id
        job_logger = with_context(job_logger, project_id=state.project_id)
        log_event(job_logger, logging.INFO, "project_created", topic=params.topic)

        scheduler = TTSScheduler(self.registry, self.config)
        host = choose_host_voice(self.registry, tts_names, self.config.get("web.filler_voice"))
        publisher = _OrderedAudioPublisher(job, ["opening", "start_notice"])
        voice_matching_thread = None
        voice_matching_result = None
        voice_matching_error = None
        start_notice_thread = None
        start_notice_announced = False
        start_notice_release = threading.Event()
        opening_pump = None
        opening_lease = None
        opening_finalize_thread = None
        opening_failed = False
        opening_streamed = False
        opening_committed = False
        opening_text = ""
        opening_first_delta_logged = False
        script_preview_count = 0
        script_started = time.perf_counter()
        line_coordinator = _IncrementalLineCoordinator(
            self, job, publisher, scheduler, {}
        )

        def fail_opening(exc=None):
            # Stop the realtime attempt but defer releasing the phase until the
            # script is known: a failure before any audio can then fall back to
            # whole-file TTS using the complete opening text.
            nonlocal opening_failed, opening_pump, opening_lease
            if opening_failed:
                return
            opening_failed = True
            if opening_pump is not None:
                opening_pump.cancel()
                opening_pump = None
            elif opening_lease is not None:
                opening_lease.abort()
                opening_lease = None
            if exc is not None:
                _emit_stream_warning(
                    job,
                    "开场实时语音失败，尝试整句兜底：{}".format(exc),
                    event="opening_realtime_failed",
                    phase="opening",
                    exc=exc,
                )

        def finalize_opening():
            # Request FINISH as soon as the opening text is complete, but do not
            # block the LLM streaming callback while the provider drains audio.
            # The caller joins this thread before moving to the post-script stage.
            nonlocal opening_finalize_thread
            if (opening_committed or opening_failed or opening_pump is None
                    or opening_finalize_thread is not None):
                return

            def finish_in_background():
                nonlocal opening_committed, opening_pump, opening_lease
                pump = opening_pump
                lease = opening_lease
                try:
                    opening_pcm = pump.finish()
                    if not opening_pcm:
                        raise TTSError("实时 TTS 没有返回音频")
                    lease.commit()
                    job.emit({"type": "opening_audio_end",
                              "duration_ms": pcm_duration_ms(opening_pcm)})
                    opening_committed = True
                except Exception as exc:
                    fail_opening(exc)

            opening_finalize_thread = threading.Thread(
                target=finish_in_background,
                name="opening-tts-finish",
                daemon=True,
            )
            opening_finalize_thread.start()

        def mark_opening_started():
            nonlocal opening_streamed
            opening_streamed = True
            job.emit({"type": "opening_audio_start"})

        def emit_script_preview_event(event, source):
            nonlocal script_preview_count
            script_preview_count += 1
            job.script_preview = event
            job.emit(event)
            log_event(
                job_logger, logging.DEBUG, "script_preview_emitted",
                phase="script", preview_index=script_preview_count,
                source=source, title=event.get("title") or "",
                opening_length=len(event.get("opening") or ""),
                character_count=len(event.get("characters") or []),
                line_count=len(event.get("lines") or []),
            )

        def emit_opening_delta(text):
            nonlocal opening_pump, opening_lease, opening_text
            nonlocal opening_first_delta_logged
            if not text or opening_committed:
                return
            opening_text += text
            if not opening_first_delta_logged:
                log_event(
                    job_logger, logging.INFO, "opening_first_delta_received",
                    phase="script", text_length=len(text),
                    time_since_script_start_ms=int(
                        (time.perf_counter() - script_started) * 1000
                    ),
                )
                opening_first_delta_logged = True
            # StoryGenerator reports opening deltas before its first preview.  Emit a
            # minimal preview here so opening audio can never overtake the preview.
            if not job.script_preview or job.script_preview.get("opening") != opening_text:
                event = _script_preview_event({"opening": opening_text})
                emit_script_preview_event(event, "opening_delta")
            job.emit({"type": "opening_text_delta", "text": text})
            if opening_failed:
                return  # keep accumulating text for the post-script HTTP fallback
            if opening_pump is None:
                if not host:
                    fail_opening()
                    return
                try:
                    opening_lease = publisher.lease("opening")
                    opening_pump = _AudioPump(
                        self._open_session(scheduler, host[1], phase="opening"), opening_lease,
                        on_first_audio=mark_opening_started,
                    )
                    opening_pump.start()
                except Exception as exc:
                    fail_opening(exc)
                    return
            try:
                opening_pump.session.send_text(text)
            except Exception as exc:
                fail_opening(exc)

        job.phase = "script"
        job.emit({"type": "status", "phase": "script", "message": "正在生成剧本…"})
        llm = self.registry.get_llm(llm_name)

        def run_voice_matching(script):
            return VoiceMatcher(
                self.registry, llm=llm,
                mode=self.config.get("voice_matcher") or "rule",
                log_context={"job_id": job.id, "project_id": state.project_id,
                             "phase": "voices"},
            ).match_voices(script, allowed_providers=tts_names)

        def start_start_notice(*, announce=False):
            nonlocal start_notice_thread, start_notice_announced
            if start_notice_thread is not None:
                if announce and not start_notice_announced:
                    job.emit({"type": "start_notice", "text": start_notice_text()})
                    start_notice_announced = True
                    start_notice_release.set()
                return
            start_notice_thread = threading.Thread(
                target=self._play_start_notice,
                args=(job, scheduler, host, publisher),
                kwargs={"emit_event": False, "release_event": start_notice_release},
                name="start-notice-tts", daemon=True,
            )
            start_notice_thread.start()
            log_event(
                job_logger, logging.INFO, "start_notice_dispatched",
                phase="script", message="主持人音色已确定，开播提示开始后台合成",
            )
            if announce:
                job.emit({"type": "start_notice", "text": start_notice_text()})
                start_notice_announced = True
                start_notice_release.set()

        def start_voice_matching(preview):
            nonlocal voice_matching_thread, voice_matching_result, voice_matching_error
            if voice_matching_thread is not None:
                return
            provisional = _script_from_json(
                {
                    "title": preview.get("title") or "",
                    "characters": preview.get("characters") or [],
                    "lines": [],
                },
                params.topic,
            )
            line_coordinator.names = {
                character.id: character.name for character in provisional.characters
            }

            def match_in_background():
                nonlocal voice_matching_result, voice_matching_error
                try:
                    voice_matching_result = run_voice_matching(provisional)
                    line_coordinator.set_provisional_voice_context(voice_matching_result)
                    matched_event = _characters_matched_event(voice_matching_result, self.registry)
                    job.characters_matched = matched_event
                    job.emit(matched_event)
                except Exception as exc:
                    voice_matching_error = exc
                    log_event(
                        job_logger,
                        logging.ERROR,
                        "voice_matching_failed",
                        phase="script",
                        error_type=type(exc).__name__,
                        exception_message=_safe_exception_message(exc),
                    )

            voice_matching_thread = threading.Thread(
                target=match_in_background, name="voice-matching", daemon=True,
            )
            voice_matching_thread.start()
            log_event(
                job_logger, logging.INFO, "voice_matching_dispatched",
                phase="script", character_count=len(provisional.characters),
            )
            # The audio was synthesized as soon as the host voice was known;
            # announce it to the client only when character voice matching starts.
            start_start_notice(announce=True)

        def emit_script_preview(preview):
            event = _script_preview_event(preview)
            emit_script_preview_event(event, "llm_snapshot")

        # Host voice selection is already complete before script streaming
        # begins. Start notice synthesis immediately; its audio remains buffered
        # by the ordered publisher until it is allowed to reach the client.
        start_start_notice()

        try:
            with timed_event(job_logger, "script_generation", phase="script", topic=params.topic):
                state.script = StoryGenerator(llm).generate_script_stream(
                    params.topic, params.length, params.complexity,
                    with_sound=bool(params.with_sound),
                    on_preview=emit_script_preview,
                    on_opening_delta=emit_opening_delta,
                    on_opening_complete=finalize_opening,
                    on_characters_ready=start_voice_matching,
                    on_line_text_delta=line_coordinator.on_delta,
                    on_line_complete=line_coordinator.on_complete,
                )
        except Exception:
            if opening_pump is not None:
                opening_pump.cancel()
            start_notice_release.set()
            publisher.cancel()
            raise

        finalize_opening()
        if opening_finalize_thread is not None:
            opening_finalize_thread.join()

        if not opening_committed:
            if opening_streamed:
                # Partial opening audio already reached the client; synthesizing
                # again would overlap speech, so release what was played and move on.
                publisher.skip("opening")
                job.emit({"type": "opening_audio_abort"})
            else:
                pcm = self._fallback_opening_http(job, publisher, host, opening_text)
                if pcm:
                    job.emit({"type": "opening_audio_end", "duration_ms": pcm_duration_ms(pcm)})
                else:
                    publisher.skip("opening")
                    if opening_text:
                        job.emit({"type": "opening_audio_abort"})

        state.state = "script_generated"
        self.projects.save_project(state)
        self.projects.rename_for_title(state)
        self.pipeline._export_script(state)
        if job.cancel_event.is_set():
            publisher.cancel()
            job.phase = "canceled"; job.emit({"type": "canceled"}); return

        job.phase = "voices"
        job.emit({"type": "status", "phase": "voices", "message": "正在匹配音色…"})
        if voice_matching_thread is None:
            voice_matching_result = run_voice_matching(state.script)
        else:
            voice_matching_thread.join()
            if voice_matching_error is not None:
                start_notice_release.set()
                raise voice_matching_error
            matched_by_id = {
                character.id: character.voice_config
                for character in voice_matching_result.characters
            }
            for character in state.script.characters:
                character.voice_config = matched_by_id.get(character.id)
        state.state = "voice_configured"
        self.projects.save_project(state)
        self.pipeline._export_script(state)

        char_map = {c.id: c.voice_config for c in state.script.characters if c.voice_config}
        narrator = self.pipeline._find_narrator_voice(state.script, char_map)
        line_coordinator.apply_final_line_voices(state.script, char_map, narrator)
        names = {c.id: c.name for c in state.script.characters}
        script_ready = {"type": "script_ready", "title": state.script.title,
                        "total": len(state.script.lines),
                        "characters": _characters_matched_event(state.script, self.registry)["characters"],
                        "lines": [{"line_id": l.line_id, "line_type": l.line_type,
                                   "character_id": l.character_id,
                                   "speaker": names.get(l.character_id) or ("旁白" if l.line_type == "narration" else "未知角色"),
                                   "text": l.text}
                                  for l in state.script.lines]}
        job.script_ready = script_ready
        job.emit(script_ready)
        log_event(job_logger, logging.INFO, "script_ready_sent", phase="voices", line_count=len(state.script.lines))
        # Character matching normally announces this earlier; keep the
        # announcement for scripts without characters as a safe fallback.
        start_start_notice(announce=True)
        start_notice_thread.join()

        if job.cancel_event.is_set():
            publisher.cancel()
            job.phase = "canceled"; job.emit({"type": "canceled"}); return
        job.phase = "line"; job.total = len(state.script.lines)
        sound_provider = sound_library = None
        with_sound = bool(params.with_sound)
        if with_sound:
            try:
                sound_provider = self.pipeline._get_sound_provider()
                sound_library = self.pipeline._get_sound_library()
            except Exception as exc:
                _emit_stream_warning(
                    job, "音效不可用：{}".format(exc),
                    event="sound_provider_unavailable", phase="line", exc=exc,
                )
                with_sound = False
        refs, line_paths = set(), []
        for index, line in enumerate(state.script.lines, 1):
            if job.cancel_event.is_set():
                publisher.cancel()
                state.state = "generating_audio"; self.projects.save_project(state)
                job.phase = "canceled"; job.emit({"type": "canceled"}); return
            voice = self.pipeline.voice_for_line(line, char_map, narrator)
            if not voice:
                publisher.skip(("line", index))
                _emit_stream_warning(
                    job, "无可用音色", event="line_voice_unavailable",
                    phase="line", line_id=line.line_id,
                )
                continue
            has_cues = with_sound and bool(line.sound_effects or line.background_music)
            incremental = line_coordinator.get(index - 1)
            if incremental is None:
                publisher.add_phase(("line", index), live=True)
            job.line_index = index
            if incremental is None:
                job.emit({"type": "line_start", "line_id": line.line_id, "index": index,
                          "total": job.total, "speaker": names.get(line.character_id) or line.line_type,
                          "text": line.text, "has_sound": has_cues})
                job.emit({"type": "line_text_delta", "line_id": line.line_id, "index": index,
                          "text": line.text})
            out = self.pipeline._audio_path(state.project_id, line.line_id, "mp3")
            directives, context = self.pipeline.line_context_directives(state.script.lines, index - 1)
            tts_timing = line.processing.setdefault("tts", {})
            tts_timing["started_at"] = human_time()
            streamed = False
            realtime_audio_published = False
            pump = None
            lease = None
            try:
                with timed_event(job_logger, "tts_line", phase="line", line_id=line.line_id,
                                 provider=voice.provider, index=index):
                    incremental_attempted = incremental is not None
                    if incremental_attempted:
                        try:
                            pcm, incremental_error = line_coordinator.wait(index - 1)
                            if pcm:
                                realtime_audio_published = True
                            if incremental_error is not None:
                                raise TTSError(str(incremental_error))
                            if not pcm:
                                raise TTSError("实时 TTS 没有返回音频")
                            pcm_to_mp3_file(pcm, out)
                            streamed = True
                        except Exception as exc:
                            _emit_stream_warning(
                                job,
                                "实时语音降级：{}".format(exc),
                                event="tts_line_realtime_fallback",
                                phase="line", line_id=line.line_id, exc=exc,
                            )
                    if not streamed and not incremental_attempted and not has_cues:
                        try:
                            lease = publisher.lease(("line", index))
                            pump = _AudioPump(
                                self._open_session(
                                    scheduler, voice, directives=directives,
                                    context=context, phase="line", line_id=line.line_id,
                                ),
                                lease,
                            )
                            pump.start()
                            pump.session.send_text(line.text)
                            pcm = pump.finish()
                            if not pcm:
                                raise TTSError("实时 TTS 没有返回音频")
                            lease.commit()
                            pcm_to_mp3_file(pcm, out)
                            streamed = True
                            realtime_audio_published = True
                        except Exception as exc:
                            if pump is not None and pump.pcm:
                                realtime_audio_published = True
                            if pump is not None:
                                pump.cancel()
                            elif lease is not None:
                                lease.abort()
                            _emit_stream_warning(
                                job,
                                "实时语音降级：{}".format(exc),
                                event="tts_line_realtime_fallback",
                                phase="line", line_id=line.line_id, exc=exc,
                            )
                    if not streamed:
                        self.registry.get_tts(voice.provider).synthesize(
                            line.text, voice, out, directives=directives, context=context)
                tts_timing["ended_at"] = human_time()
                if has_cues:
                    from .mixes import mix_line_with_cues
                    from pydub import AudioSegment
                    duration = len(AudioSegment.from_file(str(out))) / 1000.0
                    entries = self.pipeline.materialize_line_cues(
                        state, line, duration, sound_provider, sound_library, refs)
                    if entries:
                        mix_started = human_time()
                        try:
                            mix_line_with_cues(out, entries, out)
                        finally:
                            line.processing["mixing"] = {"started_at": mix_started, "ended_at": human_time()}
                if not realtime_audio_published:
                    fallback = publisher.lease(("line", index))
                    self._send_pcm_file(fallback, out)
                    fallback.commit()
                line.audio_path = str(out); line_paths.append(str(out))
                from pydub import AudioSegment
                duration_ms = len(AudioSegment.from_file(str(out)))
                job.emit({"type": "line_end", "line_id": line.line_id, "duration_ms": duration_ms})
            except Exception as exc:
                if tts_timing.get("started_at") and not tts_timing.get("ended_at"):
                    tts_timing["ended_at"] = human_time()
                publisher.skip(("line", index))
                _emit_stream_warning(
                    job, str(exc), event="tts_line_failed",
                    phase="line", line_id=line.line_id, exc=exc,
                )
        if not line_paths:
            raise TTSError("没有成功生成任何音频行")
        self.projects.save_project(state)
        job.phase = "finalizing"; job.emit({"type": "finalizing"})
        output = self.pipeline.finalize_audio(state, line_paths, "mp3", with_sound=with_sound)
        from pydub import AudioSegment
        duration_ms = len(AudioSegment.from_file(str(output)))
        job.phase = "completed"
        job.emit({"type": "complete", "project_id": state.project_id,
                  "title": state.script.title,
                  "audio_url": "/api/stories/{}/audio".format(state.project_id),
                  "script_url": "/api/stories/{}".format(state.project_id),
                  "duration_ms": duration_ms})
