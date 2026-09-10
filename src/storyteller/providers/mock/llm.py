from __future__ import annotations

import json

from ...core.llm import LLMProvider
from ...providers.base import BaseProvider


DEFAULT_SCRIPT = {
    "title": "小猫的冒险",
    "topic": "mock topic",
    "characters": [
        {"id": "narrator", "name": "旁白", "description": "故事旁白"},
        {
            "id": "cat",
            "name": "小橘",
            "description": "一只3岁的橘猫，胆小但善良",
        },
    ],
    "lines": [
        {
            "line_id": "1",
            "line_type": "narration",
            "character_id": None,
            "text": "阳光明媚的一天，小橘在公园里玩耍。",
        },
        {
            "line_id": "2",
            "line_type": "dialogue",
            "character_id": "cat",
            "text": "哇，这里的蝴蝶好漂亮呀！",
        },
        {
            "line_id": "3",
            "line_type": "narration",
            "character_id": None,
            "text": "小橘追着蝴蝶跑进了树林深处。",
        },
        {
            "line_id": "4",
            "line_type": "dialogue",
            "character_id": "cat",
            "text": "糟糕，我迷路了……",
        },
    ],
}


class MockLLMProvider(BaseProvider, LLMProvider):
    """LLM provider that returns canned responses. Used for tests."""

    def __init__(self, config):
        super().__init__(config)
        self._response = json.dumps(DEFAULT_SCRIPT, ensure_ascii=False)
        self._error = None
        self.calls = []

    def set_response(self, response):
        """Configure the text that subsequent chat() calls return."""
        self._response = response

    def set_error(self, error):
        """Configure an error that subsequent chat() calls raise."""
        self._error = error

    def chat(self, messages, temperature=0.7, max_tokens=None, **kwargs):
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "kwargs": kwargs,
            }
        )
        if self._error is not None:
            raise self._error
        return self._response

    def complete(self, prompt, temperature=0.7, max_tokens=None, **kwargs):
        return self.chat(
            [{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
