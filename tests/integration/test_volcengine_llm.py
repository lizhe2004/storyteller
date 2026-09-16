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

    def iter_lines(self, decode_unicode=False, **kwargs):
        if decode_unicode:
            return iter(self.stream_lines)
        return iter(
            line if isinstance(line, bytes) else line.encode("latin-1")
            for line in self.stream_lines
        )


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


def test_volcengine_llm_disables_thinking_by_default():
    config = _config()
    llm = VolcengineLLM(config)
    llm._session = _FakeSession(
        _FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})
    )

    llm.chat([{"role": "user", "content": "hi"}])

    assert llm._session.calls[0]["json"]["thinking"] == {"type": "disabled"}


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


def test_volcengine_stream_disables_thinking_by_default():
    config = _config()
    llm = VolcengineLLM(config)
    fake_response = _FakeResponse()
    fake_response.stream_lines = [b"data: [DONE]"]
    llm._session = _FakeSession(fake_response)

    list(llm.chat_stream([{"role": "user", "content": "hi"}]))

    assert llm._session.calls[0]["json"]["thinking"] == {"type": "disabled"}


def test_volcengine_stream_logs_only_provider_http_context(caplog):
    config = _config()
    llm = VolcengineLLM(config)
    fake_response = _FakeResponse()
    fake_response.stream_lines = [
        b'data: {"choices":[{"delta":{"content":"ok"}}]}',
        b'data: [DONE]',
    ]
    fake = _FakeSession(fake_response)
    llm._session = fake

    with caplog.at_level("INFO", logger="storyteller.providers.volcengine.llm"):
        assert list(llm.chat_stream(
            [{"role": "user", "content": "hi"}],
        )) == ["ok"]

    body = fake.calls[0]["json"]
    assert "log_context" not in body
    assert "operation" not in body
    message = "\n".join(record.getMessage() for record in caplog.records)
    assert "event=llm_http_request_started" in message
    assert "operation=chat_stream" in message
    assert "phase=" not in message
    assert "job_id=" not in message


def test_volcengine_stream_logs_first_chunk_latency(caplog):
    config = _config()
    llm = VolcengineLLM(config)
    fake_response = _FakeResponse()
    fake_response.stream_lines = [
        'data: {"choices":[{"delta":{"content":"首段"}}]}'.encode("utf-8"),
        b'data: [DONE]',
    ]
    llm._session = _FakeSession(fake_response)

    with caplog.at_level("INFO", logger="storyteller.providers.volcengine.llm"):
        assert list(llm.chat_stream([{"role": "user", "content": "hi"}])) == [
            "首段"
        ]

    message = "\n".join(record.getMessage() for record in caplog.records)
    assert "event=llm_first_chunk_received" in message
    assert "time_to_first_chunk_ms=" in message


def test_volcengine_stream_logs_each_chunk_at_debug(caplog):
    config = _config()
    llm = VolcengineLLM(config)
    fake_response = _FakeResponse()
    fake_response.stream_lines = [
        'data: {"choices":[{"delta":{"content":"一"}}]}'.encode("utf-8"),
        'data: {"choices":[{"delta":{"content":"二"}}]}'.encode("utf-8"),
        b'data: [DONE]',
    ]
    llm._session = _FakeSession(fake_response)

    with caplog.at_level("DEBUG", logger="storyteller.providers.volcengine.llm"):
        assert list(llm.chat_stream([{"role": "user", "content": "hi"}])) == [
            "一", "二"
        ]

    messages = [record.getMessage() for record in caplog.records]
    chunk_logs = [message for message in messages if "event=llm_chunk_received" in message]
    assert len(chunk_logs) == 2
    assert "chunk_index=1" in chunk_logs[0]
    assert "chunk_index=2" in chunk_logs[1]
    assert "chunk_content=一" in chunk_logs[0]
    assert "chunk_content=二" in chunk_logs[1]
    assert "wait_since_previous_chunk_ms=" in chunk_logs[0]
