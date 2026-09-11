from __future__ import annotations

from abc import ABC, abstractmethod


class SoundEffectProvider(ABC):
    """Generates sound effects / ambient beds / music from a text prompt.

    Unlike TTS the output contains no dictated speech: implementations call
    a text-to-audio model (e.g. Volcengine seed-audio) and persist one audio
    file. Generated files are cached by the SoundLibrary, so providers are
    only invoked on a cache miss.
    """

    @property
    @abstractmethod
    def name(self):
        """Provider identifier used in cache fingerprints."""

    #: Concrete model id, used in cache fingerprints and the index.
    model = None

    @abstractmethod
    def generate(
        self,
        prompt,
        output_path,
        *,
        audio_format="mp3",
        sample_rate=None,
        references=None,
    ):
        """Generate one sound for ``prompt`` and write it to output_path.

        Returns ``(path, duration_seconds)`` where duration may be None when
        the provider does not report it.
        """
        raise NotImplementedError
