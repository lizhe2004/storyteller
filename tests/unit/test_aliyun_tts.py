import json
from pathlib import Path

import pytest

from storyteller.core.config import Config
from storyteller.core.exceptions import TTSError
from storyteller.core.models import VoiceConfig
from storyteller.providers.aliyun.tts import AliyunTTS, load_voice_catalog

_ENDPOINT = "https://dashscope.aliyuncs.com"
_PATH = "/api/v1/services/audio/tts/SpeechSynthesizer"
_AUDIO_URL = "http://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/x/out.wav?sig=abc"


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"", error_url=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = content
        self._error_url = error_url

    def json(self):
        return self._payload

    @property
    def text(self):
        return json.dumps(self._payload, ensure_ascii=False)

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            if self._error_url:
                # Mimics requests' real message shape, which embeds the
                # request URL: "404 Client Error: ... for url: <url>".
                raise requests.HTTPError(
                    "{} Client Error for url: {}".format(
                        self.status_code, self._error_url
                    )
                )
            raise requests.HTTPError("status {}".format(self.status_code))


class _FakeSession:
    def __init__(self, synth_response=None, download_response=None):
        self._synth = synth_response
        self._download = download_response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"method": "POST", "url": url, **kwargs})
        return self._synth

    def get(self, url, **kwargs):
        self.calls.append({"method": "GET", "url": url, **kwargs})
        return self._download


def _synth_ok(audio_url=_AUDIO_URL):
    return _FakeResponse(
        200,
        {
            "request_id": "req-1",
            "output": {
                "finish_reason": "stop",
                "audio": {"data": "", "url": audio_url, "id": "audio_1"},
            },
            "usage": {"characters": 3},
        },
    )


def _config(**overrides):
    config = Config()
    pc = {
        "api_key": "test-key",
        "endpoint": _ENDPOINT,
        "model": "qwen-audio-3.0-tts-flash",
    }
    pc.update(overrides)
    config.set("tts.provider_config.aliyun", pc)
    return config

def _voice(voice_id="longanhuan_v3.6", **kw):
    return VoiceConfig(provider="aliyun", voice_id=voice_id, **kw)


def _make_tts(synth_response=None, download_bytes=b"ID3fake-mp3"):
    tts = AliyunTTS(_config())
    tts._session = _FakeSession(
        synth_response or _synth_ok(),
        _FakeResponse(200, content=download_bytes),
    )
    return tts


def test_aliyun_tts_has_name_and_display():
    tts = AliyunTTS(_config())
    assert tts.name == "aliyun"
    assert tts.display_name


def test_aliyun_tts_lists_catalog_voices():
    voices = AliyunTTS(_config()).list_voices()
    ids = {v.voice_id for v in voices}
    assert len(voices) == len(load_voice_catalog())
    assert "longanhuan_v3.6" in ids
    assert all(v.provider == "aliyun" for v in voices)
    # gender/age/category needed by the semantic matcher come through.
    by_id = {v.voice_id: v for v in voices}
    assert by_id["longpaopao_v3.6"].gender == "female"
    assert by_id["longpaopao_v3.6"].age == "child"
    assert by_id["longpaopao_v3.6"].category == "儿童陪伴"


def test_synthesize_posts_then_downloads_audio_url(tmp_path):
    audio_bytes = b"ID3fake-mp3-data"
    tts = _make_tts(download_bytes=audio_bytes)

    out = tmp_path / "line1.mp3"
    result = tts.synthesize("你好世界", _voice(), out)

    assert result == out
    assert out.read_bytes() == audio_bytes

    post_call = tts._session.calls[0]
    assert post_call["method"] == "POST"
    assert post_call["url"] == _ENDPOINT + _PATH
    assert post_call["timeout"] == 120
    assert post_call["headers"]["Authorization"] == "Bearer test-key"
    assert post_call["headers"]["Content-Type"] == "application/json"

    body = post_call["json"]
    assert body["model"] == "qwen-audio-3.0-tts-flash"
    inp = body["input"]
    assert inp["text"] == "你好世界"
    assert inp["voice"] == "longanhuan_v3.6"
    assert inp["format"] == "mp3"
    assert inp["sample_rate"] == 24000

    # Second HTTP call downloads the 24h URL immediately.
    get_call = tts._session.calls[1]
    assert get_call["method"] == "GET"
    assert get_call["url"] == _AUDIO_URL
    assert get_call["timeout"] == 60


def test_model_comes_from_the_voices_catalog_record(tmp_path):
    tts = _make_tts()
    tts.synthesize("你好", _voice("longanlingxin"), tmp_path / "out.mp3")
    body = tts._session.calls[0]["json"]
    assert body["model"] == "qwen-audio-3.0-tts-plus"


def test_unknown_voice_falls_back_to_configured_model(tmp_path):
    tts = _make_tts()
    tts.synthesize(
        "你好",
        _voice("my-cloned-voice"),
        tmp_path / "out.mp3",
    )
    body = tts._session.calls[0]["json"]
    assert body["model"] == "qwen-audio-3.0-tts-flash"
    assert body["input"]["voice"] == "my-cloned-voice"


def test_unknown_voice_without_configured_model_raises():
    config = _config()
    config.set("tts.provider_config.aliyun.model", None)
    tts = AliyunTTS(config)
    tts._session = _FakeSession(_synth_ok(), _FakeResponse(200, content=b"x"))
    with pytest.raises(TTSError):
        tts.synthesize("你好", _voice("mystery"), Path("out.mp3"))


def test_speed_pitch_volume_map_to_input_params(tmp_path):
    tts = _make_tts()
    voice = _voice(speed=1.5, pitch=0.8, volume=1.5)
    tts.synthesize("快一点", voice, tmp_path / "out.mp3")
    inp = tts._session.calls[0]["json"]["input"]
    assert inp["rate"] == 1.5
    assert inp["pitch"] == 0.8
    # volume multiplier 1.5x -> aliyun 0..100 scale centered at 50 -> 75.
    assert inp["volume"] == 75


def test_volume_is_clamped_to_0_100(tmp_path):
    tts = _make_tts()
    tts.synthesize(
        "响", _voice(volume=3.0), tmp_path / "loud.mp3"
    )
    tts.synthesize(
        "轻", _voice(volume=0.0), tmp_path / "quiet.mp3"
    )
    # Each synthesis is a POST followed by the URL download (GET).
    post_calls = [c for c in tts._session.calls if c["method"] == "POST"]
    assert post_calls[0]["json"]["input"]["volume"] == 100
    assert post_calls[1]["json"]["input"]["volume"] == 0


def test_defaults_are_omitted_from_request(tmp_path):
    tts = _make_tts()
    tts.synthesize("你好", _voice(), tmp_path / "out.mp3")
    inp = tts._session.calls[0]["json"]["input"]
    assert "rate" not in inp
    assert "pitch" not in inp
    assert "volume" not in inp
    assert "instruction" not in inp


def test_directives_become_instruction_without_hash_prefix(tmp_path):
    tts = _make_tts()
    tts.synthesize(
        "能一起撑伞不？",
        _voice(),
        tmp_path / "out.mp3",
        directives=["#用害羞犹豫的语气说", "声音放轻"],
    )
    inp = tts._session.calls[0]["json"]["input"]
    assert inp["instruction"] == "用害羞犹豫的语气说，声音放轻"


def test_quoted_context_is_dropped(tmp_path):
    tts = _make_tts()
    tts.synthesize(
        "你好",
        _voice(),
        tmp_path / "out.mp3",
        directives=["开心地说"],
        context=["上一句旁白内容，阿里云无对应参数"],
    )
    inp = tts._session.calls[0]["json"]["input"]
    assert inp["instruction"] == "开心地说"
    assert "context" not in inp


def test_wav_output_uses_wav_24k(tmp_path):
    tts = _make_tts()
    tts.synthesize("你好", _voice(), tmp_path / "out.wav")
    inp = tts._session.calls[0]["json"]["input"]
    assert inp["format"] == "wav"
    assert inp["sample_rate"] == 24000


def test_ogg_output_maps_to_opus_48k(tmp_path):
    tts = _make_tts()
    tts.synthesize("你好", _voice(), tmp_path / "out.ogg")
    inp = tts._session.calls[0]["json"]["input"]
    assert inp["format"] == "opus"
    assert inp["sample_rate"] == 48000


def test_workspace_endpoint_is_composed_once(tmp_path):
    tts = AliyunTTS(
        _config(endpoint="https://ws123.cn-beijing.maas.aliyuncs.com/")
    )
    tts._session = _FakeSession(_synth_ok(), _FakeResponse(200, content=b"x"))
    tts.synthesize("你好", _voice(), tmp_path / "out.mp3")
    url = tts._session.calls[0]["url"]
    assert url == (
        "https://ws123.cn-beijing.maas.aliyuncs.com" + _PATH
    )


def test_endpoint_already_including_path_is_not_doubled(tmp_path):
    full = _ENDPOINT + _PATH
    tts = AliyunTTS(_config(endpoint=full))
    tts._session = _FakeSession(_synth_ok(), _FakeResponse(200, content=b"x"))
    tts.synthesize("你好", _voice(), tmp_path / "out.mp3")
    assert tts._session.calls[0]["url"] == full


def test_synthesize_surfaces_http_error_message(tmp_path):
    tts = AliyunTTS(_config())
    tts._session = _FakeSession(
        _FakeResponse(
            401,
            payload={
                "code": "InvalidApiKey",
                "message": "Invalid API-key provided",
                "request_id": "req-err",
            },
        ),
        _FakeResponse(200, content=b"x"),
    )
    with pytest.raises(TTSError, match="Invalid API-key provided"):
        tts.synthesize("你好", _voice(), tmp_path / "out.mp3")


def test_synthesize_logs_safe_full_request_on_api_error(tmp_path, caplog):
    tts = AliyunTTS(_config())
    tts._session = _FakeSession(
        _FakeResponse(
            402,
            {
                "code": "FreeQuotaExhausted",
                "message": "free quota exhausted",
                "request_id": "req-quota",
            },
        ),
        _FakeResponse(200, content=b"x"),
    )

    with caplog.at_level("ERROR", logger="storyteller.providers.aliyun.tts"):
        with pytest.raises(TTSError):
            tts.synthesize("你好 世界", _voice(), tmp_path / "out.mp3")

    message = "\n".join(record.getMessage() for record in caplog.records)
    assert "event=tts_request_failed" in message
    assert '"text":"你好 世界"' in message
    assert '"voice":"longanhuan_v3.6"' in message
    assert '"format":"mp3"' in message
    assert "model=qwen-audio-3.0-tts-flash" in message
    assert "response_code=FreeQuotaExhausted" in message
    assert "request_id=req-quota" in message
    assert "test-key" not in message


def test_synthesize_raises_when_audio_url_missing(tmp_path):
    tts = AliyunTTS(_config())
    tts._session = _FakeSession(
        _FakeResponse(
            200,
            {"request_id": "r", "output": {"finish_reason": "null", "audio": {}}},
        ),
        _FakeResponse(200, content=b"x"),
    )
    with pytest.raises(TTSError):
        tts.synthesize("你好", _voice(), tmp_path / "out.mp3")


def test_synthesize_raises_when_download_fails(tmp_path):
    tts = AliyunTTS(_config())
    tts._session = _FakeSession(_synth_ok(), _FakeResponse(403))
    with pytest.raises(TTSError):
        tts.synthesize("你好", _voice(), tmp_path / "out.mp3")


def test_download_failure_does_not_leak_signed_url(tmp_path):
    signed_url = "https://audio.example.com/x.mp3?sig=SECRETSIG123"
    tts = AliyunTTS(_config())
    tts._session = _FakeSession(
        _synth_ok(audio_url=signed_url),
        _FakeResponse(404, error_url=signed_url),
    )
    with pytest.raises(TTSError) as exc_info:
        tts.synthesize("你好", _voice(), tmp_path / "out.mp3")
    message = str(exc_info.value)
    assert "SECRETSIG123" not in message
    assert "audio.example.com" not in message


def test_constructor_raises_on_missing_key():
    with pytest.raises(TTSError):
        AliyunTTS(_config(api_key=None))
