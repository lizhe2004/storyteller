import base64
from pathlib import Path

import pytest

from storyteller.core.config import Config
from storyteller.core.exceptions import TTSError
from storyteller.core.models import VoiceConfig
from storyteller.providers.openai_compatible.tts import OpenAICompatibleTTS


class _FakeSession:
    def __init__(self, response=None):
        self._response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self._response


class _FakeResponse:
    def __init__(self, content=b"", status_code=200, raise_exc=None):
        self._content = content
        self.status_code = status_code
        self._raise_exc = raise_exc

    @property
    def content(self):
        return self._content

    @property
    def text(self):
        return self._content.decode("utf-8", errors="ignore")

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError("status {}".format(self.status_code))


def _config():
    config = Config()
    config.set(
        "tts.provider_config.custom-tts",
        {
            "type": "openai_compatible",
            "api_key": "custom-key",
            "base_url": "https://custom.example.com/v1",
            "model": "tts-model",
        },
    )
    return config


def _tts():
    tts = OpenAICompatibleTTS(_config(), "custom-tts")
    tts._session = _FakeSession(_FakeResponse(b"fake-audio"))
    return tts


def test_openai_tts_name_is_provider_name():
    tts = _tts()
    assert tts.name == "custom-tts"


def test_openai_tts_lists_builtin_voices():
    tts = _tts()
    voices = tts.list_voices()
    by_id = {v.voice_id: v for v in voices}
    assert "alloy" in by_id
    assert "nova" in by_id
    assert "shimmer" in by_id
    assert by_id["alloy"].gender is None
    assert by_id["nova"].gender == "female"
    assert by_id["onyx"].gender == "male"
    assert all(not hasattr(v, "voice_type") for v in voices)


def test_openai_tts_synthesize(tmp_path):
    tts = _tts()
    voice = tts.list_voices()[0]
    out = tmp_path / "out.mp3"
    result = tts.synthesize("hello", voice, out)

    assert result == out
    assert out.read_bytes() == b"fake-audio"

    call = tts._session.calls[0]
    assert call["url"] == "https://custom.example.com/v1/audio/speech"
    assert call["headers"]["Authorization"] == "Bearer custom-key"
    body = call["json"]
    assert body["input"] == "hello"
    assert body["model"] == "tts-model"
    assert body["voice"] == voice.voice_id
    assert body["response_format"] == "mp3"


def test_openai_tts_synthesize_wav_format(tmp_path):
    tts = _tts()
    voice = tts.list_voices()[0]
    out = tmp_path / "out.wav"
    tts.synthesize("hello", voice, out)
    body = tts._session.calls[0]["json"]
    assert body["response_format"] == "wav"


def test_openai_tts_raises_on_http_error(tmp_path):
    tts = _tts()
    tts._session = _FakeSession(_FakeResponse(b"", 500))
    voice = tts.list_voices()[0]
    with pytest.raises(TTSError):
        tts.synthesize("hi", voice, tmp_path / "out.mp3")


def test_openai_tts_raises_on_missing_api_key():
    config = Config()
    with pytest.raises(TTSError):
        OpenAICompatibleTTS(config, "custom-tts")
