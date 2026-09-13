from __future__ import annotations

from pathlib import Path
import logging

from ..core.exceptions import TTSError
from ..core.pipeline import Pipeline
from ..core.story_generator import StoryGenerator
from ..core.voice_matcher import VoiceMatcher
from ..core.tts import CHUNK_AUDIO, STREAM_SAMPLE_RATE
from .fillers import FillerPrefetcher
from .tts_chunks import audio_file_to_standard_pcm, iter_pcm_frames, pcm_to_mp3_file, pcm_duration_ms
from ..core.pipeline import human_time

logger = logging.getLogger(__name__)


class StreamOrchestrator:
    def __init__(self, config, projects=None, registry=None):
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

    def _send_pcm_file(self, job, path):
        pcm = audio_file_to_standard_pcm(path)
        for frame in iter_pcm_frames(pcm):
            job.emit_bytes(frame)
        return pcm

    def _llm_name(self):
        names = self.registry.list_llm_names()
        default = self.config.get("llm.default_provider")
        return default if default in names else (names[0] if names else None)

    def run(self, job):
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
        fillers = FillerPrefetcher(
            self.registry, llm_name, tts_names,
            str(Path(self.config.get("data_dir")) / "web_cache"),
            self.config.get("web.filler_voice"),
        )
        try:
            job.phase = "script"
            job.emit({"type": "status", "phase": "script", "message": "正在生成剧本…"})
            thinking_started = False
            thinking_audio_sent = False
            thinking_closed = False
            def emit_thinking_text(text):
                nonlocal thinking_started
                if thinking_closed:
                    return
                thinking_started = True
                job.emit({"type": "filler_start", "kind": "thinking", "text": text})
            def emit_thinking_audio(clip):
                nonlocal thinking_audio_sent
                if thinking_closed or thinking_audio_sent:
                    return
                pcm = self._send_pcm_file(job, clip.mp3_path)
                thinking_audio_sent = True
                job.emit({"type": "filler_end", "kind": "thinking", "duration_ms": pcm_duration_ms(pcm)})
            fillers.start(params.topic, on_thinking_text=emit_thinking_text,
                          on_thinking_ready=emit_thinking_audio)
            llm = self.registry.get_llm(llm_name)
            state.script = StoryGenerator(llm).generate_script(
                params.topic, params.length, params.complexity,
                with_sound=bool(params.with_sound))
            state.state = "script_generated"
            self.projects.save_project(state)
            self.projects.rename_for_title(state)
            self.pipeline._export_script(state)
            if job.cancel_event.is_set():
                job.phase = "canceled"; job.emit({"type": "canceled"}); return

            thinking_sent = False
            thinking = fillers.get("thinking", timeout=0)
            if thinking and not thinking_audio_sent:
                pcm = self._send_pcm_file(job, thinking.mp3_path)
                thinking_audio_sent = True
                job.emit({"type": "filler_end", "kind": "thinking", "duration_ms": pcm_duration_ms(pcm)})
                thinking_sent = True
            else:
                thinking_sent = thinking_audio_sent

            job.phase = "voices"
            job.emit({"type": "status", "phase": "voices", "message": "正在匹配音色…"})
            VoiceMatcher(self.registry, llm=llm,
                         mode=self.config.get("voice_matcher") or "rule").match_voices(
                             state.script, allowed_providers=tts_names)
            state.state = "voice_configured"
            self.projects.save_project(state)
            self.pipeline._export_script(state)
            if not thinking_sent and not thinking_started:
                thinking = fillers.get("thinking", timeout=0)
                if thinking:
                    job.emit({"type": "filler_start", "kind": "thinking", "text": thinking.text})
                    thinking_started = True
                    pcm = self._send_pcm_file(job, thinking.mp3_path)
                    thinking_audio_sent = True
                    job.emit({"type": "filler_end", "kind": "thinking", "duration_ms": pcm_duration_ms(pcm)})
                    thinking_sent = True
            if thinking_started and not thinking_sent:
                thinking_closed = True
                job.emit({"type": "filler_abort", "kind": "thinking"})

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
            intro = fillers.get("intro", timeout=0)
            if intro:
                job.emit({"type": "filler_start", "kind": "intro", "text": intro.text})
                pcm = self._send_pcm_file(job, intro.mp3_path)
                job.emit({"type": "filler_end", "kind": "intro", "duration_ms": pcm_duration_ms(pcm)})
        finally:
            fillers.shutdown()

        if job.cancel_event.is_set():
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
                state.state = "generating_audio"; self.projects.save_project(state)
                job.phase = "canceled"; job.emit({"type": "canceled"}); return
            voice = self.pipeline.voice_for_line(line, char_map, narrator)
            if not voice:
                job.emit({"type": "warning", "line_id": line.line_id, "message": "无可用音色"}); continue
            has_cues = with_sound and bool(line.sound_effects or line.background_music)
            job.line_index = index
            job.emit({"type": "line_start", "line_id": line.line_id, "index": index,
                      "total": job.total, "speaker": names.get(line.character_id) or line.line_type,
                      "text": line.text, "has_sound": has_cues})
            out = self.pipeline._audio_path(state.project_id, line.line_id, "mp3")
            directives, context = self.pipeline.line_context_directives(state.script.lines, index - 1)
            try:
                stream = self.registry.get_stream_tts(voice.provider)
                tts_timing = line.processing.setdefault("tts", {})
                tts_timing["started_at"] = human_time()
                streamed = stream is not None and not has_cues
                if streamed:
                    buf = bytearray()
                    for chunk in stream.stream_synthesize(line.text, voice, directives=directives, context=context):
                        if chunk.kind != CHUNK_AUDIO:
                            continue
                        if len(chunk.data) % 2:
                            raise ValueError("PCM frame must have even byte length")
                        job.emit_bytes(chunk.data); buf.extend(chunk.data)
                    pcm_to_mp3_file(bytes(buf), out)
                else:
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
                    self._send_pcm_file(job, out)
                line.audio_path = str(out); line_paths.append(str(out))
                from pydub import AudioSegment
                duration_ms = len(AudioSegment.from_file(str(out)))
                job.emit({"type": "line_end", "line_id": line.line_id, "duration_ms": duration_ms})
            except Exception as exc:
                if "tts_timing" in locals() and tts_timing.get("started_at") and not tts_timing.get("ended_at"):
                    tts_timing["ended_at"] = human_time()
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
