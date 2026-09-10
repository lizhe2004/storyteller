import pytest
from pathlib import Path

from storyteller.core.llm import LLMProvider
from storyteller.core.tts import TTSProvider
from storyteller.core.audio import AudioProcessor
from storyteller.core.models import VoiceConfig


# ========== LLMProvider abstract ==========
def test_llm_provider_is_abstract():
    with pytest.raises(TypeError):
        LLMProvider()


def test_llm_provider_has_abstract_methods():
    methods = LLMProvider.__abstractmethods__
    assert "chat" in methods


def test_llm_chat_signature():
    import inspect

    sig = inspect.signature(LLMProvider.chat)
    params = list(sig.parameters)
    assert "self" in params
    assert "messages" in params


# ========== TTSProvider abstract ==========
def test_tts_provider_is_abstract():
    with pytest.raises(TypeError):
        TTSProvider()


def test_tts_provider_has_abstract_methods():
    methods = TTSProvider.__abstractmethods__
    assert "list_voices" in methods
    assert "synthesize" in methods


def test_tts_synthesize_signature():
    import inspect

    sig = inspect.signature(TTSProvider.synthesize)
    params = list(sig.parameters)
    assert "text" in params
    assert "voice_config" in params
    assert "output_path" in params


# ========== AudioProcessor abstract ==========
def test_audio_processor_is_abstract():
    with pytest.raises(TypeError):
        AudioProcessor()


def test_audio_processor_has_abstract_methods():
    methods = AudioProcessor.__abstractmethods__
    assert "concatenate" in methods
    assert "convert_format" in methods
