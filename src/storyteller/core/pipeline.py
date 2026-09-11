from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .exceptions import LLMError, TTSError
from .project import ProjectManager, _script_to_dict
from .story_generator import StoryGenerator

# Script SoundEffect.type -> SoundLibrary kind.
_KIND_FOR_TYPE = {"effect": "sfx", "ambient": "ambient", "music": "music"}


class Pipeline:
    """Orchestrates the full story-to-audio workflow.

    Coordinates project management, script generation, voice matching,
    TTS synthesis, audio concatenation, and format conversion.
    """

    def __init__(
        self,
        config,
        project_manager=None,
        sound_provider=None,
        sound_library=None,
    ):
        self.config = config
        from ..providers.registry import ProviderRegistry

        self.registry = ProviderRegistry(config)
        self.projects = project_manager or ProjectManager(
            config.get("project_dir") or "./.storyteller/stories"
        )
        # Injected (typically by tests); real ones are built lazily so that
        # with sound disabled, no key/provider is ever required.
        self._sound_provider = sound_provider
        self._sound_library = sound_library

    # ----- public entry points -----
    def run(self, topic, length="medium", complexity="simple", **kwargs):
        """Run a fresh pipeline from topic to audio output."""
        self._setup_logging()
        state = self.projects.create_project(
            topic=topic,
            config={"length": length, "complexity": complexity},
        )
        return self._execute_pipeline(state, **kwargs)

    def resume(self, project_id, **kwargs):
        """Resume an existing project from whatever state it's in."""
        self._setup_logging()
        state = self.projects.load_project(project_id)
        if state.state == "completed":
            output = self._find_final_output(project_id)
            if output:
                return str(output)
            raise RuntimeError("No output found for completed project")
        return self._execute_pipeline(state, **kwargs)

    def draft_script(self, topic, length="medium", complexity="simple"):
        """Generate only a script: persist project state and export the
        script JSON, without voice matching or audio synthesis.

        Returns ``(script, script_path)``.
        """
        self._setup_logging()
        state = self.projects.create_project(
            topic=topic,
            config={"length": length, "complexity": complexity},
        )
        llm = self._get_default_llm()
        state.script = StoryGenerator(llm).generate_script(
            topic, length, complexity, with_sound=self._sound_enabled()
        )
        state.state = "script_generated"
        self.projects.save_project(state)
        script_path = self._export_script(state)
        return state.script, script_path

    # ----- internal orchestration -----
    def _execute_pipeline(self, state, **kwargs):
        """Execute remaining steps based on current project state."""
        topic = state.config.get("topic", "")
        length = state.config.get("length", "medium")
        complexity = state.config.get("complexity", "simple")

        # Step 1: Generate script (if not already done)
        if state.state not in ("script_generated", "voice_configured", "voice_configuring", "generating_audio", "audio_generated", "post_processing"):
            llm = self._get_default_llm()
            generator = StoryGenerator(llm)
            state.script = generator.generate_script(
                topic, length, complexity, with_sound=self._sound_enabled()
            )
            state.state = "script_generated"
            self.projects.save_project(state)
            self._log_progress("Script generated: %s" % state.script.title)

        # Export the script as a standalone JSON next to the final audio.
        if state.script is not None:
            self._export_script(state)

        # Step 2: Match voices (if not already done)
        if state.state not in ("voice_configured", "generating_audio", "audio_generated", "post_processing"):
            tts_voices = self.registry.list_tts_voices()
            if not tts_voices:
                raise TTSError("No TTS voices available")

            from .voice_matcher import VoiceMatcher

            mode = self.config.get("voice_matcher") or "llm"
            matcher_llm = (
                self._get_default_llm() if mode == "llm" else None
            )
            matcher = VoiceMatcher(
                self.registry, llm=matcher_llm, mode=mode
            )
            matcher.match_voices(
                state.script,
                allowed_providers=kwargs.get("tts_providers"),
                allowed_voice_ids=kwargs.get("voice_ids"),
                default_provider=self.config.get("tts.default_provider"),
            )
            state.state = "voice_configured"
            self.projects.save_project(state)
            # Re-export so the standalone script JSON captures the matched
            # voices (the first export above runs before voice matching).
            self._export_script(state)
            self._log_progress("Voices configured")

        # Step 3: Generate audio per line. The loop below is authoritative:
        # it reuses the canonical per-line file when present and relocates any
        # legacy absolute-path segment, so start empty even on resume.
        lines_audio_paths = []
        output_format = kwargs.get("output_format") or self.config.get("output_format") or "mp3"
        total = len(state.script.lines)
        progress_step = kwargs.get("progress_step", "Generating audio %d/%d")

        # Build character_id -> voice map and find narrator voice
        char_voice_map = {
            c.id: c.voice_config
            for c in state.script.characters
            if c.voice_config
        }
        narrator_voice = self._find_narrator_voice(state.script, char_voice_map)

        for idx, line in enumerate(state.script.lines, start=1):
            # Voice precedence: line-level override > character voice > narrator
            voice = line.voice_config
            if not voice and line.line_type == "dialogue" and line.character_id:
                voice = char_voice_map.get(line.character_id)
            if not voice:
                voice = narrator_voice
            if not voice:
                self._log_error(line.line_id, RuntimeError("No voice assigned"))
                continue

            out_path = self._audio_path(state.project_id, line.line_id, output_format)
            if out_path.exists():
                lines_audio_paths.append(str(out_path))
                continue
            self._log_progress(progress_step % (idx, total))
            if line.audio_path and Path(line.audio_path).exists():
                # Segment recorded under an older layout: relocate it into the
                # per-project audio dir so offsets and later resumes find it.
                import shutil

                out_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(line.audio_path, out_path)
                line.audio_path = str(out_path)
                lines_audio_paths.append(str(out_path))
                continue
            try:
                tts = self.registry.get_tts(voice.provider)
                directives, context = self._line_context(state.script.lines, idx - 1)
                tts.synthesize(
                    line.text,
                    voice,
                    out_path,
                    directives=directives,
                    context=context,
                )
                line.audio_path = str(out_path)
                lines_audio_paths.append(str(out_path))
            except Exception as exc:
                self._log_error(line.line_id, exc)
                continue

        if not lines_audio_paths:
            raise TTSError("No audio segments were generated successfully")

        state.state = "audio_generated"
        self.projects.save_project(state)

        # Step 4: Concatenate into final output
        self._log_progress("Concatenating audio...")
        output_path = self._final_output_path(state.project_id, output_format)
        self._concatenate(lines_audio_paths, output_path)

        # Step 5 (optional): generate/cache sound effects + BGM and mix in.
        if self._sound_enabled():
            self._apply_soundtrack(state, output_path)

        state.state = "completed"
        self.projects.save_project(state)

        return str(output_path)

    # ----- helpers -----
    def _find_narrator_voice(self, script, char_voice_map):
        """Find a narrator voice, or fall back to any available voice."""
        narrator_keywords = ("narrator", "旁白", "说书", "叙述")
        for char in script.characters:
            text = "{} {}".format(char.id, char.name).lower()
            if any(kw in text for kw in narrator_keywords):
                voice = char_voice_map.get(char.id)
                if voice:
                    return voice
        # Fallback: prefer a narrator-typed voice so narration is not read in
        # the first dialogue character's timbre; only then use any voice.
        for voice in char_voice_map.values():
            if voice and voice.voice_type == "narrator":
                return voice
        for voice in char_voice_map.values():
            return voice
        return None

    def _setup_logging(self):
        from .utils import setup_logging

        setup_logging(self.config.get("log_level") or "info")

    def _get_default_llm(self):
        default = self.config.get("llm.default_provider")
        if default:
            return self.registry.get_llm(default)
        names = self.registry.list_llm_names()
        if names:
            return self.registry.get_llm(names[0])
        raise LLMError("No LLM provider registered")

    def _audio_path(self, project_id, line_id, output_format):
        return (
            self._project_dir(project_id)
            / "audio"
            / "{}.{}".format(line_id, output_format)
        )

    @staticmethod
    def _line_context(lines, idx, lookback=4):
        """Build (directives, quoted_context) for one line.

        directives carries the line's acting direction; quoted_context is
        the most recent narration and dialogue within a small lookback,
        kept in story order, so the model inherits the scene's emotion.
        """
        current = lines[idx]
        directives = []
        direction = (current.metadata or {}).get("direction")
        if direction:
            directives.append(str(direction))

        picked = {}
        for j in range(idx - 1, max(-1, idx - lookback - 1), -1):
            prev = lines[j]
            kind = prev.line_type
            if kind in ("narration", "dialogue") and kind not in picked and prev.text:
                picked[kind] = (j, prev.text)
        context = [text for _, text in sorted(picked.values())]
        return directives, context

    def _final_output_path(self, project_id, output_format):
        return self._project_dir(project_id) / "story.{}".format(output_format)

    def _script_path(self, project_id):
        return self._project_dir(project_id) / "story.script.json"

    def _project_dir(self, project_id):
        """All files for one story (state, segments, script, final audio)."""
        root = self.config.get("project_dir") or self.config.get(
            "output_dir"
        ) or "./.storyteller/stories"
        return Path(root) / project_id

    def _export_script(self, state):
        """Write the script to a standalone JSON file in the output dir."""
        path = self._script_path(state.project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                _script_to_dict(state.script),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def _find_final_output(self, project_id):
        """Return the existing final audio (story.<ext>) for a project."""
        project_dir = self._project_dir(project_id)
        if not project_dir.exists():
            return None
        candidates = sorted(project_dir.glob("story.*"))
        for candidate in candidates:
            if candidate.suffix.lstrip(".") in (
                "mp3", "wav", "ogg", "opus", "flac", "aac",
            ):
                return candidate
        return candidates[0] if candidates else None

    def _concatenate(self, audio_paths, output_path):
        from .audio import PydubAudioProcessor

        processor = PydubAudioProcessor()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return processor.concatenate(audio_paths, output_path)

    # ----- soundtrack (optional sound effects / background music) -----
    def _sound_enabled(self):
        return bool(self.config.get("sound.enabled"))

    def _get_sound_provider(self):
        if self._sound_provider is not None:
            return self._sound_provider
        from ..providers.volcengine.sfx import VolcengineSoundProvider

        self._sound_provider = VolcengineSoundProvider(self.config)
        return self._sound_provider

    def _get_sound_library(self):
        if self._sound_library is not None:
            return self._sound_library
        from .sound_library import SoundLibrary

        sound_dir = self.config.get("sound.dir") or "./.storyteller/sounds"
        self._sound_library = SoundLibrary(sound_dir)
        return self._sound_library

    def _apply_soundtrack(self, state, output_path):
        """Generate/cache BGM + effects and mix them into the concatenated file."""
        script = state.script
        cues = list(script.sound_effects)
        if script.background_music is not None:
            cues.append(script.background_music)
        for line in script.lines:
            cues.extend(line.sound_effects)
            if line.background_music is not None:
                cues.append(line.background_music)
        pending = [c for c in cues if c.prompt and not c.source_path]
        if not pending and not any(c.source_path for c in cues):
            return

        provider = self._get_sound_provider()
        library = self._get_sound_library()
        for cue in pending:
            try:
                path, record, _ = library.get_or_create(
                    provider,
                    prompt=cue.prompt,
                    name=cue.name,
                    kind=_KIND_FOR_TYPE.get(cue.type, "sfx"),
                    description=cue.description or "",
                    tags=cue.tags or [],
                    audio_format="mp3",
                )
            except Exception as exc:
                self._log_error(cue.effect_id, exc)
                continue
            cue.source_path = str(path)
            cue.source_type = "local"
            if cue.duration is None:
                cue.duration = record.get("duration")
        self.projects.save_project(state)
        self._export_script(state)

        from .audio import PydubAudioProcessor

        processor = PydubAudioProcessor()
        offsets = self._line_offsets(state, output_path.suffix.lstrip("."))

        # Position every line-scoped cue at the start of its line.
        effects = []
        for line in script.lines:
            offset = offsets.get(line.line_id, 0.0)
            for cue in line.sound_effects:
                if cue.source_path:
                    cue.start_time = offset
                    effects.append(cue)
            if line.background_music is not None and line.background_music.source_path:
                line.background_music.start_time = offset
                effects.append(line.background_music)
        effects.extend(c for c in script.sound_effects if c.source_path)

        working_path = output_path
        if script.background_music is not None and script.background_music.source_path:
            working_path = output_path.with_name(
                "{}.bgm{}".format(output_path.stem, output_path.suffix)
            )
            processor.mix_background(
                output_path, script.background_music.source_path, working_path
            )

        if effects:
            processor.add_effects(working_path, effects, output_path)
            if working_path != output_path and working_path.exists():
                working_path.unlink()
        elif working_path != output_path:
            working_path.replace(output_path)

    def _line_offsets(self, state, output_format):
        """Map line_id -> start offset (seconds) in the concatenated audio."""
        from pydub import AudioSegment

        offsets = {}
        elapsed_ms = 0
        for line in state.script.lines:
            offsets[line.line_id] = elapsed_ms / 1000.0
            path = self._audio_path(
                state.project_id, line.line_id, output_format
            )
            source = path if path.exists() else (
                Path(line.audio_path) if line.audio_path else None
            )
            if source is not None and Path(source).exists():
                try:
                    elapsed_ms += len(AudioSegment.from_file(str(source)))
                except Exception:
                    pass
        return offsets

    def _log_progress(self, msg):
        level = self.config.get("progress_level") or "simple"
        if level == "quiet":
            return
        print(msg)

    def _log_error(self, line_id, exc):
        mode = self.config.get("strict_mode") or False
        if mode:
            raise exc
        print("Warning: failed line %s: %s" % (line_id, exc))