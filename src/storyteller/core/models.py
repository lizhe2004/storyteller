from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Literal


# ========== Enums ==========
class LineType(str, Enum):
    DIALOGUE = "dialogue"
    NARRATION = "narration"


class SoundType(str, Enum):
    AMBIENT = "ambient"
    EFFECT = "effect"
    MUSIC = "music"


class ProjectStatus(str, Enum):
    INITIALIZED = "initialized"
    TOPIC_COLLECTED = "topic_collected"
    CONFIGURING = "configuring"
    SCRIPT_GENERATING = "script_generating"
    SCRIPT_GENERATED = "script_generated"
    VOICE_CONFIGURING = "voice_configuring"
    VOICE_CONFIGURED = "voice_configured"
    GENERATING_AUDIO = "generating_audio"
    AUDIO_GENERATED = "audio_generated"
    POST_PROCESSING = "post_processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ========== Sound ==========
@dataclass
class SoundEffect:
    effect_id: str
    name: str
    type: Literal["ambient", "effect", "music"]
    source_path: Optional[str] = None
    source_type: Literal["local", "builtin", "url"] = "local"
    volume: float = 1.0
    start_time: float = 0.0
    duration: Optional[float] = None
    fade_in: float = 0.0
    fade_out: float = 0.0
    # Generation hints: prompt drives the text-to-audio model; description
    # and tags describe the sound for catalog search and reuse.
    prompt: Optional[str] = None
    description: Optional[str] = None
    tags: list = field(default_factory=list)
    # Verbatim phrase from the owning line at which a punctual effect should
    # fire (ambient beds omit it and start at the line head). Used to estimate
    # an intra-line offset because TTS gives no word-level timestamps.
    anchor: Optional[str] = None


# ========== Voice ==========
@dataclass
class VoiceConfig:
    provider: str
    voice_id: str
    voice_type: Literal["male", "female", "child", "narrator"]
    language: str = "zh-CN"
    style: Optional[str] = None
    speed: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0
    # Descriptive hints used by semantic (LLM) voice matching.
    name: Optional[str] = None
    age: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None


# ========== Character ==========
@dataclass
class Character:
    id: str
    name: str
    description: str
    voice_config: Optional[VoiceConfig] = None


# ========== Script ==========
@dataclass
class ScriptLine:
    line_id: str
    line_type: Literal["dialogue", "narration"]
    character_id: Optional[str] = None
    text: str = ""
    voice_config: Optional[VoiceConfig] = None
    audio_path: Optional[str] = None
    sound_effects: list = field(default_factory=list)
    background_music: Optional[SoundEffect] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Script:
    script_id: str
    title: str
    topic: str
    characters: list = field(default_factory=list)
    lines: list = field(default_factory=list)
    background_music: Optional[SoundEffect] = None
    sound_effects: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


# ========== Project State ==========
@dataclass
class ProjectState:
    project_id: str
    state: Literal[
        "initialized",
        "topic_collected",
        "configuring",
        "script_generating",
        "script_generated",
        "voice_configuring",
        "voice_configured",
        "generating_audio",
        "audio_generated",
        "post_processing",
        "completed",
        "failed",
    ] = "initialized"
    script: Optional[Script] = None
    current_step: Optional[str] = None
    config: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
