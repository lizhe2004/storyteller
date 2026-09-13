from __future__ import annotations

from ..core.exceptions import ProviderError

try:
    from .volcengine.llm import VolcengineLLM
    from .volcengine.tts import VolcengineTTS
except ImportError:  # pragma: no cover
    VolcengineLLM = None
    VolcengineTTS = None

try:
    from .openai_compatible.llm import OpenAICompatibleLLM
    from .openai_compatible.tts import OpenAICompatibleTTS
except ImportError:  # pragma: no cover
    OpenAICompatibleLLM = None
    OpenAICompatibleTTS = None

try:
    from .aliyun.tts import AliyunTTS
except ImportError:  # pragma: no cover
    AliyunTTS = None

try:
    from .mock.llm import MockLLMProvider
    from .mock.tts import MockTTSProvider, MockStreamingTTS
except ImportError:  # pragma: no cover
    MockLLMProvider = None
    MockTTSProvider = None
    MockStreamingTTS = None

try:
    from .volcengine.sfx import VolcengineSoundProvider
except ImportError:  # pragma: no cover
    VolcengineSoundProvider = None

try:
    from .mock.sfx import MockSoundProvider
except ImportError:  # pragma: no cover
    MockSoundProvider = None


def register_providers_from_config(config, registry):
    """Register LLM, TTS, and sound providers based on the config's provider lists.

    - Providers listed in ``llm.providers`` / ``tts.providers`` are
      registered (defaulting to the Volcengine implementation unless the
      provider config has ``type: openai_compatible``).
    - OpenAI-compatible providers are parameterized by their configured
      provider name (which config.load_environments assigns from the
      *_NAME env var).
    - The configured default providers are set on the registry.
    """
    _register_llms(config, registry)
    _register_tts(config, registry)
    _register_sounds(config, registry)
    _set_defaults(config, registry)


def _register_llms(config, registry):
    for name in config.get("llm.providers", []) or []:
        provider_config = config.get(
            "llm.provider_config.{}".format(name), {}
        ) or {}
        provider_type = provider_config.get("type")

        if provider_type == "openai_compatible" and OpenAICompatibleLLM:
            registry.register_llm(
                name,
                lambda c, n=name: OpenAICompatibleLLM(c, n),
            )
        elif provider_type == "mock" and MockLLMProvider:
            registry.register_llm(name, lambda c: MockLLMProvider(c))
        elif VolcengineLLM:
            registry.register_llm(name, lambda c: VolcengineLLM(c))
        # Else: no matching implementation, skip quietly.


def _register_tts(config, registry):
    for name in config.get("tts.providers", []) or []:
        provider_config = config.get(
            "tts.provider_config.{}".format(name), {}
        ) or {}
        provider_type = provider_config.get("type")

        if provider_type == "openai_compatible" and OpenAICompatibleTTS:
            registry.register_tts(
                name,
                lambda c, n=name: OpenAICompatibleTTS(c, n),
            )
        elif provider_type == "aliyun" and AliyunTTS:
            registry.register_tts(name, lambda c: AliyunTTS(c))
        elif provider_type == "mock" and MockTTSProvider:
            registry.register_tts(name, lambda c: MockStreamingTTS(c) if MockStreamingTTS else MockTTSProvider(c))
        elif VolcengineTTS:
            registry.register_tts(name, lambda c: VolcengineTTS(c))


def _register_sounds(config, registry):
    for name in config.get("sound.providers", []) or []:
        provider_config = config.get(
            "sound.provider_config.{}".format(name), {}
        ) or {}
        provider_type = provider_config.get("type")

        if provider_type == "mock" and MockSoundProvider:
            registry.register_sound(
                name, lambda c: MockSoundProvider(c)
            )
        elif provider_type in (None, "volcengine") and VolcengineSoundProvider:
            registry.register_sound(
                name, lambda c: VolcengineSoundProvider(c)
            )
        # Other types (aliyun/openai_compatible/...) have no sound
        # implementation yet — skip quietly, like missing LLM impls.


def _set_defaults(config, registry):
    llm_default = config.get("llm.default_provider")
    if llm_default:
        try:
            registry.set_default_llm(llm_default)
        except ProviderError:
            pass  # not registered, ignore

    tts_default = config.get("tts.default_provider")
    if tts_default:
        try:
            registry.set_default_tts(tts_default)
        except ProviderError:
            pass  # not registered, ignore

    sound_default = config.get("sound.default_provider")
    if sound_default:
        try:
            registry.set_default_sound(sound_default)
        except ProviderError:
            pass  # not registered, ignore
