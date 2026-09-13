import json

import pytest

from storyteller.core.config import Config
from storyteller.core.exceptions import LLMError
from storyteller.providers.volcengine.llm import VolcengineLLM


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, raise_exc=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self._raise_exc = raise_exc
        self.stream_lines = []

    def json(self):
        return self._payload

    @property
    def text(self):
        return json.dumps(self._payload, ensure_ascii=False)

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError("status {}".format(self.status_code))

    def iter_lines(self, decode_unicode=False):
        if decode_unicode:
            return iter(self.stream_lines)
        return iter(line.encode("latin-1") for line in self.stream_lines)


class _FakeSession:
    def __init__(self, response=None):
        self._response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self._response


def _config():
    config = Config()
    config.set(
        "llm.provider_config.volcengine",
        {
            "api_key": "test-key",
            "model": "doubao-test",
            "endpoint": "https://ark.example.com/api/v3",
        },
    )
    return config


def test_volcengine_llm_builds_chat_request():
    config = _config()
    llm = VolcengineLLM(config)
    payload = {"choices": [{"message": {"content": "你好"}}]}
    fake = _FakeSession(_FakeResponse(200, payload))
    llm._session = fake

    result = llm.chat(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
    )

    assert result == "你好"
    call = fake.calls[0]
    assert call["url"] == "https://ark.example.com/api/v3/chat/completions"
    body = call["json"]
    assert body["model"] == "doubao-test"
    assert body["messages"][0]["role"] == "system"
    assert call["headers"]["Authorization"] == "Bearer test-key"


def test_volcengine_llm_passes_temperature():
    config = _config()
    llm = VolcengineLLM(config)
    llm._session = _FakeSession(
        _FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})
    )
    llm.chat([{"role": "user", "content": "hi"}], temperature=0.3)
    body = llm._session.calls[0]["json"]
    assert body["temperature"] == 0.3


def test_volcengine_llm_raises_on_http_error():
    config = _config()
    llm = VolcengineLLM(config)
    llm._session = _FakeSession(_FakeResponse(500, {"error": "boom"}))
    with pytest.raises(LLMError):
        llm.chat([{"role": "user", "content": "hi"}])


def test_volcengine_llm_raises_on_missing_key(monkeypatch):
    config = Config()
    monkeypatch.setenv("STORYTELLER_LLM_VOLCENGINE_API_KEY", "")
    with pytest.raises(LLMError):
        VolcengineLLM(config)


def test_volcengine_stream_decodes_utf8_sse_text():
    config = _config()
    llm = VolcengineLLM(config)
    payload = json.dumps(
        {"choices": [{"delta": {"content": "你好，世界"}}]},
        ensure_ascii=False,
    )
    fake_response = _FakeResponse()
    # This simulates requests returning a string decoded with the wrong
    # default charset when iter_lines(decode_unicode=True) is used.
    fake_response.stream_lines = ["data: " + (payload.encode("utf-8").decode("latin-1"))]
    llm._session = _FakeSession(fake_response)

    assert list(llm.chat_stream([{"role": "user", "content": "hi"}])) == [
        "你好，世界"
    ]
