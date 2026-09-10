from __future__ import annotations

import requests

from ...core.exceptions import LLMError
from ...core.llm import LLMProvider
from ..base import BaseProvider

_DEFAULT_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3"


class VolcengineLLM(BaseProvider, LLMProvider):
    """Volcengine Ark (Doubao) chat completion provider.

    Uses the OpenAI-compatible /chat/completions endpoint.
    """

    def __init__(self, config):
        super().__init__(config)
        provider_config = config.get(
            "llm.provider_config.volcengine", {}
        ) or {}
        self.api_key = provider_config.get("api_key")
        self.model = provider_config.get("model", "doubao-pro-4k")
        self.endpoint = (
            provider_config.get("endpoint") or _DEFAULT_ENDPOINT
        ).rstrip("/")

        if not self.api_key:
            raise LLMError(
                "Volcengine LLM api_key is missing "
                "(STORYTELLER_LLM_VOLCENGINE_API_KEY)"
            )

        self._session = requests.Session()

    def chat(self, messages, temperature=0.7, max_tokens=None, **kwargs):
        url = "{}/chat/completions".format(self.endpoint)
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
                "Volcengine LLM request failed: {}".format(exc)
            ) from exc
        except ValueError as exc:
            raise LLMError("Invalid JSON from Volcengine LLM") from exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                "Unexpected Volcengine LLM response shape: {}".format(data)
            ) from exc
