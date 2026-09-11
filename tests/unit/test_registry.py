import pytest

from storyteller.core.config import Config
from storyteller.core.llm import LLMProvider
from storyteller.core.tts import TTSProvider
from storyteller.core.models import VoiceConfig
from storyteller.providers.base import BaseProvider
from storyteller.providers.registry import ProviderRegistry
from storyteller.core.exceptions import ConfigError, ProviderError


# ========== Test fixtures ==========
class FakeLLM(BaseProvider, LLMProvider):
    def chat(self, messages, temperature=0.7, max_tokens=None, **kwargs):
        return "fake-llm-response"


class FakeTTS(BaseProvider, TTSProvider):
    @property
    def name(self):
        return "fake"

    def list_voices(self, **kwargs):
        return [
            VoiceConfig(
                provider="fake",
                voice_id="v1",
                gender="female",
                category="有声阅读",
            )
        ]

    def synthesize(self, text, voice_config, output_path, **kwargs):
        return output_path


# ========== BaseProvider ==========
def test_base_provider_takes_config():
    config = Config()
    provider = FakeLLM(config)
    assert provider.config is config


def test_base_provider_validate_config_passes_by_default():
    config = Config()
    FakeLLM(config)


# ========== ProviderRegistry LLM ==========
def test_registry_register_and_get_llm():
    config = Config()
    registry = ProviderRegistry(config)
    registry.register_llm("fake", FakeLLM)
    llm = registry.get_llm("fake")
    assert isinstance(llm, FakeLLM)
    assert llm.chat([]) == "fake-llm-response"


def test_registry_get_unknown_llm_raises():
    config = Config()
    registry = ProviderRegistry(config)
    with pytest.raises(ProviderError):
        registry.get_llm("nonexistent")


def test_registry_default_llm():
    config = Config()
    registry = ProviderRegistry(config)
    registry.register_llm("fake", FakeLLM)
    registry.set_default_llm("fake")
    assert registry.get_default_llm() is not None


# ========== ProviderRegistry TTS ==========
def test_registry_register_and_get_tts():
    config = Config()
    registry = ProviderRegistry(config)
    registry.register_tts("fake", FakeTTS)
    tts = registry.get_tts("fake")
    assert isinstance(tts, FakeTTS)
    assert tts.name == "fake"


def test_registry_get_unknown_tts_raises():
    config = Config()
    registry = ProviderRegistry(config)
    with pytest.raises(ProviderError):
        registry.get_tts("nonexistent")


def test_registry_list_tts_voices():
    config = Config()
    registry = ProviderRegistry(config)
    registry.register_tts("fake", FakeTTS)
    voices = registry.list_tts_voices(["fake"])
    assert len(voices) == 1
    assert voices[0].voice_id == "v1"
    assert voices[0].provider == "fake"


def test_registry_list_tts_voices_filtered():
    config = Config()
    registry = ProviderRegistry(config)
    registry.register_tts("fake", FakeTTS)
    # Filter to a voice_id that doesn't exist
    voices = registry.list_tts_voices(["fake"], allowed_voice_ids={"nope"})
    assert len(voices) == 0


def test_registry_list_tts_voices_subset_of_providers():
    config = Config()
    registry = ProviderRegistry(config)
    registry.register_tts("fake", FakeTTS)
    # Only asking for a provider that isn't registered
    voices = registry.list_tts_voices(["other"])
    assert len(voices) == 0


def test_registry_default_tts():
    config = Config()
    registry = ProviderRegistry(config)
    registry.register_tts("fake", FakeTTS)
    registry.set_default_tts("fake")
    assert registry.get_default_tts() is not None


def test_registry_list_registered_names():
    config = Config()
    registry = ProviderRegistry(config)
    registry.register_llm("fake", FakeLLM)
    registry.register_tts("fake", FakeTTS)
    assert "fake" in registry.list_llm_names()
    assert "fake" in registry.list_tts_names()
