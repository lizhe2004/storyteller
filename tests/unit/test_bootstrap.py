from storyteller.core.config import Config
from storyteller.providers.registry import ProviderRegistry
from storyteller.providers.bootstrap import register_providers_from_config


def test_register_volcengine_llm_and_tts():
    config = Config()
    config.set("llm.providers", ["volcengine"])
    config.set("llm.default_provider", "volcengine")
    config.set(
        "llm.provider_config.volcengine",
        {"api_key": "llm-key", "model": "doubao"},
    )
    config.set("tts.providers", ["volcengine"])
    config.set(
        "tts.provider_config.volcengine",
        {"api_key": "tts-key"},
    )

    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)

    assert "volcengine" in registry.list_llm_names()
    assert "volcengine" in registry.list_tts_names()
    llm = registry.get_default_llm()
    assert llm is not None
    # Instantiation validates config; with fake key it should succeed.
    assert registry.get_tts("volcengine") is not None


def test_register_openai_compatible_tts():
    config = Config()
    config.set("tts.providers", ["my-custom-tts"])
    config.set(
        "tts.provider_config.my-custom-tts",
        {
            "type": "openai_compatible",
            "api_key": "custom-key",
            "base_url": "https://custom.example.com/v1",
            "model": "custom-model",
        },
    )

    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)

    assert "my-custom-tts" in registry.list_tts_names()
    tts = registry.get_tts("my-custom-tts")
    assert tts.name == "my-custom-tts"
    assert tts.base_url == "https://custom.example.com/v1"
    assert tts.model == "custom-model"


def test_register_openai_compatible_llm():
    config = Config()
    config.set("llm.providers", ["custom-llm"])
    config.set(
        "llm.provider_config.custom-llm",
        {
            "type": "openai_compatible",
            "api_key": "llm-key",
            "base_url": "https://llm.example.com/v1",
            "model": "llm-model",
        },
    )

    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)

    assert "custom-llm" in registry.list_llm_names()
    llm = registry.get_llm("custom-llm")
    assert llm.model == "llm-model"


def test_register_aliyun_tts():
    config = Config()
    config.set("tts.providers", ["aliyun"])
    config.set(
        "tts.provider_config.aliyun",
        {
            "type": "aliyun",
            "api_key": "dashscope-key",
            "model": "qwen-audio-3.0-tts-flash",
        },
    )

    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)

    assert "aliyun" in registry.list_tts_names()
    tts = registry.get_tts("aliyun")
    assert tts is not None
    assert tts.name == "aliyun"
    assert tts.model == "qwen-audio-3.0-tts-flash"


def test_register_skips_unknown_defaults():
    config = Config()
    config.set("llm.providers", ["volcengine"])
    config.set(
        "llm.provider_config.volcengine",
        {"api_key": "x"},
    )
    config.set("llm.default_provider", "does-not-exist")

    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)

    # Default that isn't registered is ignored; no exception raised.
    assert registry.get_default_llm() is None


def test_register_mock_sound_provider():
    config = Config()
    config.set("sound.providers", ["mock"])
    config.set("sound.default_provider", "mock")
    config.set("sound.provider_config.mock", {"type": "mock"})

    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)

    assert registry.list_sound_names() == ["mock"]
    assert registry.get_sound("mock").name == "mock"
    assert registry.get_default_sound() is not None


def test_register_volcengine_sound_provider_lazily():
    config = Config()
    config.set("sound.providers", ["volcengine"])
    config.set(
        "sound.provider_config.volcengine",
        {"api_key": "sound-key"},
    )

    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)

    # Factory registered without instantiation (missing key would raise at
    # construction time; here the key exists, but listing must stay lazy).
    assert registry.list_sound_names() == ["volcengine"]


def test_unsupported_sound_type_is_skipped():
    config = Config()
    config.set("sound.providers", ["aliyun"])
    config.set(
        "sound.provider_config.aliyun",
        {"type": "aliyun", "api_key": "k"},
    )

    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)

    assert registry.list_sound_names() == []
