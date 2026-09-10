from __future__ import annotations

import requests

from ...core.exceptions import LLMError
from ...core.llm import LLMProvider
from ..base import BaseProvider


class OpenAICompatibleLLM(BaseProvider, LLMProvider):
    """OpenAI-compatible chat completion provider.

    For any endpoint that speaks the OpenAI /chat/completions wire format.
    """

    def __init__(self, config, provider_name=None):
        super().__init__(config)
        self.provider_name = provider_name or "openai_compatible"
        provider_config = (
            config.get(
                "llm.provider_config.{}".format(self.provider_name)
            )
            or {}
        )
        if not provider_config:
            raise LLMError(
                "No configuration found for LLM provider {}".format(
                    self.provider_name
                )
            )

        self.api_key = provider_config.get("api_key")
        self.base_url = provider_config.get(
            "base_url", provider_config.get("endpoint", "https://api.openai.com/v1")
        )
        self.model = provider_config.get("model", "gpt-4o-mini")

        if not self.api_key:
            raise LLMError(
                "OpenAI-compatible LLM api_key is missing for {}".format(
                    self.provider_name
                )
            )

        self._session = requests.Session()

    def chat(self, messages, temperature=0.7, max_tokens=None, **kwargs):
        url = "{}/chat/completions".format(self.base_url.rstrip("/"))
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        body.update(kwargs)

        headers = {
            "Authorization": "Bearer {}".format(self.api_key),
            "Content-Type": "application/json",
        }

        try:
            response = self._session.post(
                url, headers=headers, json=body, timeout=60
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise LLMError(
                "OpenAI-compatible LLM request failed: {}".format(exc)
            ) from exc
        except ValueError as exc:
            raise LLMError("Invalid JSON from OpenAI-compatible LLM") from exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                "Unexpected OpenAI-compatible LLM response shape: {}".format(
                    data
                )
            ) from exc