import threading

import pytest

from storyteller.core.models import VoiceConfig
from storyteller.core.tts import CHUNK_AUDIO, STREAM_CHANNELS, STREAM_SAMPLE_RATE, STREAM_SAMPLE_WIDTH, StreamChunk
from storyteller.core.exceptions import TTSError
from storyteller.providers.mock.tts import (
    MockStreamingTTS,
    MockStreamingTTSSession,
    MockTTSProvider,
)
from storyteller.providers.registry import ProviderRegistry


class SessionFlagOnlyTTS(MockTTSProvider):
    supports_text_streaming = True


def test_wire_constants():
    assert (STREAM_SAMPLE_RATE, STREAM_CHANNELS, STREAM_SAMPLE_WIDTH) == (24000, 1, 2)


def test_registry_capability_detection():
    registry = ProviderRegistry(config={})
    registry.register_tts("plain", MockTTSProvider)
    registry.register_tts("stream", MockStreamingTTS)
    assert registry.get_stream_tts("plain") is None
    assert registry.get_stream_tts("stream").supports_streaming


def test_mock_stream_is_standard_pcm():
    provider = MockStreamingTTS({})
    chunks = list(provider.stream_synthesize("测试", VoiceConfig(provider="mock", voice_id="v")))
    assert chunks and all(isinstance(c, StreamChunk) and c.kind == CHUNK_AUDIO for c in chunks)
    assert len(b"".join(c.data for c in chunks)) == 24000


def test_mock_streaming_session_emits_audio_before_finish_and_closes_on_finish():
    """Removing queued audio, or closing before finish, must break this contract."""
    provider = MockStreamingTTS({})
    session = provider.open_stream(VoiceConfig(provider="mock", voice_id="v"))

    session.send_text("第一段")
    audio = next(session.iter_audio())
    session.send_text("第二段")

    assert audio.kind == CHUNK_AUDIO
    assert isinstance(audio.data, bytes)
    assert len(audio.data) == STREAM_SAMPLE_RATE * STREAM_SAMPLE_WIDTH // 10

    stream = session.iter_audio()
    assert next(stream).kind == CHUNK_AUDIO
    stopped = threading.Event()

    def wait_for_close():
        with pytest.raises(StopIteration):
            next(stream)
        stopped.set()

    waiter = threading.Thread(target=wait_for_close)
    waiter.start()
    assert not stopped.wait(0.05)

    session.finish()
    waiter.join(timeout=1)
    assert stopped.is_set()


def test_registry_returns_none_when_provider_has_no_text_streaming_session():
    """Accidentally treating legacy stream_synthesize as the new API must fail."""
    registry = ProviderRegistry(config={})
    registry.register_tts("plain", SessionFlagOnlyTTS)

    assert registry.get_streaming_tts("plain") is None


def test_mock_streaming_session_translates_provider_failures_to_tts_error():
    """Leaking arbitrary provider errors from a session must fail."""
    provider = MockStreamingTTS({})
    provider.set_error(RuntimeError("upstream unavailable"))
    session = provider.open_stream(VoiceConfig(provider="mock", voice_id="v"))

    with pytest.raises(TTSError, match="upstream unavailable"):
        session.send_text("失败")


def test_mock_streaming_session_cancel_rejects_a_sender_blocked_by_full_audio_buffer(
    monkeypatch,
):
    """Reintroducing an enqueue after cancel must fail this full-buffer race."""
    class GatedChunkProvider(MockStreamingTTS):
        def __init__(self):
            super().__init__({})
            self.chunk_started = threading.Event()
            self.release_chunk = threading.Event()

        def _stream_chunk(self, text, voice_config, **kwargs):
            if text == "blocked":
                self.chunk_started.set()
                assert self.release_chunk.wait(timeout=1)
            return super()._stream_chunk(text, voice_config, **kwargs)

    monkeypatch.setattr(MockStreamingTTSSession, "_QUEUE_SIZE", 1)
    provider = GatedChunkProvider()
    session = provider.open_stream(VoiceConfig(provider="mock", voice_id="v"))
    session.send_text("already queued")
    sender_done = threading.Event()
    sender_error = []

    def submit_blocked_text():
        try:
            session.send_text("blocked")
        except Exception as exc:
            sender_error.append(exc)
        finally:
            sender_done.set()

    sender = threading.Thread(target=submit_blocked_text)
    sender.start()
    assert provider.chunk_started.wait(timeout=1)

    provider.release_chunk.set()
    session.cancel()
    assert sender_done.wait(timeout=1)
    sender.join()

    assert len(sender_error) == 1
    assert isinstance(sender_error[0], TTSError)
    assert list(session.iter_audio()) == []


def test_mock_streaming_session_snapshots_voice_config_when_opened():
    """Passing the caller's mutable VoiceConfig through later chunks must fail."""
    provider = MockStreamingTTS({})
    voice = VoiceConfig(
        provider="mock",
        voice_id="original",
        language="zh-CN",
        style="warm",
        speed=0.8,
        pitch=1.2,
        volume=0.6,
    )
    session = provider.open_stream(voice)

    voice.voice_id = "mutated"
    voice.language = "en-US"
    voice.style = "flat"
    voice.speed = 1.5
    voice.pitch = 0.7
    voice.volume = 1.0
    session.send_text("uses original voice")

    assert provider.synth_calls[-1]["voice_config"] == VoiceConfig(
        provider="mock",
        voice_id="original",
        language="zh-CN",
        style="warm",
        speed=0.8,
        pitch=1.2,
        volume=0.6,
    )
    assert provider.synth_calls[-1]["voice_config"] is not voice
