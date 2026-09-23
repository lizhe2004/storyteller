from pathlib import Path

import pytest

from storyteller.providers.mock.llm import MockLLMProvider
from storyteller.providers.mock.tts import MockTTSProvider
from storyteller.core.config import Config
from storyteller.core.models import VoiceConfig


# ========== MockLLMProvider ==========
def test_mock_llm_returns_configured_response():
    provider = MockLLMProvider(Config())
    provider.set_response("hello world")
    result = provider.chat([{"role": "user", "content": "hi"}])
    assert result == "hello world"


def test_mock_llm_default_response_is_json_script():
    provider = MockLLMProvider(Config())
    result = provider.chat([{"role": "user", "content": "hi"}])
    assert isinstance(result, str)
    # Default response should be parseable JSON with script structure
    import json
    data = json.loads(result)
    assert "title" in data
    assert "characters" in data
    assert "lines" in data


def test_mock_llm_records_calls():
    provider = MockLLMProvider(Config())
    provider.chat([{"role": "user", "content": "hello"}])
    assert len(provider.calls) == 1
    assert provider.calls[0]["messages"][0]["content"] == "hello"


def test_mock_llm_streams_configured_response_in_chunks():
    provider = MockLLMProvider(Config())
    provider.set_response("abcdefgh")

    chunks = list(provider.chat_stream([{"role": "user", "content": "hi"}]))

    assert "".join(chunks) == "abcdefgh"
    assert len(chunks) > 1


def test_mock_llm_can_simulate_error():
    provider = MockLLMProvider(Config())
    provider.set_error(RuntimeError("simulated failure"))
    with pytest.raises(RuntimeError):
        provider.chat([{"role": "user", "content": "hi"}])


# ========== MockTTSProvider ==========
def test_mock_tts_has_name():
    provider = MockTTSProvider(Config())
    assert provider.name == "mock"


def test_mock_tts_lists_voices():
    provider = MockTTSProvider(Config())
    voices = provider.list_voices()
    assert len(voices) > 0
    for v in voices:
        assert v.provider == "mock"
        assert v.voice_id
    assert next(v for v in voices if v.voice_id == "child_01").age == [
        "child", "teen"
    ]


def test_mock_tts_synthesize_writes_file(tmp_path):
    provider = MockTTSProvider(Config())
    voice = provider.list_voices()[0]
    out = tmp_path / "out.wav"
    result = provider.synthesize("hello", voice, out)
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 0


def test_mock_tts_records_synth_calls(tmp_path):
    provider = MockTTSProvider(Config())
    voice = provider.list_voices()[0]
    out = tmp_path / "out.wav"
    provider.synthesize("hello", voice, out)
    assert len(provider.synth_calls) == 1
    assert provider.synth_calls[0]["text"] == "hello"


def test_mock_tts_can_simulate_error(tmp_path):
    provider = MockTTSProvider(Config())
    provider.set_error(RuntimeError("synth failed"))
    voice = provider.list_voices()[0]
    with pytest.raises(RuntimeError):
        provider.synthesize("hi", voice, tmp_path / "out.wav")
