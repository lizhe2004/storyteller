from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..core.voice_matcher import is_narration_voice
START_NOTICE = "故事就要开始喽，准备好了吗？"


def start_notice_text():
    """Return the fixed notice played between the opening and story lines."""
    return START_NOTICE


def choose_host_voice(registry, tts_names, filler_voice=None):
    if filler_voice and ":" in filler_voice:
        name, voice_id = filler_voice.split(":", 1)
        if name in tts_names:
            for voice in registry.get_tts(name).list_voices():
                if voice.voice_id == voice_id:
                    return name, voice
    for name in tts_names:
        voices = registry.get_tts(name).list_voices()
        for voice in voices:
            if is_narration_voice(voice):
                return name, voice
        if voices:
            return name, voices[0]
    return None


@dataclass
class FillerClip:
    kind: str
    text: str
    mp3_path: str


def cached_start_notice(registry, host, cache_dir):
    """Return a cached full-file fallback when a realtime session is unavailable."""
    if not host:
        return None
    provider, voice = host
    text = start_notice_text()
    key = hashlib.sha256("|".join((provider, voice.voice_id,
                                    str(voice.speed), str(voice.pitch), text)).encode()).hexdigest()
    path = Path(cache_dir) / "fillers" / (key + ".mp3")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        registry.get_tts(provider).synthesize(text, voice, path)
    return FillerClip("start_notice", text, str(path))
