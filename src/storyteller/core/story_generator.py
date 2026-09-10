from __future__ import annotations

import json
import re

from .exceptions import LLMError
from .llm import LLMProvider
from .models import Character, Script, ScriptLine
from .utils import generate_id


DEFAULT_SYSTEM_PROMPT = (
    "你是一位专业的广播剧编剧。请根据用户给定的故事主题，创作一个"
    "多角色的音频故事剧本。\n\n"
    "要求：\n"
    "1. 剧本包含旁白和至少2个对话角色。\n"
    "2. 严格以JSON格式输出，不要包含任何其他文字。格式如下：\n"
    '{\n'
    '  "title": "故事标题",\n'
    '  "characters": [\n'
    '    {"id": "角色id", "name": "角色名", "description": "角色性格/年龄/性别描述"}\n'
    '  ],\n'
    '  "lines": [\n'
    '    {"line_id": "1", "line_type": "narration", "text": "旁白内容"},\n'
    '    {"line_id": "2", "line_type": "dialogue", "character_id": "角色id", "text": "台词"}\n'
    '  ]\n'
    '}\n'
    "3. 旁白的 line_type 为 narration，对话的 line_type 为 dialogue，"
    "对话必须提供 character_id。\n"
    "4. 角色描述请包含年龄、性别、性格等信息，便于后续匹配声音。\n"
)


class StoryGenerator:
    """Turns a topic into a Script by prompting an LLM.

    Owns the prompt-building and response-parsing business logic. Knows
    nothing about which LLM provider is used.
    """

    def __init__(self, llm, system_prompt=None):
        self.llm = llm
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    def generate_script(
        self,
        topic,
        length="medium",
        complexity="simple",
        **kwargs,
    ):
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": self._build_user_prompt(
                    topic, length, complexity
                ),
            },
        ]
        try:
            response = self.llm.chat(messages, **kwargs)
        except Exception as exc:
            raise LLMError("LLM call failed: {}".format(exc)) from exc
        return self._parse_response(response, topic)

    def refine_script(self, script, feedback, **kwargs):
        """Regenerate a script given feedback (reserved for later)."""
        raise NotImplementedError("refine_script not implemented")

    # ----- internals -----
    def _build_user_prompt(self, topic, length, complexity):
        return (
            "请围绕以下主题创作一个故事剧本：{}\n\n"
            "故事长度：{}\n"
            "剧本复杂度：{}"
        ).format(topic, length, complexity)

    def _parse_response(self, response, topic):
        data = _extract_json(response)
        if data is None:
            raise LLMError(
                "LLM returned unparseable content: {}".format(
                    _truncate(response, 200)
                )
            )
        return _script_from_json(data, topic)


def _extract_json(text):
    """Extract a JSON object from LLM output.

    Handles responses wrapped in markdown code fences (```json ... ```)
    or with surrounding prose.
    """
    if not text:
        return None
    text = text.strip()

    # Try parsing directly first.
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass

    # Strip code fences.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except (ValueError, TypeError):
            pass

    # Find the first {...} block as a last resort.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except (ValueError, TypeError):
            pass

    return None


def _script_from_json(data, topic):
    characters = []
    char_lookup = {}
    for idx, raw_char in enumerate(data.get("characters") or []):
        char = Character(
            id=str(raw_char.get("id") or "char_{}".format(idx)),
            name=str(raw_char.get("name") or "角色{}".format(idx + 1)),
            description=str(raw_char.get("description") or ""),
        )
        characters.append(char)
        char_lookup[char.id] = char

    lines = []
    for raw_line in data.get("lines") or []:
        line_type = str(raw_line.get("line_type") or "narration")
        char_id = raw_line.get("character_id")
        lines.append(
            ScriptLine(
                line_id=str(raw_line.get("line_id") or generate_id("l_")),
                line_type=line_type,
                character_id=str(char_id) if char_id else None,
                text=str(raw_line.get("text") or ""),
            )
        )

    return Script(
        script_id=generate_id("script_"),
        title=str(data.get("title") or "未命名故事"),
        topic=topic,
        characters=characters,
        lines=lines,
        metadata={
            "length": data.get("length"),
            "complexity": data.get("complexity"),
        },
    )


def _truncate(text, limit):
    text = text or ""
    return text[:limit] + ("..." if len(text) > limit else "")
