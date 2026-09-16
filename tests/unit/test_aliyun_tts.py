import json
import struct
import threading
import traceback
from pathlib import Path

import pytest

from storyteller.core.config import Config
from storyteller.core.exceptions import TTSError
from storyteller.core.models import VoiceConfig
from storyteller.providers.aliyun import tts as aliyun_tts_module
from storyteller.providers.aliyun.tts import (
    AliyunTTS,
    load_voice_catalog,
    load_voice_index,
)

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


class _FakeRealtimeSynthesizer:
    def __init__(self, callback, audio_chunks=(), error=None):
        self.callback = callback
        self.audio_chunks = list(audio_chunks)
        self.error = error
        self.calls = []
        self.completed = False
        self.cancelled = False

    def streaming_call(self, text):
        self.calls.append(("streaming_call", text))
        if self.error:
            self.callback.on_error(self.error)

    def streaming_complete(self):
        self.calls.append(("streaming_complete",))
        for chunk in self.audio_chunks:
            self.callback.on_data(chunk)
        self.completed = True
        self.callback.on_complete()

    def streaming_cancel(self):
        self.cancelled = True


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
        "workspace_id": "test-workspace",
    }
    pc.update(overrides)
    config.set("tts.provider_config.aliyun", pc)
    return config

def _voice(voice_id="longanhuan_v3.6", **kw):
    return VoiceConfig(provider="aliyun", voice_id=voice_id, **kw)


def _make_tts(synth_response=None, download_bytes=b"ID3fake-mp3"):
    tts = AliyunTTS(_config(workspace_id=""))
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


def test_enabled_models_allowlist_filters_list_voices():
    # flash has no free quota left; set MODELS to plus to restrict voice
    # matching to that tier only. Exact match on the catalog model id.
    config = _config(models="qwen-audio-3.0-tts-plus")
    voices = AliyunTTS(config).list_voices()
    ids = {v.voice_id for v in voices}
    assert "longanfengyue" not in ids  # flash voice
    assert "longanlingxin" in ids     # plus voice
    assert all(
        load_voice_index()[v.voice_id]["model"] == "qwen-audio-3.0-tts-plus"
        for v in voices
    )


def test_enabled_models_supports_multiple_and_whitespace():
    # Both plus and flash explicitly listed -> both visible.
    config = _config(models=" qwen-audio-3.0-tts-plus , qwen-audio-3.0-tts-flash ")
    voices = AliyunTTS(config).list_voices()
    assert len(voices) == len(load_voice_catalog())


def test_enabled_models_unset_exposes_all_catalog_voices():
    # Default behaviour (no MODELS env) is backwards-compatible: every
    # catalog voice is available.
    config = _config()
    assert "models" not in config.get("tts.provider_config.aliyun")
    voices = AliyunTTS(config).list_voices()
    assert len(voices) == len(load_voice_catalog())


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


def test_websocket_session_builds_workspace_url_forwards_text_and_resamples_callback_pcm():
    """Bypassing the callback bridge or 22.05kHz conversion breaks the stream contract."""
    tts = AliyunTTS(_config(workspace_id="workspace-123"))
    created = {}
    input_pcm = struct.pack("<147h", *range(147))

    def factory(**kwargs):
        created.update(kwargs)
        synthesizer = _FakeRealtimeSynthesizer(kwargs["callback"], [input_pcm])
        created["synthesizer"] = synthesizer
        return synthesizer

    tts._realtime_synthesizer_factory = factory
    session = tts.open_stream(_voice())
    session.send_text("第一段")
    session.send_text("第二段")
    session.finish()

    synthesizer = created["synthesizer"]
    assert synthesizer.calls == [
        ("streaming_call", "第一段"),
        ("streaming_call", "第二段"),
        ("streaming_complete",),
    ]
    assert synthesizer.completed is True
    assert created["format"] == "PCM_22050HZ_MONO_16BIT"
    assert created["websocket_api_url"] == (
        "wss://workspace-123.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference"
    )
    output_pcm = b"".join(chunk.data for chunk in session.iter_audio())
    assert len(output_pcm) == 320
    assert output_pcm != input_pcm


def test_websocket_session_translates_callback_errors_and_can_cancel():
    """Leaking a DashScope callback error would expose an SDK-specific failure."""
    tts = AliyunTTS(_config())
    created = {}

    def factory(**kwargs):
        synthesizer = _FakeRealtimeSynthesizer(
            kwargs["callback"], error="service unavailable"
        )
        created["synthesizer"] = synthesizer
        return synthesizer

    tts._realtime_synthesizer_factory = factory
    session = tts.open_stream(_voice())
    with pytest.raises(TTSError, match="service unavailable"):
        session.send_text("会失败")

    session.cancel()
    assert created["synthesizer"].cancelled is True


def test_realtime_session_requires_realtime_configuration_before_constructing_sdk():
    """An ordinary HTTP-only Aliyun provider must never construct the SDK client."""
    tts = AliyunTTS(_config(workspace_id=""))

    def unexpected_factory(**kwargs):
        raise AssertionError("realtime synthesizer factory must not be called")

    tts._realtime_synthesizer_factory = unexpected_factory
    with pytest.raises(TTSError, match="not configured"):
        tts.open_stream(_voice())


def test_realtime_session_finish_waits_for_callback_completion():
    """Returning from finish before DashScope completes truncates trailing audio."""
    tts = AliyunTTS(_config())
    created = {}

    class DelayedCompletingSynthesizer:
        def __init__(self, callback):
            self.callback = callback
            self.complete_called = threading.Event()

        def streaming_call(self, text):
            pass

        def streaming_complete(self):
            self.complete_called.set()

    def factory(**kwargs):
        synthesizer = DelayedCompletingSynthesizer(kwargs["callback"])
        created["synthesizer"] = synthesizer
        return synthesizer

    tts._realtime_synthesizer_factory = factory
    session = tts.open_stream(_voice())
    finisher = threading.Thread(target=session.finish)
    finisher.start()

    synthesizer = created["synthesizer"]
    assert synthesizer.complete_called.wait(timeout=1)
    assert finisher.is_alive()
    synthesizer.callback.on_complete()
    finisher.join(timeout=1)
    assert not finisher.is_alive()


def test_realtime_session_finish_times_out_without_completion(monkeypatch):
    """A DashScope SDK that never calls on_complete must not hang the job."""
    tts = AliyunTTS(_config())

    class NeverCompletingSynthesizer:
        def __init__(self, callback):
            self.callback = callback

        def streaming_call(self, text):
            pass

        def streaming_complete(self):
            return  # terminal callback is never delivered

    tts._realtime_synthesizer_factory = lambda **kwargs: NeverCompletingSynthesizer(
        kwargs["callback"]
    )
    session = tts.open_stream(_voice())
    monkeypatch.setattr(type(session), "_FINISH_TIMEOUT_SECONDS", 0.05)
    session.send_text("第一句")
    with pytest.raises(TTSError, match="timed out"):
        session.finish()
    with pytest.raises(TTSError):  # the audio iterator is unblocked, not hung
        list(session.iter_audio())


def test_realtime_session_cancel_releases_callback_blocked_by_bounded_audio_queue():
    """An unbounded or uncleared callback queue would leak memory or deadlock finish."""
    tts = AliyunTTS(_config())
    created = {}
    input_pcm = struct.pack("<3h", 1, 2, 3)

    class BufferFillingSynthesizer(_FakeRealtimeSynthesizer):
        def __init__(self, callback):
            super().__init__(callback)
            self.second_callback_started = threading.Event()

        def streaming_complete(self):
            self.callback.on_data(input_pcm)
            self.second_callback_started.set()
            self.callback.on_data(input_pcm)
            self.callback.on_complete()

    def factory(**kwargs):
        synthesizer = BufferFillingSynthesizer(kwargs["callback"])
        created["synthesizer"] = synthesizer
        return synthesizer

    tts._realtime_synthesizer_factory = factory
    session = tts.open_stream(_voice())
    session._QUEUE_SIZE = 1
    finisher = threading.Thread(target=session.finish)
    finisher.start()

    synthesizer = created["synthesizer"]
    assert synthesizer.second_callback_started.wait(timeout=1)
    with session._changed:
        assert len(session._audio) == 1
    session.cancel()
    finisher.join(timeout=1)

    assert not finisher.is_alive()
    assert list(session.iter_audio()) == []


def test_realtime_session_finishes_before_draining_more_than_bounded_audio_chunks():
    """A full callback buffer must not make finish-before-drain deadlock."""
    tts = AliyunTTS(_config())
    created = {}
    input_pcm = struct.pack("<3h", 1, 2, 3)

    class LongAudioSynthesizer(_FakeRealtimeSynthesizer):
        def streaming_complete(self):
            self.calls.append(("streaming_complete",))
            for _ in range(4):
                self.callback.on_data(input_pcm)
            self.callback.on_complete()

    def factory(**kwargs):
        synthesizer = LongAudioSynthesizer(kwargs["callback"])
        created["synthesizer"] = synthesizer
        return synthesizer

    tts._realtime_synthesizer_factory = factory
    session = tts.open_stream(_voice())
    session._QUEUE_SIZE = 1
    finished = threading.Event()
    finisher = threading.Thread(
        target=lambda: (session.finish(), finished.set()), daemon=True
    )
    finisher.start()

    try:
        assert finished.wait(timeout=1)
        with session._changed:
            assert len(session._audio) == session._QUEUE_SIZE
            assert session._spill is not None
        audio = b"".join(chunk.data for chunk in session.iter_audio())
    finally:
        if not finished.is_set():
            session.cancel()
        finisher.join(timeout=1)

    assert len(audio) > 0
    assert created["synthesizer"].calls == [("streaming_complete",)]


def test_realtime_session_failure_drains_overflow_spill_before_iterator_cleanup(
    monkeypatch,
):
    """Closing spill on failure must not discard already accepted overflow PCM."""
    tts = AliyunTTS(_config())
    created = {}
    input_pcm = struct.pack("<3h", 1, 2, 3)

    real_temporary_file = aliyun_tts_module.tempfile.TemporaryFile

    def tracked_temporary_file(*args, **kwargs):
        spill = real_temporary_file(*args, **kwargs)
        created["spill"] = spill
        return spill

    monkeypatch.setattr(
        aliyun_tts_module.tempfile,
        "TemporaryFile",
        tracked_temporary_file,
    )

    class FailingLongAudioSynthesizer:
        def __init__(self, callback):
            self.callback = callback

        def streaming_call(self, text):
            pass

        def streaming_complete(self):
            self.callback.on_data(input_pcm)
            self.callback.on_data(input_pcm)
            self.callback.on_error("provider failed")

    def factory(**kwargs):
        return FailingLongAudioSynthesizer(kwargs["callback"])

    tts._realtime_synthesizer_factory = factory
    session = tts.open_stream(_voice())
    session._QUEUE_SIZE = 1

    with pytest.raises(TTSError, match="provider failed"):
        session.finish()

    drained = []
    with pytest.raises(TTSError, match="provider failed"):
        for chunk in session.iter_audio():
            drained.append(chunk.data)

    assert len(drained) == 2
    assert all(drained)
    assert created["spill"].closed
    assert session._spill is None


def test_realtime_session_redacts_callback_credentials_and_signed_urls():
    """SDK diagnostics must not expose API credentials through pipeline errors."""
    tts = AliyunTTS(_config())

    def factory(**kwargs):
        return _FakeRealtimeSynthesizer(
            kwargs["callback"],
            error="api_key=test-key https://audio.example.com/x.pcm?sig=secret",
        )

    tts._realtime_synthesizer_factory = factory
    session = tts.open_stream(_voice())
    with pytest.raises(TTSError) as exc_info:
        session.send_text("不会泄露")

    message = str(exc_info.value)
    assert "test-key" not in message
    assert "sig=secret" not in message
    assert "[redacted]" in message


def test_realtime_session_redacts_websocket_signed_urls_from_callback_errors():
    """Changing URL schemes must not bypass realtime diagnostics redaction."""
    tts = AliyunTTS(_config())

    def factory(**kwargs):
        return _FakeRealtimeSynthesizer(
            kwargs["callback"],
            error=(
                "wss://audio.example.com/pcm?signature=WSS_SECRET "
                "ws://fallback.example.com/pcm?token=WS_SECRET"
            ),
        )

    tts._realtime_synthesizer_factory = factory
    session = tts.open_stream(_voice())
    with pytest.raises(TTSError) as exc_info:
        session.send_text("不会泄露")

    message = str(exc_info.value)
    assert "WSS_SECRET" not in message
    assert "WS_SECRET" not in message
    assert "audio.example.com" not in message
    assert "fallback.example.com" not in message
    assert message.count("[signed-url-redacted]") == 2


def test_realtime_provider_exception_hides_sdk_context_from_traceback():
    """A sanitized connection failure must not print the SDK's secret message."""
    tts = AliyunTTS(_config())

    def factory(**kwargs):
        raise RuntimeError(
            "api_key=test-key wss://audio.example.com/pcm?signature=SECRET"
        )

    tts._realtime_synthesizer_factory = factory
    with pytest.raises(TTSError) as exc_info:
        tts.open_stream(_voice())

    rendered = "".join(
        traceback.format_exception(
            exc_info.type, exc_info.value, exc_info.tb
        )
    )
    assert "test-key" not in rendered
    assert "SECRET" not in rendered
    assert "audio.example.com" not in rendered
    assert exc_info.value.__suppress_context__ is True


def test_realtime_session_rejects_send_that_started_after_cancellation():
    """A send that loses the cancel race must not reach the DashScope SDK."""
    tts = AliyunTTS(_config())
    submitted = []
    call_accessed = threading.Event()
    release_call_access = threading.Event()

    class CancelRaceSynthesizer:
        @property
        def streaming_call(self):
            call_accessed.set()
            assert release_call_access.wait(timeout=1)
            return self._submit

        def _submit(self, text):
            submitted.append(text)

        def streaming_cancel(self):
            pass

    def factory(**kwargs):
        return CancelRaceSynthesizer()

    tts._realtime_synthesizer_factory = factory
    session = tts.open_stream(_voice())
    sender_error = []

    def send_text():
        try:
            session.send_text("late text")
        except Exception as exc:
            sender_error.append(exc)

    sender = threading.Thread(target=send_text)
    sender.start()
    assert call_accessed.wait(timeout=1)
    session.cancel()
    release_call_access.set()
    sender.join(timeout=1)

    assert len(sender_error) == 1
    assert isinstance(sender_error[0], TTSError)
    assert submitted == []
