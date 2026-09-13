from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from .models import VoiceConfig

STREAM_SAMPLE_RATE = 24000
STREAM_CHANNELS = 1
STREAM_SAMPLE_WIDTH = 2
CHUNK_AUDIO = "audio"
CHUNK_EVENT = "event"


@dataclass
class StreamChunk:
    kind: str
    data: object


class TTSProvider(ABC):
    """Abstract interface for TTS providers.

    Knows only about text -> audio. Knows nothing about characters.
    """

    supports_streaming = False

    def stream_synthesize(self, text, voice_config, *, directives=None, context=None):
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self):
        """The provider's registered name (e.g. 'volcengine')."""
        raise NotImplementedError

    @abstractmethod
    def list_voices(self, **kwargs):
        """Return the list of VoiceConfig this provider offers."""
        raise NotImplementedError

    @abstractmethod
    def synthesize(self, text, voice_config, output_path, **kwargs):
        """Synthesize text to an audio file at output_path. Returns the
        Path written."""
        raise NotImplementedError

    def list_voices_filtered(self, allowed_voice_ids=None, **kwargs):
        """Return voices, optionally filtered to a set of voice_ids."""
        voices = self.list_voices(**kwargs)
        if allowed_voice_ids is None:
            return voices
        return [v for v in voices if v.voice_id in allowed_voice_ids]
