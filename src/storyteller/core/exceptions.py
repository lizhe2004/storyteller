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


class SoundGenerationError(ProviderError):
    """A generated sound was unusable (e.g. near-silent failed output)."""


class AudioProcessingError(StorytellerError):
    """Audio processing errors."""


class ProjectError(StorytellerError):
    """Project save/load errors."""
