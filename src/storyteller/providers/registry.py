from __future__ import annotations

from typing import Optional

from ..core.exceptions import ProviderError
from ..core.models import VoiceConfig


class ProviderRegistry:
    """Central registry for LLM and TTS providers.

    Providers are instantiated once and cached. TTS voice lists are
    aggregated across registered providers, optionally filtered.
    """

    def __init__(self, config):
        self.config = config
        self._llm_factories = {}
        self._tts_factories = {}
        self._llm_instances = {}
        self._tts_instances = {}
        self._default_llm = None
        self._default_tts = None

    # ----- LLM -----
    def register_llm(self, name, factory):
        """Register an LLM provider. factory may be a class or callable
        taking (config) and returning an LLMProvider instance."""
        self._llm_factories[name] = factory

    def get_llm(self, name):
        """Get (and lazily instantiate) an LLM provider by name."""
        if name not in self._llm_factories:
            raise ProviderError("Unknown LLM provider: {}".format(name))
        if name not in self._llm_instances:
            self._llm_instances[name] = self._llm_factories[name](self.config)
        return self._llm_instances[name]

    def set_default_llm(self, name):
        if name not in self._llm_factories:
            raise ProviderError("Unknown LLM provider: {}".format(name))
        self._default_llm = name

    def get_default_llm(self):
        if self._default_llm is None:
            return None
        return self.get_llm(self._default_llm)

    def list_llm_names(self):
        return list(self._llm_factories.keys())

    # ----- TTS -----
    def register_tts(self, name, factory):
        """Register a TTS provider. factory may be a class or callable
        taking (config) and returning a TTSProvider instance."""
        self._tts_factories[name] = factory

    def get_tts(self, name):
        if name not in self._tts_factories:
            raise ProviderError("Unknown TTS provider: {}".format(name))
        if name not in self._tts_instances:
            self._tts_instances[name] = self._tts_factories[name](self.config)
        return self._tts_instances[name]

    def set_default_tts(self, name):
        if name not in self._tts_factories:
            raise ProviderError("Unknown TTS provider: {}".format(name))
        self._default_tts = name

    def get_default_tts(self):
        if self._default_tts is None:
            return None
        return self.get_tts(self._default_tts)

    def list_tts_names(self):
        return list(self._tts_factories.keys())

    # ----- Voice aggregation -----
    def list_tts_voices(self, provider_names=None, allowed_voice_ids=None):
        """Aggregate voices across the given providers (or all if None).
        Optionally filter to a set of voice_ids."""
        if provider_names is None:
            provider_names = self.list_tts_names()

        voices = []
        for name in provider_names:
            if name not in self._tts_factories:
                continue
            tts = self.get_tts(name)
            voices.extend(tts.list_voices())

        if allowed_voice_ids is not None:
            voices = [v for v in voices if v.voice_id in allowed_voice_ids]
        return voices
