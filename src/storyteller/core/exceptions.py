class StorytellerError(Exception):
    """Base exception for all storyteller errors."""


class ConfigError(StorytellerError):
    """Configuration related errors."""


class ProviderError(StorytellerError):
    """Provider related errors."""


class LLMError(ProviderError):
    """LLM provider errors."""


class TTSError(ProviderError):
    """TTS provider errors."""


class AudioProcessingError(StorytellerError):
    """Audio processing errors."""


class ProjectError(StorytellerError):
    """Project save/load errors."""
