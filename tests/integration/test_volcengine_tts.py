import base64
import json

import pytest

from storyteller.core.config import Config
from storyteller.core.exceptions import TTSError
from storyteller.core.models import VoiceConfig
from storyteller.providers.volcengine.tts import VolcengineTTS


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    @property
    def text(self):
        return json.dumps(self._payload, ensure_ascii=False)

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError("status {}".format(self.status_code))


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
        "tts.provider_config.volcengine",
        {
            "api_key": "test-key",
            "endpoint": "https://openspeech.example.com/api/v1/tts",
            "appid": "test-app",
            "cluster": "volcano_tts",
        },
    )
    return config


def test_volcengine_tts_has_name():
    tts = VolcengineTTS(_config())
    assert tts.name == "volcengine"


def test_volcengine_tts_lists_builtin_voices():
    tts = VolcengineTTS(_config())
    voices = tts.list_voices()
    assert len(voices) > 0
    assert all(v.provider == "volcengine" for v in voices)
    assert all(v.voice_id for v in voices)


def test_volcengine_tts_synthesize_writes_audio(tmp_path):
    audio_bytes = b"ID3fake-mp3-data"
    payload = {
        "code": 3000,
        "message": "success",
        "data": base64.b64encode(audio_bytes).decode(),
    }
    tts = VolcengineTTS(_config())
    tts._session = _FakeSession(_FakeResponse(200, payload))

    voice = tts.list_voices()[0]
    out = tmp_path / "line1.mp3"
    result = tts.synthesize("你好", voice, out)

    assert result == out
    assert out.read_bytes() == audio_bytes

    call = tts._session.calls[0]
    assert call["url"] == "https://openspeech.example.com/api/v1/tts"
    assert call["headers"]["X-Api-Key"] == "test-key"
    body = call["json"]
    assert body["request"]["text"] == "你好"
    assert body["audio"]["voice_type"] == voice.voice_id


def test_volcengine_tts_raises_on_api_error_code(tmp_path):
    payload = {"code": 3001, "message": "invalid params"}
    tts = VolcengineTTS(_config())
    tts._session = _FakeSession(_FakeResponse(200, payload))
    voice = tts.list_voices()[0]
    with pytest.raises(TTSError):
        tts.synthesize("你好", voice, tmp_path / "out.mp3")


def test_volcengine_tts_raises_on_missing_key():
    config = Config()
    with pytest.raises(TTSError):
        VolcengineTTS(config)


def test_volcengine_tts_passes_speed_config(tmp_path):
    payload = {
        "code": 3000,
        "data": base64.b64encode(b"x").decode(),
    }
    tts = VolcengineTTS(_config())
    tts._session = _FakeSession(_FakeResponse(200, payload))
    voice = VoiceConfig(
        provider="volcengine",
        voice_id="zh_test_voice",
        voice_type="female",
        speed=1.5,
    )
    tts.synthesize("快一点", voice, tmp_path / "out.mp3")
    body = tts._session.calls[0]["json"]
    assert body["audio"]["speed_ratio"] == 1.5
