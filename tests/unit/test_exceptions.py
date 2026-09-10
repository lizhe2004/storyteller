import pytest

from storyteller.core.exceptions import (
    StorytellerError,
    ConfigError,
    ProviderError,
    LLMError,
    TTSError,
    AudioProcessingError,
    ProjectError,
)


def test_all_exceptions_inherit_base():
    assert issubclass(ConfigError, StorytellerError)
    assert issubclass(ProviderError, StorytellerError)
    assert issubclass(LLMError, StorytellerError)
    assert issubclass(TTSError, StorytellerError)
    assert issubclass(AudioProcessingError, StorytellerError)
    assert issubclass(ProjectError, StorytellerError)


def test_llm_and_tts_inherit_provider_error():
    assert issubclass(LLMError, ProviderError)
    assert issubclass(TTSError, ProviderError)


def test_exception_carries_message():
    err = ConfigError("test message")
    assert str(err) == "test message"


def test_can_raise_and_catch():
    with pytest.raises(StorytellerError):
        raise LLMError("llm failed")
