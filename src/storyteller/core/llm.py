from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class LLMProvider(ABC):
    """Abstract interface for LLM providers.

    Knows only about text in / text out. Knows nothing about scripts.
    """

    @abstractmethod
    def chat(
        self,
        messages,
        temperature=0.7,
        max_tokens=None,
        **kwargs,
    ):
        """Run a chat completion. messages is a list of
        {"role": ..., "content": ...} dicts. Returns the generated text."""
        raise NotImplementedError

    def complete(
        self,
        prompt,
        temperature=0.7,
        max_tokens=None,
        **kwargs,
    ):
        """Run a completion. Default implementation wraps the prompt as a
        single user message and delegates to chat()."""
        return self.chat(
            [{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
