"""Unit tests for provider ``list_models()`` implementations."""

import pytest

from storyteller.core.config import Config
from storyteller.core.exceptions import LLMError, TTSError
from storyteller.providers.aliyun.tts import AliyunTTS
from storyteller.providers.openai_compatible.llm import OpenAICompatibleLLM
from storyteller.providers.openai_compatible.tts import OpenAICompatibleTTS
from storyteller.providers.volcengine.llm import VolcengineLLM
from storyteller.providers.volcengine.tts import VolcengineTTS


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, *payloads):
        self._payloads = list(payloads)
        self.requests = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.requests.append({"url": url, "params": params})
        payload = self._payloads.pop(0) if self._payloads else {"data": []}
        return _FakeResponse(payload)


def _config(**entries):
    config = Config()
    for path, value in entries.items():
        config.set(path.replace("__", "."), value)
    return config


def test_volcengine_llm_lists_active_then_retiring_chat_models():
    provider = VolcengineLLM(
        _config(llm__provider_config__volcengine={"api_key": "test-key"})
    )
    provider._session = _FakeSession(
        {
            "data": [
                {"id": "deepseek-v4-flash-ga-260731", "domain": "LLM"},
                {"id": "doubao-seed-2-1-pro-260628", "domain": "VLM"},
                {
                    "id": "deepseek-v4-flash-260425",
                    "domain": "LLM",
                    "status": "Retiring",
                },
                {"id": "doubao-seed-1-8-251228", "domain": "VLM", "status": "Retiring"},
                {"id": "doubao-old", "domain": "LLM", "status": "Shutdown"},
                {"id": "doubao-seed-2-0-old", "domain": "VLM", "status": "Shutdown"},
                {"id": "doubao-seedream-4-0", "domain": "ImageGeneration"},
                {"id": "embedding-x", "domain": "Embedding"},
                {"domain": "LLM"},
                "junk",
            ]
        }
    )

    assert provider.list_models() == [
        {"id": "deepseek-v4-flash-ga-260731", "retiring": False},
        {"id": "doubao-seed-2-1-pro-260628", "retiring": False},
        {"id": "deepseek-v4-flash-260425", "retiring": True},
        {"id": "doubao-seed-1-8-251228", "retiring": True},
    ]
    assert provider._session.requests[0]["url"].endswith("/api/v3/models")


def test_volcengine_llm_rejects_bad_payload():
    provider = VolcengineLLM(
        _config(llm__provider_config__volcengine={"api_key": "test-key"})
    )
    provider._session = _FakeSession({"unexpected": True})

    with pytest.raises(LLMError):
        provider.list_models()


def test_openai_compatible_llm_lists_models():
    provider = OpenAICompatibleLLM(
        _config(
            llm__provider_config__openai={
                "type": "openai_compatible",
                "api_key": "test-key",
                "base_url": "https://llm.example/v1/",
            }
        ),
        provider_name="openai",
    )
    provider._session = _FakeSession(
        {"data": [{"id": "model-b"}, {"id": "model-a"}, {"no_id": 1}]}
    )

    assert provider.list_models() == [
        {"id": "model-a", "retiring": False},
        {"id": "model-b", "retiring": False},
    ]
    assert (
        provider._session.requests[0]["url"] == "https://llm.example/v1/models"
    )


def test_openai_compatible_tts_filters_audio_models():
    provider = OpenAICompatibleTTS(
        _config(
            tts__provider_config__openai={
                "type": "openai_compatible",
                "api_key": "test-key",
                "base_url": "https://tts.example/v1",
            }
        ),
        provider_name="openai",
    )
    provider._session = _FakeSession(
        {
            "data": [
                {"id": "gpt-4o"},
                {"id": "gpt-4o-mini-tts"},
                {"id": "qwen-speech-pro"},
                {"id": "text-embedding-3"},
            ]
        }
    )

    assert provider.list_models() == [
        {"id": "gpt-4o-mini-tts", "retiring": False},
        {"id": "qwen-speech-pro", "retiring": False},
    ]


def test_volcengine_tts_lists_catalog_resource_ids():
    provider = VolcengineTTS(
        _config(tts__provider_config__volcengine={"api_key": "test-key"})
    )

    assert provider.list_models() == [{"id": "seed-tts-2.0", "retiring": False}]


def test_volcengine_tts_filters_voices_by_enabled_resource_ids():
    provider = VolcengineTTS(
        _config(
            tts__provider_config__volcengine={
                "api_key": "test-key",
                "models": "resource-that-is-not-in-catalog",
            }
        )
    )

    assert provider.list_voices() == []


def test_aliyun_tts_falls_back_to_catalog_without_workspace():
    provider = AliyunTTS(
        _config(tts__provider_config__aliyun={"api_key": "test-key"})
    )

    models = provider.list_models()
    assert models
    assert {"id": "qwen-audio-3.0-tts-plus", "retiring": False} in models


def test_aliyun_tts_merges_remote_models_with_catalog():
    provider = AliyunTTS(
        _config(
            tts__provider_config__aliyun={
                "api_key": "test-key",
                "workspace_id": "ws-1",
            }
        )
    )
    provider._session = _FakeSession(
        {"output": {"total": 2, "page_no": 1, "models": [
            {"model": "qwen-tts-new"},
            {
                "model": "qwen-tts-old",
                "inference_offline_info": {"offline_time": "2026-12-31 00:00:00"},
            },
        ]}}
    )

    models = provider.list_models()
    assert {"id": "qwen-tts-new", "retiring": False} in models
    assert {"id": "qwen-tts-old", "retiring": True} in models
    assert {"id": "qwen-audio-3.0-tts-plus", "retiring": False} in models
    call = provider._session.requests[0]
    assert (
        call["url"] == "https://ws-1.cn-beijing.maas.aliyuncs.com/api/v1/models"
    )
    assert ("capabilities", "TTS") in call["params"]
    assert ("capabilities", "Realtime-Text-to-Speech") in call["params"]


def test_aliyun_tts_paginates_until_total():
    provider = AliyunTTS(
        _config(
            tts__provider_config__aliyun={
                "api_key": "test-key",
                "workspace_id": "ws-1",
            }
        )
    )
    page_one = [{"model": "remote-{:03d}".format(i)} for i in range(100)]
    provider._session = _FakeSession(
        {"output": {"total": 101, "page_no": 1, "models": page_one}},
        {"output": {"total": 101, "page_no": 2, "models": [{"model": "remote-100"}]}},
    )

    models = provider.list_models()
    assert {"id": "remote-000", "retiring": False} in models
    assert {"id": "remote-100", "retiring": False} in models
    assert len(provider._session.requests) == 2
