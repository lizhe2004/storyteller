from __future__ import annotations

import json
import logging
import requests
import time

from ...core.exceptions import LLMError
from ...core.llm import LLMProvider
from ..base import BaseProvider
from ...core.observability import timed_event
from ...core.observability import log_event

logger = logging.getLogger(__name__)

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
        self.model = provider_config.get("model", "deepseek-v4-flash-260425")
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
            "thinking": {"type": "disabled"},
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        body.update(kwargs)

        headers = {
            "Authorization": "Bearer {}".format(self.api_key),
            "Content-Type": "application/json",
        }

        try:
            with timed_event(logger, "llm_http_request", operation="chat",
                             provider="volcengine",
                             model=self.model):
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

    def chat_stream(self, messages, temperature=0.7, max_tokens=None, **kwargs):
        url = "{}/chat/completions".format(self.endpoint)
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "thinking": {"type": "disabled"},
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        body.update(kwargs)
        headers = {
            "Authorization": "Bearer {}".format(self.api_key),
            "Content-Type": "application/json",
        }
        request_started = time.perf_counter()
        last_chunk_at = request_started
        chunk_index = 0
        first_chunk_logged = False
        try:
            with timed_event(logger, "llm_http_request", operation="chat_stream",
                             provider="volcengine",
                             model=self.model):
                response = self._session.post(
                    url, headers=headers, json=body, stream=True, timeout=60
                )
                response.raise_for_status()
                # Decode explicitly as UTF-8. requests may otherwise use a
                # latin-1-like default for text/event-stream and corrupt Chinese.
                for line in response.iter_lines(decode_unicode=False):
                    chunk = _content_from_sse_line(line)
                    if chunk:
                        now = time.perf_counter()
                        chunk_index += 1
                        wait_ms = int((now - last_chunk_at) * 1000)
                        log_event(
                            logger, logging.DEBUG, "llm_chunk_received",
                            provider="volcengine", model=self.model,
                            operation="chat_stream", chunk_index=chunk_index,
                            chunk_length=len(chunk),
                            chunk_content=chunk,
                            wait_since_previous_chunk_ms=wait_ms,
                            elapsed_ms=int((now - request_started) * 1000),
                        )
                        if wait_ms >= 500:
                            log_event(
                                logger, logging.DEBUG, "llm_chunk_gap_detected",
                                provider="volcengine", model=self.model,
                                operation="chat_stream", chunk_index=chunk_index,
                                gap_ms=wait_ms,
                                message="等待LLM下一个流式chunk",
                            )
                        last_chunk_at = now
                        if not first_chunk_logged:
                            log_event(
                                logger, logging.INFO,
                                "llm_first_chunk_received",
                                provider="volcengine", model=self.model,
                                operation="chat_stream",
                                time_to_first_chunk_ms=int(
                                    (time.perf_counter() - request_started) * 1000
                                ),
                            )
                            first_chunk_logged = True
                        yield chunk
        except requests.RequestException as exc:
            raise LLMError(
                "Volcengine streaming LLM request failed: {}".format(exc)
            ) from exc


def _content_from_sse_line(line):
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    line = (line or "").strip()
    if not line or not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if payload == "[DONE]":
        return None
    try:
        data = json.loads(payload)
        choice = (data.get("choices") or [{}])[0]
        delta = choice.get("delta") or {}
        return delta.get("content") or choice.get("message", {}).get("content")
    except (TypeError, ValueError, KeyError, IndexError):
        return None
