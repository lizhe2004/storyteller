from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from .models import VoiceConfig
from .tts import StreamChunk


class StreamingTTSSession(ABC):
    """A bidirectional text-to-speech stream for one voice."""

    @abstractmethod
    def send_text(self, text: str) -> None:
        """Submit text for synthesis without closing the session."""
        raise NotImplementedError

    @abstractmethod
    def iter_audio(self) -> Iterator[StreamChunk]:
        """Yield audio chunks until the session is finished or cancelled."""
        raise NotImplementedError

    @abstractmethod
    def finish(self) -> None:
        """Signal that no more text will be submitted."""
        raise NotImplementedError

    @abstractmethod
    def cancel(self) -> None:
        """Stop synthesis and discard any pending audio."""
        raise NotImplementedError


class StreamingTTSProvider(ABC):
    """Capability contract for TTS providers that accept incremental text."""

    supports_text_streaming = True

    @abstractmethod
    def open_stream(
        self,
        voice: VoiceConfig,
        *,
        directives=None,
        context=None,
    ) -> StreamingTTSSession:
        """Open a text-streaming TTS session for ``voice``."""
        raise NotImplementedError
