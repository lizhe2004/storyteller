import threading

import pytest

from storyteller.core.models import VoiceConfig
from storyteller.core.tts import CHUNK_AUDIO, STREAM_CHANNELS, STREAM_SAMPLE_RATE, STREAM_SAMPLE_WIDTH, StreamChunk
from storyteller.core.exceptions import TTSError
from storyteller.providers.mock.tts import MockStreamingTTS, MockTTSProvider
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
