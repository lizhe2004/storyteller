from __future__ import annotations

from collections import deque
from pathlib import Path
import logging
import threading

from ..core.exceptions import TTSError
from ..core.pipeline import Pipeline, human_time
from ..core.story_generator import StoryGenerator
from ..core.tts import CHUNK_AUDIO, STREAM_SAMPLE_RATE
from ..core.voice_matcher import VoiceMatcher
from .fillers import cached_start_notice, choose_host_voice, start_notice_text
from .tts_chunks import audio_file_to_standard_pcm, iter_pcm_frames, pcm_duration_ms, pcm_to_mp3_file
from .tts_scheduler import TTSScheduler
from ..core.observability import log_event, timed_event, with_context

logger = logging.getLogger(__name__)


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
    """Bounded, all-or-nothing PCM publication in opening/notice/line order."""

    def __init__(self, job, phases, max_frames=64):
        self._job = job
        self._phases = list(phases)
        self._tracks = {
            key: {"generation": 0, "state": "waiting", "frames": deque()}
            for key in self._phases
        }
        self._max_frames = max(1, int(max_frames))
        self._cursor = 0
        self._cancelled = False
        self._lock = threading.Lock()

    def lease(self, key):
        with self._lock:
            track = self._track(key)
            if self._cancelled or self._job.cancel_event.is_set():
                self._cancel_locked()
                raise TTSError("音频发布已取消")
            if track["state"] == "open":
                raise TTSError("音频阶段已有活动生产者")
            if track["state"] in ("committed", "released"):
                raise TTSError("音频阶段已经完成")
            track["generation"] += 1
            track["state"] = "open"
            track["frames"].clear()
            return _AudioLease(self, key, track["generation"])

    def add_phase(self, key):
        with self._lock:
            if key in self._tracks:
                raise TTSError("重复的音频阶段")
            self._phases.append(key)
            self._tracks[key] = {"generation": 0, "state": "waiting", "frames": deque()}

    def publish(self, lease, data):
        if len(data) % 2:
            raise ValueError("PCM frame must have even byte length")
        with self._lock:
            track = self._valid_track(lease)
            if len(track["frames"]) >= self._max_frames:
                raise TTSError("有序音频发布缓冲区已满")
            track["frames"].append(data)

    def commit(self, lease):
        with self._lock:
            track = self._valid_track(lease)
            track["state"] = "committed"
            self._flush_ready_locked()

    def abort(self, lease):
        with self._lock:
            if self._cancelled:
                return
            track = self._tracks.get(lease._key)
            if track is None or track["generation"] != lease._generation:
                return
            track["frames"].clear()
            track["state"] = "aborted"

    def skip(self, key):
        """Finish a phase without audio, allowing the following phase to publish."""
        with self._lock:
            track = self._track(key)
            if track["state"] == "released":
                return
            track["generation"] += 1
            track["frames"].clear()
            track["state"] = "skipped"
            self._flush_ready_locked()

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

    def _flush_ready_locked(self):
        while self._cursor < len(self._phases):
            track = self._tracks[self._phases[self._cursor]]
            if track["state"] not in ("committed", "skipped"):
                return
            if track["state"] == "committed":
                for frame in track["frames"]:
                    self._job.emit_bytes(frame)
            track["frames"].clear()
            track["state"] = "released"
            self._cursor += 1

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
        return default if default in names else (names[0] if names else None)

    def _open_session(self, scheduler, voice, *, directives=None, context=None):
        return scheduler.open(
            voice.provider,
            self.registry.get_tts_model(voice),
            voice,
            directives=directives,
            context=context,
        )

    def _play_start_notice(self, job, scheduler, host, publisher):
        text = start_notice_text()
        job.emit({"type": "start_notice", "text": text})
        if not host:
            job.emit({"type": "warning", "message": "无可用主持人音色，跳过开播提示"})
            publisher.skip("start_notice")
            return
        _, voice = host
        pump = None
        lease = None
        try:
            lease = publisher.lease("start_notice")
            pump = _AudioPump(self._open_session(scheduler, voice), lease)
            pump.start()
            pump.session.send_text(text)
            pcm = pump.finish()
            if not pcm:
                raise TTSError("实时 TTS 没有返回音频")
            lease.commit()
            return
        except Exception as exc:
            if pump is not None:
                pump.cancel()
            elif lease is not None:
                lease.abort()
            job.emit({"type": "warning", "message": "开播提示实时语音失败：{}".format(exc)})
        fallback = None
        try:
            clip = cached_start_notice(
                self.registry, host,
                Path(self.config.get("data_dir") or ".storyteller") / "web_cache",
            )
            if clip:
                fallback = publisher.lease("start_notice")
                self._send_pcm_file(fallback, clip.mp3_path)
                fallback.commit()
                return
        except Exception as exc:
            if fallback is not None:
                fallback.abort()
            job.emit({"type": "warning", "message": "开播提示不可用：{}".format(exc)})
        publisher.skip("start_notice")

    def run(self, job):
        if job.config_snapshot is not None:
            self._configure(job.config_snapshot.to_config())
        self._active_state = None
        try:
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

    def _run(self, job):
        params = job.params
        job_logger = with_context(logger, job_id=job.id)
        log_event(job_logger, logging.INFO, "job_started", topic=params.topic)
        job.emit({"type": "ready", "audio": {"encoding": "pcm_s16le",
                  "sample_rate": STREAM_SAMPLE_RATE, "channels": 1}})
        tts_names = params.tts_providers or self.config.get("tts.providers") or self.registry.list_tts_names()
        llm_name = self._llm_name()
        if not tts_names or not llm_name:
            raise TTSError("没有可用的 TTS 或 LLM provider")
        state = self.projects.create_project(
            topic=params.topic,
            config={"topic": params.topic, "length": params.length,
                    "complexity": params.complexity},
        )
        self._active_state = state
        job.project_id = state.project_id
        job_logger = with_context(job_logger, project_id=state.project_id)
        log_event(job_logger, logging.INFO, "project_created", topic=params.topic)

        scheduler = TTSScheduler(self.registry, self.config)
        host = choose_host_voice(self.registry, tts_names, self.config.get("web.filler_voice"))
        publisher = _OrderedAudioPublisher(job, ["opening", "start_notice"])
        opening_pump = None
        opening_lease = None
        opening_aborted = False
        opening_text = ""

        def abort_opening(exc=None):
            nonlocal opening_aborted, opening_pump, opening_lease
            if opening_aborted:
                return
            opening_aborted = True
            if opening_pump is not None:
                opening_pump.cancel()
            elif opening_lease is not None:
                opening_lease.abort()
            publisher.skip("opening")
            if exc is not None:
                job.emit({"type": "warning", "message": "开场实时语音失败：{}".format(exc)})
            job.emit({"type": "opening_audio_abort"})

        def emit_opening_delta(text):
            nonlocal opening_pump, opening_lease, opening_text
            if opening_aborted or not text:
                return
            opening_text += text
            # StoryGenerator reports opening deltas before its first preview.  Emit a
            # minimal preview here so opening audio can never overtake the preview.
            if not job.script_preview or job.script_preview.get("opening") != opening_text:
                event = _script_preview_event({"opening": opening_text})
                job.script_preview = event
                job.emit(event)
            job.emit({"type": "opening_text_delta", "text": text})
            if opening_pump is None:
                if not host:
                    abort_opening()
                    return
                try:
                    opening_lease = publisher.lease("opening")
                    opening_pump = _AudioPump(
                        self._open_session(scheduler, host[1]), opening_lease,
                        on_first_audio=lambda: job.emit({"type": "opening_audio_start"}),
                    )
                    opening_pump.start()
                except Exception as exc:
                    abort_opening(exc)
                    return
            try:
                opening_pump.session.send_text(text)
            except Exception as exc:
                abort_opening(exc)

        job.phase = "script"
        job.emit({"type": "status", "phase": "script", "message": "正在生成剧本…"})
        llm = self.registry.get_llm(llm_name)

        def emit_script_preview(preview):
            event = _script_preview_event(preview)
            job.script_preview = event
            job.emit(event)

        try:
            with timed_event(job_logger, "script_generation", phase="script", topic=params.topic):
                state.script = StoryGenerator(llm).generate_script_stream(
                    params.topic, params.length, params.complexity,
                    with_sound=bool(params.with_sound),
                    on_preview=emit_script_preview,
                    on_opening_delta=emit_opening_delta,
                )
        except Exception:
            if opening_pump is not None:
                opening_pump.cancel()
            publisher.cancel()
            raise

        if opening_pump is not None and not opening_aborted:
            try:
                opening_pcm = opening_pump.finish()
                if not opening_pcm:
                    raise TTSError("实时 TTS 没有返回音频")
                opening_lease.commit()
                job.emit({"type": "opening_audio_end", "duration_ms": pcm_duration_ms(opening_pcm)})
            except Exception as exc:
                abort_opening(exc)
        elif not opening_aborted:
            publisher.skip("opening")

        for index, _ in enumerate(state.script.lines, 1):
            publisher.add_phase(("line", index))

        state.state = "script_generated"
        self.projects.save_project(state)
        self.projects.rename_for_title(state)
        self.pipeline._export_script(state)
        if job.cancel_event.is_set():
            publisher.cancel()
            job.phase = "canceled"; job.emit({"type": "canceled"}); return

        job.phase = "voices"
        job.emit({"type": "status", "phase": "voices", "message": "正在匹配音色…"})
        with timed_event(job_logger, "voice_matching", phase="voices"):
            VoiceMatcher(self.registry, llm=llm,
                         mode=self.config.get("voice_matcher") or "rule",
                         log_context={"job_id": job.id, "project_id": state.project_id,
                                      "phase": "voices"}).match_voices(
                             state.script, allowed_providers=tts_names)
        state.state = "voice_configured"
        self.projects.save_project(state)
        self.pipeline._export_script(state)

        char_map = {c.id: c.voice_config for c in state.script.characters if c.voice_config}
        narrator = self.pipeline._find_narrator_voice(state.script, char_map)
        names = {c.id: c.name for c in state.script.characters}
        script_ready = {"type": "script_ready", "title": state.script.title,
                        "total": len(state.script.lines),
                        "characters": [{"id": c.id, "name": c.name,
                                        "description": c.description,
                                        "voice": ({"provider": c.voice_config.provider,
                                                   "voice_id": c.voice_config.voice_id,
                                                   "name": c.voice_config.name}
                                                  if c.voice_config else None)}
                                       for c in state.script.characters],
                        "lines": [{"line_id": l.line_id, "line_type": l.line_type,
                                   "character_id": l.character_id,
                                   "speaker": names.get(l.character_id) or ("旁白" if l.line_type == "narration" else "未知角色"),
                                   "text": l.text}
                                  for l in state.script.lines]}
        job.script_ready = script_ready
        job.emit(script_ready)
        log_event(job_logger, logging.INFO, "script_ready_sent", phase="voices", line_count=len(state.script.lines))
        self._play_start_notice(job, scheduler, host, publisher)

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
                job.emit({"type": "warning", "message": "音效不可用：{}".format(exc)})
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
                job.emit({"type": "warning", "line_id": line.line_id, "message": "无可用音色"}); continue
            has_cues = with_sound and bool(line.sound_effects or line.background_music)
            job.line_index = index
            job.emit({"type": "line_start", "line_id": line.line_id, "index": index,
                      "total": job.total, "speaker": names.get(line.character_id) or line.line_type,
                      "text": line.text, "has_sound": has_cues})
            # The parser currently yields formal lines only after the script is complete;
            # this is therefore the first safe point to submit their text after voice assignment.
            job.emit({"type": "line_text_delta", "line_id": line.line_id, "index": index,
                      "text": line.text})
            out = self.pipeline._audio_path(state.project_id, line.line_id, "mp3")
            directives, context = self.pipeline.line_context_directives(state.script.lines, index - 1)
            tts_timing = line.processing.setdefault("tts", {})
            tts_timing["started_at"] = human_time()
            streamed = False
            pump = None
            lease = None
            try:
                with timed_event(job_logger, "tts_line", phase="line", line_id=line.line_id,
                                 provider=voice.provider, index=index):
                    if not has_cues:
                        try:
                            lease = publisher.lease(("line", index))
                            pump = _AudioPump(
                                self._open_session(scheduler, voice, directives=directives, context=context),
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
                        except Exception as exc:
                            if pump is not None:
                                pump.cancel()
                            elif lease is not None:
                                lease.abort()
                            job.emit({"type": "warning", "line_id": line.line_id,
                                      "message": "实时语音降级：{}".format(exc)})
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
                if not streamed:
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
                job.emit({"type": "warning", "line_id": line.line_id, "message": str(exc)})
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
