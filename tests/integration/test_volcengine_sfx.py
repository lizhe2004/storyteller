import base64
import json

import pytest
import requests

from storyteller.core.config import Config
from storyteller.core.exceptions import TTSError
from storyteller.providers.volcengine.sfx import VolcengineSoundProvider

_ENDPOINT = "https://openspeech.example.com/api/v3/tts/create"


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = content

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError("status {}".format(self.status_code))


class _FakeSession:
    def __init__(self, response=None, get_response=None, get_error=None):
        self._response = response
        self._get_response = get_response
        self._get_error = get_error
        self.post_calls = []
        self.get_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append({"url": url, **kwargs})
        return self._response

    def get(self, url, **kwargs):
        self.get_calls.append({"url": url, **kwargs})
        if self._get_error is not None:
            raise self._get_error
        return self._get_response


def _config(**sound):
    config = Config()
    config.set(
        "sound.provider_config.volcengine",
        {
            "api_key": "sound-key",
            "endpoint": _ENDPOINT,
            "model": "seed-audio-1.0",
            **sound,
        },
    )
    return config


def test_name_and_model():
    provider = VolcengineSoundProvider(_config())
    assert provider.name == "volcengine"
    assert provider.model == "seed-audio-1.0"


def test_generate_writes_inline_base64_audio(tmp_path):
    audio_bytes = b"ID3fake-sound"
    payload = {
        "code": 0,
        "audio": base64.b64encode(audio_bytes).decode(),
        "duration": 2.5,
    }
    session = _FakeSession(_FakeResponse(200, payload))
    provider = VolcengineSoundProvider(_config(), session=session)

    out = tmp_path / "wind.mp3"
    path, duration = provider.generate("微风声", out)

    assert path == out
    assert out.read_bytes() == audio_bytes
    assert duration == 2.5

    call = session.post_calls[0]
    assert call["url"] == _ENDPOINT
    assert call["timeout"] == 300
    assert call["headers"]["X-Api-Key"] == "sound-key"
    assert call["headers"]["X-Api-Request-Id"]
    body = call["json"]
    assert body["model"] == "seed-audio-1.0"
    assert body["text_prompt"] == "微风声"
    assert body["audio_config"]["format"] == "mp3"
    assert body["audio_config"]["sample_rate"] == 44100


def test_generate_code_absent_is_treated_as_success(tmp_path):
    audio_bytes = b"sound"
    payload = {"audio": base64.b64encode(audio_bytes).decode()}
    session = _FakeSession(_FakeResponse(200, payload))
    provider = VolcengineSoundProvider(_config(), session=session)
    out = tmp_path / "s.mp3"
    path, _ = provider.generate("雨声", out)
    assert out.read_bytes() == audio_bytes


def test_generate_raises_on_error_code(tmp_path):
    session = _FakeSession(
        _FakeResponse(200, {"code": 4001, "message": "bad prompt"})
    )
    provider = VolcengineSoundProvider(_config(), session=session)
    with pytest.raises(TTSError) as exc:
        provider.generate("x", tmp_path / "s.mp3")
    assert "4001" in str(exc.value)
    assert "bad prompt" in str(exc.value)


def test_generate_falls_back_to_url_download(tmp_path):
    payload = {"code": 0, "url": "https://cdn.example.com/s.mp3"}
    get_response = _FakeResponse(200, content=b"downloaded-bytes")
    session = _FakeSession(_FakeResponse(200, payload), get_response)
    provider = VolcengineSoundProvider(_config(), session=session)

    out = tmp_path / "s.mp3"
    path, _ = provider.generate("笛声", out)

    assert out.read_bytes() == b"downloaded-bytes"
    assert session.get_calls[0]["url"] == "https://cdn.example.com/s.mp3"


def test_generate_raises_when_no_audio_or_url(tmp_path):
    session = _FakeSession(_FakeResponse(200, {"code": 0}))
    provider = VolcengineSoundProvider(_config(), session=session)
    with pytest.raises(TTSError):
        provider.generate("x", tmp_path / "s.mp3")


def test_download_network_error_does_not_leak_signed_url(tmp_path):
    signed_url = "https://cdn.example.com/signature=SECRETTOKEN/s.mp3?Expires=123"
    payload = {"code": 0, "url": signed_url}
    get_error = requests.ConnectionError("bad url: " + signed_url)
    session = _FakeSession(
        _FakeResponse(200, payload), get_error=get_error
    )
    provider = VolcengineSoundProvider(_config(), session=session)

    with pytest.raises(TTSError) as exc:
        provider.generate("x", tmp_path / "s.mp3")

    message = str(exc.value)
    assert "network error" in message
    assert "ConnectionError" in message
    assert signed_url not in message
    assert "SECRETTOKEN" not in message


def test_download_http_error_does_not_leak_signed_url(tmp_path):
    signed_url = "https://cdn.example.com/signature=SECRETTOKEN/s.mp3?Expires=123"
    payload = {"code": 0, "url": signed_url}
    get_response = _FakeResponse(500, {})
    session = _FakeSession(
        _FakeResponse(200, payload), get_response=get_response
    )
    provider = VolcengineSoundProvider(_config(), session=session)

    with pytest.raises(TTSError) as exc:
        provider.generate("x", tmp_path / "s.mp3")

    message = str(exc.value)
    assert "HTTP 500" in message
    assert signed_url not in message
    assert "SECRETTOKEN" not in message


def test_generate_raises_on_http_error(tmp_path):
    session = _FakeSession(_FakeResponse(500, {}))
    provider = VolcengineSoundProvider(_config(), session=session)
    with pytest.raises(TTSError):
        provider.generate("x", tmp_path / "s.mp3")


def test_wav_uses_24k_and_ogg_uses_48k(tmp_path):
    session = _FakeSession(
        _FakeResponse(
            200, {"code": 0, "audio": base64.b64encode(b"x").decode()}
        )
    )
    provider = VolcengineSoundProvider(_config(), session=session)
    provider.generate("x", tmp_path / "a.wav", audio_format="wav")
    provider.generate("x", tmp_path / "a.ogg", audio_format="ogg")
    assert session.post_calls[0]["json"]["audio_config"]["sample_rate"] == 24000
    assert session.post_calls[1]["json"]["audio_config"]["format"] == "ogg_opus"
    assert session.post_calls[1]["json"]["audio_config"]["sample_rate"] == 48000


def test_missing_key_raises():
    config = Config()
    with pytest.raises(TTSError):
        VolcengineSoundProvider(config)


def test_tts_key_is_not_used_as_fallback():
    config = Config()
    config.set(
        "tts.provider_config.volcengine",
        {"api_key": "tts-key", "endpoint": _ENDPOINT},
    )
    with pytest.raises(TTSError) as exc:
        VolcengineSoundProvider(config)
    message = str(exc.value)
    assert "STORYTELLER_SOUND_VOLCENGINE_API_KEY" in message
    # The unrelated TTS key must not appear in the error either.
    assert "tts-key" not in message
