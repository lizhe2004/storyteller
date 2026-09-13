from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

from .exceptions import LLMError, TTSError, SoundGenerationError
from .project import ProjectManager, _script_to_dict
from .story_generator import StoryGenerator
from .voice_matcher import is_narration_voice
from .observability import timed_event

# Script SoundEffect.type -> SoundLibrary kind.
_KIND_FOR_TYPE = {"effect": "sfx", "ambient": "ambient", "music": "music"}

# Total generation attempts per cue: seed-audio nondeterministically returns
# near-silent clips, so the same prompt is retried before the cue is skipped.
MAX_SOUND_ATTEMPTS = 3

# seed-audio exposes no duration parameter: the desired length is appended to
# text_prompt as natural language. Clamp to a sane range; 120s is the API's
# single-request ceiling.
MIN_SOUND_DURATION_SEC = 2
MAX_SOUND_DURATION_SEC = 120
# A punctual effect is one discrete event, not a bed: the anchor-to-line-end
# window can be tens of seconds on long lines, which would make the "no longer
# than N seconds" directive meaningless. Cap it; the mix still hard-cuts at
# the line end as a backstop.
EFFECT_MAX_DURATION_SEC = 6

logger = logging.getLogger(__name__)


def human_time():
    """Return a local, millisecond-precision time for project diagnostics."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def sound_duration_seconds(cue_type, line_duration, anchor_offset=0.0):
    """Target clip length for a cue, from its owning line's real TTS length.

    Ambient/music fills the whole line; a punctual effect gets only the window
    from its anchor position to the line's end (capped). Returns None when the
    line duration is unknown, so the caller leaves the prompt unconstrained.
    """
    if not line_duration or line_duration <= 0:
        return None
    if cue_type == "effect":
        from .audio import EFFECT_TAIL_GRACE_SEC

        # The mix lets an effect ring EFFECT_TAIL_GRACE_SEC past the line end
        # (an event on the line's last words must not be chopped), so request
        # a clip matching that wider playable window.
        window = min(
            EFFECT_MAX_DURATION_SEC,
            max(0.0, line_duration - (anchor_offset or 0.0))
            + EFFECT_TAIL_GRACE_SEC,
        )
    else:
        window = line_duration
    if window <= 0:
        return None
    # Half-up rounding (not Python's banker's rounding): a 2.5s window is
    # worth asking for 3 seconds, not 2.
    seconds = int(window + 0.5)
    if seconds < 1:
        seconds = 1
    return min(
        MAX_SOUND_DURATION_SEC, max(MIN_SOUND_DURATION_SEC, seconds)
    )


def build_sound_prompt(prompt, cue_type, line_duration, anchor_offset=0.0):
    """Append a natural-language duration directive to a cue's prompt."""
    seconds = sound_duration_seconds(
        cue_type, line_duration, anchor_offset
    )
    if seconds is None:
        return prompt
    if cue_type == "effect":
        directive = "这是一个单独的声音事件，时长不超过%d秒" % seconds
    else:
        directive = "持续约%d秒，平缓可循环，结尾自然减弱" % seconds
    return "%s，%s" % (prompt.rstrip("。.!?！？"), directive)

# Punctuation/whitespace ignored when estimating an anchor's spoken position.
_PUNCT_RE = re.compile(r"[\s，。！？；：、,…,.\!?;:\-—“”\"'（）()…]")


def _count_spoken(text):
    """Count spoken characters (exclude punctuation/whitespace) for timing."""
    return len(_PUNCT_RE.sub("", text or ""))


def _snippet(text, n):
    """Shorten text for progress display, appending an ellipsis when cut."""
    text = (text or "").strip()
    return text if len(text) <= n else text[:n] + "…"


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
        self._log_progress("Generating script...")
        state.script = StoryGenerator(llm).generate_script(
            topic, length, complexity, with_sound=self._sound_enabled()
        )
        state.state = "script_generated"
        self.projects.save_project(state)
        self.projects.rename_for_title(state)
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
            self._log_progress("Generating script...")
            state.script = generator.generate_script(
                topic, length, complexity, with_sound=self._sound_enabled()
            )
            state.state = "script_generated"
            self.projects.save_project(state)
            self.projects.rename_for_title(state)
            self._log_progress("Script generated: %s" % state.script.title)

        # Export the script as a standalone JSON next to the final audio.
        if state.script is not None:
            self._export_script(state)

        # Step 2: Match voices (if not already done)
        if state.state not in ("voice_configured", "generating_audio", "audio_generated", "post_processing"):
            selected_tts = kwargs.get("tts_providers")
            if selected_tts is not None:
                known_tts = self.registry.list_tts_names()
                unknown_tts = [p for p in selected_tts if p not in known_tts]
                if unknown_tts:
                    raise TTSError(
                        "Unknown TTS provider(s): {}. Configured providers: "
                        "{}. Set STORYTELLER_TTS_<NAME>_API_KEY for each "
                        "(and STORYTELLER_TTS_<NAME>_TYPE for non-Volcengine "
                        "implementations), or choose from the configured list."
                        .format(
                            ", ".join(unknown_tts),
                            ", ".join(known_tts) or "(none)",
                        )
                    )
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
            allowed_tts = kwargs.get("tts_providers")
            if allowed_tts is None:
                allowed_tts = self.config.get("tts.providers") or None
            matcher.match_voices(
                state.script,
                allowed_providers=allowed_tts,
                allowed_voice_ids=kwargs.get("voice_ids"),
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
        char_names = {c.id: c.name for c in state.script.characters}

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
                self._log_detail(
                    "  line %s cached, skipped" % line.line_id
                )
                lines_audio_paths.append(str(out_path))
                continue
            self._log_progress(progress_step % (idx, total))
            speaker = char_names.get(line.character_id, "") or line.line_type
            self._log_detail(
                "  line %s [%s]: %s" % (
                    line.line_id, speaker, _snippet(line.text, 20)
                )
            )
            if line.audio_path and Path(line.audio_path).exists():
                # Segment recorded under an older layout: relocate it into the
                # per-project audio dir so offsets and later resumes find it.
                out_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(line.audio_path, out_path)
                line.audio_path = str(out_path)
                lines_audio_paths.append(str(out_path))
                continue
            try:
                tts = self.registry.get_tts(voice.provider)
                directives, context = self._line_context(state.script.lines, idx - 1)
                tts_timing = line.processing.setdefault("tts", {})
                tts_timing["started_at"] = human_time()
                try:
                    tts.synthesize(
                        line.text,
                        voice,
                        out_path,
                        directives=directives,
                        context=context,
                    )
                finally:
                    tts_timing["ended_at"] = human_time()
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
        # Fallback: prefer a reading/narration-suited voice so narration is
        # not read in the first dialogue character's timbre; then any voice.
        for voice in char_voice_map.values():
            if voice and is_narration_voice(voice):
                return voice
        for voice in char_voice_map.values():
            return voice
        return None

    def voice_for_line(self, line, char_voice_map, narrator_voice):
        voice = line.voice_config
        if not voice and line.line_type == "dialogue" and line.character_id:
            voice = char_voice_map.get(line.character_id)
        return voice or narrator_voice

    def line_context_directives(self, lines, idx):
        return self._line_context(lines, idx)

    def materialize_line_cues(self, state, line, line_duration, provider,
                              library, referenced_paths):
        cues = list(line.sound_effects)
        if line.background_music is not None:
            cues.append(line.background_music)
        entries = []
        for cue in cues:
            if not cue.source_path and not cue.prompt:
                continue
            offset = self._anchor_offset(line, cue, line_duration)
            if not cue.source_path:
                gen_prompt = build_sound_prompt(cue.prompt, cue.type,
                                                 line_duration, offset)
                record = library.find(provider, gen_prompt, audio_format="mp3")
                raw_path = self._project_sound_path(
                    state.project_id, cue, referenced_paths)
                try:
                    record, _ = self._materialize_cue(
                        provider, library, cue, raw_path, gen_prompt,
                        record=record)
                except Exception as exc:
                    self._log_error(cue.effect_id, exc)
                    continue
                referenced_paths.add(Path(raw_path))
                cue.source_path = str(raw_path)
                cue.source_type = "local"
                if cue.duration is None:
                    cue.duration = record.get("duration")
            if Path(cue.source_path).exists():
                entries.append((cue, offset))
        return entries

    def finalize_audio(self, state, line_paths, output_format="mp3",
                       with_sound=False):
        output_path = self._final_output_path(state.project_id, output_format)
        self._concatenate(line_paths, output_path)
        if with_sound:
            self._apply_soundtrack(state, output_path)
        state.state = "completed"
        self.projects.save_project(state)
        return output_path

    def _setup_logging(self):
        from .utils import setup_logging

        setup_logging(
            self.config.get("log_level") or "info",
            log_dir=Path(self.config.get("data_dir") or "./.storyteller") / "logs",
        )

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
        """All files for one story (state, segments, script, final audio).

        Follows the date-title directory rename via the project manager's
        id -> directory resolution.
        """
        return self.projects.resolve_project_dir(project_id)

    def _project_sound_path(self, project_id, cue, referenced_paths=None):
        """Raw clip path inside the project's sounds/ dir for one cue.

        An existing file is REUSED (overwritten) unless another cue already
        owns that path in this pass (``referenced_paths``), so a failed
        near-silent clip keeps the same inspection path on retry/resume
        instead of accumulating name-2.mp3, name-3.mp3.
        """
        from .sound_library import safe_sound_name

        sounds_dir = self._project_dir(project_id) / "sounds"
        sounds_dir.mkdir(parents=True, exist_ok=True)
        fallback = "sfx_" + str(cue.effect_id)[-6:]
        stem = safe_sound_name(cue.name or (cue.prompt or "")[:12], fallback)
        referenced = referenced_paths or set()
        candidate = sounds_dir / "{}.mp3".format(stem)
        suffix = 2
        while candidate in referenced:
            candidate = sounds_dir / "{}-{}.mp3".format(stem, suffix)
            suffix += 1
        return candidate

    def _export_script(self, state):
        """Write the script to a standalone JSON file in the output dir."""
        path = self._script_path(state.project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with timed_event(logger, "script_export", project_id=state.project_id,
                         path=path):
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
        names = self.registry.list_sound_names()
        name = self.config.get("sound.default_provider")
        if name not in names:
            # An unregistered default is ignored the same way bootstrap
            # ignores it; fall back to the first registered provider.
            name = names[0] if names else None
        if name is None:
            raise TTSError(
                "No sound provider configured: set "
                "STORYTELLER_SOUND_<NAME>_API_KEY "
                "(use --sound-provider to choose one)"
            )
        self._sound_provider = self.registry.get_sound(name)
        return self._sound_provider

    def _get_sound_library(self):
        if self._sound_library is not None:
            return self._sound_library
        from .sound_library import SoundLibrary

        sound_dir = self.config.get("sound.dir") or "./.storyteller/sounds"
        self._sound_library = SoundLibrary(sound_dir)
        return self._sound_library

    def _generate_cue_with_retry(
        self, provider, library, cue, raw_path, gen_prompt
    ):
        """Generate one cue, retrying near-silent results up to the limit.

        SoundGenerationError from the loudness gate is retried with the same
        prompt up to MAX_SOUND_ATTEMPTS; the raw clip is overwritten each
        time, leaving only the last failure on disk. Other errors (network,
        API) propagate to the caller without retry.
        """
        last_error = None
        for attempt in range(1, MAX_SOUND_ATTEMPTS + 1):
            attempt_timing = {"attempt": attempt, "started_at": human_time()}
            cue.generation_history.append(attempt_timing)
            try:
                _, gen_duration = provider.generate(
                    gen_prompt, raw_path, audio_format="mp3"
                )
            finally:
                attempt_timing["ended_at"] = human_time()
            try:
                return library.admit(
                    raw_path,
                    provider,
                    prompt=gen_prompt,
                    name=cue.name,
                    kind=_KIND_FOR_TYPE.get(cue.type, "sfx"),
                    description=cue.description or "",
                    tags=cue.tags or [],
                    audio_format="mp3",
                    duration=gen_duration,
                )
            except SoundGenerationError as exc:
                last_error = exc
                if attempt < MAX_SOUND_ATTEMPTS:
                    self._log_progress(
                        "  %s 近静音，重试 %d/%d…" % (
                            cue.name, attempt, MAX_SOUND_ATTEMPTS - 1
                        )
                    )
                continue
        raise last_error

    def _materialize_cue(
        self, provider, library, cue, raw_path, gen_prompt, record=None
    ):
        """Return an audible clip for one cue: cache hit or retried generate.

        ``gen_prompt`` is the duration-enhanced prompt used for both cache
        lookup and generation, so fingerprints stay consistent. ``record`` may
        be a cache record the caller already looked up. Returns
        ``(record, created)``.
        """
        if record is None:
            record = library.find(
                provider, gen_prompt, audio_format="mp3"
            )
        if record is not None:
            shutil.copy2(library.path_for(record), raw_path)
            return record, False
        return self._generate_cue_with_retry(
            provider, library, cue, raw_path, gen_prompt
        ), True

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

        # Line durations bound each generation request: ambient fills its
        # line, an effect fills the window after its anchor, script-level
        # cues target the full story. Computed before generation so the
        # duration directive can be baked into the generation prompt.
        timing = self._line_timing(
            state, output_path.suffix.lstrip(".")
        )
        total_duration = sum(
            (d or 0.0) for _, d in timing.values()
        )
        cue_context = {}
        for line in script.lines:
            _, line_duration = timing.get(line.line_id, (0.0, 0.0))
            line_cues = list(line.sound_effects)
            if line.background_music is not None:
                line_cues.append(line.background_music)
            for cue in line_cues:
                cue_context[id(cue)] = (
                    line_duration,
                    self._anchor_offset(line, cue, line_duration),
                )
        for cue in script.sound_effects:
            cue_context.setdefault(id(cue), (total_duration, 0.0))
        if script.background_music is not None:
            cue_context.setdefault(
                id(script.background_music), (total_duration, 0.0)
            )

        total_pending = len(pending)
        # Paths already owned by cues materialized this pass, so same-named
        # distinct cues get a -2 suffix rather than overwriting each other.
        referenced_paths = {
            Path(c.source_path)
            for c in cues
            if c.source_path and Path(c.source_path).exists()
        }
        for idx, cue in enumerate(pending, start=1):
            line_duration, anchor_offset = cue_context.get(
                id(cue), (0.0, 0.0)
            )
            gen_prompt = build_sound_prompt(
                cue.prompt, cue.type, line_duration, anchor_offset
            )
            record = library.find(
                provider, gen_prompt, audio_format="mp3"
            )
            if record is not None:
                self._log_progress(
                    "Sound %d/%d · %s (cached)" % (
                        idx, total_pending, cue.name
                    )
                )
            else:
                self._log_progress(
                    "Generating sound %d/%d · %s" % (
                        idx, total_pending, cue.name
                    )
                )
            try:
                raw_path = self._project_sound_path(
                    state.project_id, cue, referenced_paths
                )
                record, created = self._materialize_cue(
                    provider,
                    library,
                    cue,
                    raw_path,
                    gen_prompt,
                    record=record,
                )
            except Exception as exc:
                # The raw clip (if any) stays in the project's sounds/ dir
                # for inspection; the cue is simply left out of the mix.
                self._log_error(cue.effect_id, exc)
                continue
            referenced_paths.add(Path(raw_path))
            cue.source_path = str(raw_path)
            cue.source_type = "local"
            if cue.duration is None:
                cue.duration = record.get("duration")
            self._log_detail(
                "  sound %s -> %s (%.1fs%s)" % (
                    cue.name, raw_path.name, record.get("duration") or 0,
                    "" if created else ", cached"
                )
            )
        self.projects.save_project(state)
        self._export_script(state)

        from .audio import PydubAudioProcessor

        processor = PydubAudioProcessor()

        # One cue group per line. Punctual effects with an anchor phrase are
        # offset to where that phrase is spoken inside the line; ambience and
        # unanchored cues start at the head. Every cue is still cut at the
        # line's end so a long bed cannot continue into the next line.
        groups = []
        for line in script.lines:
            start, duration = timing.get(line.line_id, (0.0, 0.0))
            cues = list(line.sound_effects)
            if line.background_music is not None:
                cues.append(line.background_music)
            cues = [c for c in cues if c.source_path]
            if cues:
                entries = [
                    (c, self._anchor_offset(line, c, duration)) for c in cues
                ]
                groups.append((start, duration, entries))
        # Script-scoped cues have no owning line: play from the start without
        # a line-end trim.
        top_cues = [c for c in script.sound_effects if c.source_path]
        if top_cues:
            groups.append((0.0, None, [(c, 0.0) for c in top_cues]))

        working_path = output_path
        # 临时关闭：背景音乐不混入最终文件（仅保留音效叠加），需要时恢复。
        # if script.background_music is not None and script.background_music.source_path:
        #     working_path = output_path.with_name(
        #         "{}.bgm{}".format(output_path.stem, output_path.suffix)
        #     )
        #     processor.mix_background(
        #         output_path, script.background_music.source_path, working_path
        #     )

        if groups:
            self._log_progress("Mixing soundtrack...")
            mix_started = human_time()
            try:
                processor.add_effect_groups(
                    working_path, groups, output_path
                )
            finally:
                mix_ended = human_time()
                for line in script.lines:
                    if any(c.source_path for c in line.sound_effects) or line.background_music is not None:
                        line.processing["mixing"] = {"started_at": mix_started, "ended_at": mix_ended}
            if working_path != output_path and working_path.exists():
                working_path.unlink()
        elif working_path != output_path:
            working_path.replace(output_path)

    @staticmethod
    def _anchor_offset(line, cue, line_duration):
        """Estimate where inside its line a punctual effect should fire.

        TTS returns no word timestamps, so locate the cue's verbatim anchor in
        the spoken text and scale its character position by the line's real
        audio duration. Character counts exclude punctuation, which folds
        pause time into the proportional estimate proportionally; per-line
        self-calibration tolerates varying speech rates. Returns 0 for beds
        and when the anchor is absent.
        """
        if not line_duration or cue.type != "effect" or not cue.anchor:
            return 0.0
        text, anchor = line.text or "", cue.anchor
        idx = text.find(anchor)
        if idx < 0:
            return 0.0
        before = _count_spoken(text[:idx])
        total = _count_spoken(text)
        if total <= 0:
            return 0.0
        return min(line_duration, line_duration * before / total)

    def _line_timing(self, state, output_format):
        """Map line_id -> (start_sec, duration_sec) in the concatenated audio.

        Duration is the spoken segment's own length; it bounds how long the
        line's sound effects may play before being cut at the next line.
        """
        from pydub import AudioSegment

        timing = {}
        elapsed_ms = 0
        for line in state.script.lines:
            path = self._audio_path(
                state.project_id, line.line_id, output_format
            )
            source = path if path.exists() else (
                Path(line.audio_path) if line.audio_path else None
            )
            duration_ms = 0
            if source is not None and Path(source).exists():
                try:
                    duration_ms = len(
                        AudioSegment.from_file(str(source))
                    )
                except Exception:
                    duration_ms = 0
            timing[line.line_id] = (
                elapsed_ms / 1000.0,
                duration_ms / 1000.0,
            )
            elapsed_ms += duration_ms
        return timing

    def _log_progress(self, msg):
        level = self.config.get("progress_level") or "simple"
        if level == "quiet":
            return
        print(msg)

    def _log_detail(self, msg):
        """Per-line / per-cue detail, only shown with --progress detailed."""
        if (self.config.get("progress_level") or "simple") == "detailed":
            print(msg)

    def _log_error(self, line_id, exc):
        mode = self.config.get("strict_mode") or False
        if mode:
            raise exc
        print("Warning: failed line %s: %s" % (line_id, exc))
