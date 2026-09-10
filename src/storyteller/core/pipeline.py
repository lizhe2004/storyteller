from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .exceptions import LLMError, TTSError
from .project import ProjectManager
from .story_generator import StoryGenerator


class Pipeline:
    """Orchestrates the full story-to-audio workflow.

    Coordinates project management, script generation, voice matching,
    TTS synthesis, audio concatenation, and format conversion.
    """

    def __init__(self, config, project_manager=None):
        self.config = config
        from ..providers.registry import ProviderRegistry

        self.registry = ProviderRegistry(config)
        self.projects = project_manager or ProjectManager(
            config.get("project_dir") or "./projects"
        )

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
            outputs = self._find_outputs(project_id)
            if outputs:
                return str(outputs[0])
            raise RuntimeError("No output found for completed project")
        return self._execute_pipeline(state, **kwargs)

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
            state.script = generator.generate_script(topic, length, complexity)
            state.state = "script_generated"
            self.projects.save_project(state)
            self._log_progress("Script generated: %s" % state.script.title)

        # Step 2: Match voices (if not already done)
        if state.state not in ("voice_configured", "generating_audio", "audio_generated", "post_processing"):
            tts_voices = self.registry.list_tts_voices()
            if not tts_voices:
                raise TTSError("No TTS voices available")

            from .voice_matcher import VoiceMatcher

            matcher = VoiceMatcher(self.registry)
            matcher.match_voices(
                state.script,
                allowed_providers=kwargs.get("tts_providers"),
                allowed_voice_ids=kwargs.get("voice_ids"),
                default_provider=self.config.get("tts.default_provider"),
            )
            state.state = "voice_configured"
            self.projects.save_project(state)
            self._log_progress("Voices configured")

        # Step 3: Generate audio per line
        lines_audio_paths = self._collect_existing_audio(state) if state.state in ("generating_audio", "audio_generated", "post_processing") else []
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
                lines_audio_paths.append(line.audio_path)
                line.audio_path = str(out_path)
                continue
            try:
                tts = self.registry.get_tts(voice.provider)
                tts.synthesize(line.text, voice, out_path)
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

        state.state = "completed"
        self.projects.save_project(state)

        self._log_progress("Done! Output: %s" % output_path)
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
        # Fallback: any character's voice
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
        base = Path(self.config.get("output_dir") or "./outputs")
        return base / project_id / "audio" / "{}.{}".format(line_id, output_format)

    def _final_output_path(self, project_id, output_format):
        base = Path(self.config.get("output_dir") or "./outputs")
        return base / "{}.{}".format(project_id, output_format)

    def _find_outputs(self, project_id):
        base = Path(self.config.get("output_dir") or "./outputs")
        if not base.exists():
            return []
        return [p for p in base.iterdir() if p.is_file() and p.name.startswith(project_id)]

    def _collect_existing_audio(self, state):
        paths = []
        for line in state.script.lines:
            if line.audio_path and Path(line.audio_path).exists():
                paths.append(line.audio_path)
        return paths

    def _concatenate(self, audio_paths, output_path):
        from .audio import PydubAudioProcessor

        processor = PydubAudioProcessor()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return processor.concatenate(audio_paths, output_path)

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