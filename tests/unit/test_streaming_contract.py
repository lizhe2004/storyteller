from storyteller.core.models import VoiceConfig
from storyteller.core.tts import CHUNK_AUDIO, STREAM_CHANNELS, STREAM_SAMPLE_RATE, STREAM_SAMPLE_WIDTH, StreamChunk
from storyteller.providers.mock.tts import MockStreamingTTS, MockTTSProvider
from storyteller.providers.registry import ProviderRegistry


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
