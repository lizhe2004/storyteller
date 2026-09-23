import base64
import json
import struct
import threading

import pytest

from storyteller.core.config import Config
from storyteller.core.exceptions import TTSError
from storyteller.core.models import VoiceConfig
from storyteller.providers.volcengine.tts import VolcengineTTS

_ENDPOINT = "https://openspeech.example.com/api/v3/tts/unidirectional"


class _FakeResponse:
    def __init__(self, status_code=200, lines=None, payload=None):
        self.status_code = status_code
        # NDJSON lines returned by the streaming endpoint.
        self._lines = lines if lines is not None else []
        # Non-streaming JSON body, used for HTTP errors.
        self._payload = payload if payload is not None else {}

    def iter_lines(self, decode_unicode=True):
        return iter(list(self._lines))

    def json(self):
        return self._payload

    @property
    def text(self):
        return json.dumps(self._payload, ensure_ascii=False)

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError("status {}".format(self.status_code))

    def close(self):
        pass


class _FakeSession:
    def __init__(self, response=None):
        self._response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self._response


class _FakeRealtimeTransport:
    """In-memory Volcengine socket which only knows the binary wire boundary."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.sent = []
        self.closed = False

    def send(self, frame):
        self.sent.append(frame)

    def recv(self):
        return self._responses.pop(0)

    def close(self):
        self.closed = True


class _GatedTaskRequestTransport(_FakeRealtimeTransport):
    """Fake transport that pauses a TaskRequest before it is recorded."""

    def __init__(self, responses):
        super().__init__(responses)
        self.task_request_started = threading.Event()
        self.release_task_request = threading.Event()
        self.cancel_sent = threading.Event()

    def send(self, frame):
        event = _volc_event(frame)
        if event == 200:
            self.task_request_started.set()
            assert self.release_task_request.wait(timeout=1)
        super().send(frame)
        if event == 101:
            self.cancel_sent.set()


class _GatedAudioTransport(_FakeRealtimeTransport):
    """Fake transport that pauses the reader after receiving audio."""

    def __init__(self, responses):
        super().__init__(responses)
        self.audio_received = threading.Event()
        self.release_audio = threading.Event()

    def recv(self):
        frame = super().recv()
        if _volc_event(frame) == 352:
            self.audio_received.set()
            assert self.release_audio.wait(timeout=1)
        return frame


def _volc_response(event, payload=b"{}", session_id=b"session-1", *, audio=False):
    """Build a documented Volcengine v3 server frame for the fake socket."""
    message_type = 0xB4 if audio else 0x94
    return b"\x11" + bytes([message_type]) + b"\x10\x00" + struct.pack(
        ">I", event
    ) + struct.pack(">I", len(session_id)) + session_id + struct.pack(
        ">I", len(payload)
    ) + payload


def _volc_error(code, message):
    payload = json.dumps({"message": message}).encode("utf-8")
    return b"\x11\xf0\x10\x00" + struct.pack(">I", code) + struct.pack(
        ">I", len(payload)
    ) + payload


def _volc_event(frame):
    return struct.unpack(">I", frame[4:8])[0]


def _volc_payload(frame):
    offset = 8
    session_id_size = struct.unpack(">I", frame[offset:offset + 4])[0]
    offset += 4 + session_id_size
    payload_size = struct.unpack(">I", frame[offset:offset + 4])[0]
    return json.loads(frame[offset + 4:offset + 4 + payload_size])


def _stream_lines(audio_bytes, code=0):
    return [
        json.dumps(
            {"code": code, "data": base64.b64encode(audio_bytes).decode()}
        ),
        json.dumps({"code": 20000000, "data": None}),
    ]


def _config():
    config = Config()
    config.set(
        "tts.provider_config.volcengine",
        {
            "api_key": "test-key",
            "resource_id": "seed-tts-2.0",
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
    assert all(v.voice_id for v in voices)
    assert all(v.provider == "volcengine" for v in voices)
    by_id = {voice.voice_id: voice for voice in voices}
    assert by_id["zh_male_m191_uranus_bigtts"].model == "seed-tts-2.0"
    assert by_id["ICL_uranus_zh_male_wennuanshaonian_tob"].age == [
        "child", "teen"
    ]
    assert by_id["zh_male_m191_uranus_bigtts"].age == ["young_adult"]


def test_volcengine_tts_synthesize_writes_audio(tmp_path):
    audio_bytes = b"ID3fake-mp3-data"
    tts = VolcengineTTS(_config())
    tts._session = _FakeSession(
        _FakeResponse(200, _stream_lines(audio_bytes))
    )

    voice = tts.list_voices()[0]
    out = tmp_path / "line1.mp3"
    result = tts.synthesize("你好", voice, out)

    assert result == out
    assert out.read_bytes() == audio_bytes

    call = tts._session.calls[0]
    assert call["url"] == "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    assert call["stream"] is True
    assert call["headers"]["X-Api-Key"] == "test-key"
    assert call["headers"]["X-Api-Resource-Id"] == "seed-tts-2.0"
    assert call["headers"]["X-Api-Request-Id"]
    params = call["json"]["req_params"]
    assert params["text"] == "你好"
    assert params["speaker"] == voice.voice_id
    assert params["audio_params"]["format"] == "mp3"
    assert params["audio_params"]["sample_rate"] == 24000
    additions = json.loads(params["additions"])
    assert additions["disable_markdown_filter"] is True
    assert additions["disable_emoji_filter"] is True


def test_volcengine_tts_assembles_multiple_chunks(tmp_path):
    chunks = [b"ID3", b"fake", b"-mp3"]
    lines = [
        json.dumps({"code": 0, "data": base64.b64encode(c).decode()})
        for c in chunks
    ]
    lines.append(json.dumps({"code": 20000000}))
    tts = VolcengineTTS(_config())
    tts._session = _FakeSession(_FakeResponse(200, lines))

    out = tmp_path / "out.mp3"
    tts.synthesize("你好", tts.list_voices()[0], out)
    assert out.read_bytes() == b"ID3fake-mp3"


def test_volcengine_tts_raises_on_stream_error_code(tmp_path):
    lines = [
        json.dumps(
            {"code": 55000000, "message": "resource ID is mismatched"}
        )
    ]
    tts = VolcengineTTS(_config())
    tts._session = _FakeSession(_FakeResponse(200, lines))
    voice = tts.list_voices()[0]
    with pytest.raises(TTSError):
        tts.synthesize("你好", voice, tmp_path / "out.mp3")


def test_volcengine_tts_raises_on_http_error(tmp_path):
    tts = VolcengineTTS(_config())
    tts._session = _FakeSession(
        _FakeResponse(401, payload={"header": {"status": 401}})
    )
    voice = tts.list_voices()[0]
    with pytest.raises(TTSError):
        tts.synthesize("你好", voice, tmp_path / "out.mp3")


def test_volcengine_tts_raises_on_empty_audio(tmp_path):
    lines = [json.dumps({"code": 20000000, "data": None})]
    tts = VolcengineTTS(_config())
    tts._session = _FakeSession(_FakeResponse(200, lines))
    voice = tts.list_voices()[0]
    with pytest.raises(TTSError):
        tts.synthesize("你好", voice, tmp_path / "out.mp3")


def test_volcengine_tts_raises_on_missing_key():
    config = Config()
    with pytest.raises(TTSError):
        VolcengineTTS(config)


def test_volcengine_tts_maps_speed_pitch_volume(tmp_path):
    tts = VolcengineTTS(_config())
    tts._session = _FakeSession(_FakeResponse(200, _stream_lines(b"x")))
    voice = VoiceConfig(
        provider="volcengine",
        voice_id="zh_female_vv_uranus_bigtts",
        gender="female",
        speed=1.5,
        pitch=1.5,
        volume=1.5,
    )
    tts.synthesize("快一点", voice, tmp_path / "out.mp3")
    req = tts._session.calls[0]["json"]["req_params"]
    assert req["audio_params"]["speech_rate"] == 50
    assert req["audio_params"]["loudness_rate"] == 50
    # pitch 1.5x frequency ~ +7 semitones, sent via post_process.
    assert req["post_process"]["pitch"] == 7


def test_volcengine_tts_omits_pitch_at_default(tmp_path):
    tts = VolcengineTTS(_config())
    tts._session = _FakeSession(_FakeResponse(200, _stream_lines(b"x")))
    voice = VoiceConfig(
        provider="volcengine",
        voice_id="zh_female_vv_uranus_bigtts",
        gender="female",
    )
    tts.synthesize("你好", voice, tmp_path / "out.mp3")
    req = tts._session.calls[0]["json"]["req_params"]
    assert "post_process" not in req


def test_volcengine_tts_ogg_uses_48k(tmp_path):
    tts = VolcengineTTS(_config())
    tts._session = _FakeSession(_FakeResponse(200, _stream_lines(b"x")))
    voice = VoiceConfig(
        provider="volcengine",
        voice_id="zh_female_vv_uranus_bigtts",
        gender="female",
    )
    tts.synthesize("你好", voice, tmp_path / "out.ogg")
    audio_params = tts._session.calls[0]["json"]["req_params"]["audio_params"]
    assert audio_params["format"] == "ogg_opus"
    assert audio_params["sample_rate"] == 48000


def test_volcengine_tts_passes_directives_and_context(tmp_path):
    tts = VolcengineTTS(_config())
    tts._session = _FakeSession(_FakeResponse(200, _stream_lines(b"x")))
    voice = VoiceConfig(
        provider="volcengine",
        voice_id="zh_female_vv_uranus_bigtts",
        gender="female",
    )
    tts.synthesize(
        "能一起撑伞不？",
        voice,
        tmp_path / "out.mp3",
        directives=["用害羞犹豫的语气说"],
        context=["外面突然下起了大雨，两人在屋檐下躲雨"],
    )
    additions = json.loads(
        tts._session.calls[0]["json"]["req_params"]["additions"]
    )
    assert additions["context_texts"] == [
        "#用害羞犹豫的语气说",
        "外面突然下起了大雨，两人在屋檐下躲雨",
    ]


def test_volcengine_tts_omits_context_texts_when_empty(tmp_path):
    tts = VolcengineTTS(_config())
    tts._session = _FakeSession(_FakeResponse(200, _stream_lines(b"x")))
    voice = VoiceConfig(
        provider="volcengine",
        voice_id="zh_female_vv_uranus_bigtts",
        gender="female",
    )
    tts.synthesize("你好", voice, tmp_path / "out.mp3")
    additions = json.loads(
        tts._session.calls[0]["json"]["req_params"]["additions"]
    )
    assert "context_texts" not in additions


def test_volcengine_tts_uses_catalog_resource_id(tmp_path):
    from storyteller.providers.volcengine.tts import load_voice_catalog

    record = load_voice_catalog()[0]
    tts = VolcengineTTS(_config())
    tts._session = _FakeSession(_FakeResponse(200, _stream_lines(b"x")))
    voice = VoiceConfig(
        provider="volcengine",
        voice_id=record["voice_id"],
        gender=record["gender"],
    )
    tts.synthesize("你好", voice, tmp_path / "out.mp3")
    assert (
        tts._session.calls[0]["headers"]["X-Api-Resource-Id"]
        == record["resource_id"] == "seed-tts-2.0"
    )


def test_realtime_session_sends_start_task_finish_and_yields_pcm_audio():
    """Dropping or reordering a session command must break the realtime protocol."""
    transport = _FakeRealtimeTransport(
        [
            _volc_response(50, session_id=b"connection-1"),
            _volc_response(150),
            _volc_response(352, b"\x01\x00\x02\x00", audio=True),
            _volc_response(152),
        ]
    )
    tts = VolcengineTTS(_config())
    tts._realtime_transport_factory = lambda endpoint, headers: transport

    session = tts.open_stream(tts.list_voices()[0])
    session.send_text("第一句")
    session.send_text("第二句")
    session.finish()

    assert [_volc_event(frame) for frame in transport.sent] == [1, 100, 200, 200, 102]
    start = _volc_payload(transport.sent[1])
    assert start["req_params"]["speaker"] == tts.list_voices()[0].voice_id
    assert start["req_params"]["audio_params"] == {
        "format": "pcm",
        "sample_rate": 24000,
        "speech_rate": 0,
        "loudness_rate": 0,
    }
    assert [_volc_payload(frame)["req_params"]["text"] for frame in transport.sent[2:4]] == [
        "第一句",
        "第二句",
    ]
    assert [chunk.data for chunk in session.iter_audio()] == [b"\x01\x00\x02\x00"]


class _IdleThenReplayTransport(_FakeRealtimeTransport):
    """Raises N read timeouts (quiet keepalive window) then serves queued frames."""

    def __init__(self, responses, idle_reads):
        super().__init__(responses)
        self._idle_remaining = idle_reads

    def recv(self):
        if self._idle_remaining:
            self._idle_remaining -= 1
            raise _named_timeout()
        return super().recv()


def _named_timeout():
    # The provider matches websocket-client's exception purely by class name.
    return type("WebSocketTimeoutException", (Exception,), {})()


class _IdleAfterHandshakeTransport(_FakeRealtimeTransport):
    """Completes the handshake then never delivers a terminal SESSION_FINISHED."""

    def __init__(self):
        super().__init__([
            _volc_response(50, session_id=b"connection-1"),
            _volc_response(150),
        ])

    def recv(self):
        if self._responses:
            return self._responses.pop(0)
        raise _named_timeout()


def test_realtime_session_survives_idle_read_timeouts_before_audio():
    """A quiet keepalive window during the long opening must not abort the session."""
    transport = _IdleThenReplayTransport(
        [
            _volc_response(50, session_id=b"connection-1"),
            _volc_response(150),
            _volc_response(352, b"\x05\x00", audio=True),
            _volc_response(152),
        ],
        0,
    )
    tts = VolcengineTTS(_config())
    tts._realtime_transport_factory = lambda endpoint, headers: transport
    session = tts.open_stream(tts.list_voices()[0])  # handshake pops 50/150
    transport._idle_remaining = 3  # arm quiet reads during the streaming window
    session.send_text("开场很长，剧本还在生成")
    session.finish()
    assert [chunk.data for chunk in session.iter_audio()] == [b"\x05\x00"]


def test_realtime_finish_times_out_when_terminal_frame_never_arrives(monkeypatch):
    from storyteller.providers.volcengine.tts import VolcengineStreamingTTSSession

    transport = _IdleAfterHandshakeTransport()
    tts = VolcengineTTS(_config())
    tts._realtime_transport_factory = lambda endpoint, headers: transport
    monkeypatch.setattr(VolcengineStreamingTTSSession, "_FINISH_TIMEOUT_SECONDS", 0.05)
    session = tts.open_stream(tts.list_voices()[0])
    session.send_text("服务器不再回包")
    with pytest.raises(TTSError, match="timed out"):
        session.finish()
    assert transport.closed is True


def test_realtime_session_surfaces_server_errors_and_cancel_closes_socket():
    """Treating a server error as normal completion would hide provider failures."""
    transport = _FakeRealtimeTransport(
        [
            _volc_response(50, session_id=b"connection-1"),
            _volc_response(150),
            _volc_error(55000000, "upstream unavailable"),
        ]
    )
    tts = VolcengineTTS(_config())
    tts._realtime_transport_factory = lambda endpoint, headers: transport
    session = tts.open_stream(tts.list_voices()[0])

    session.send_text("会失败")
    with pytest.raises(TTSError, match="upstream unavailable"):
        session.finish()

    session.cancel()
    assert transport.closed is True


def test_realtime_session_uses_injected_bidirectional_transport_and_closes():
    """A completed one-shot session must not retain an authenticated socket."""
    transport = _FakeRealtimeTransport(
        [
            _volc_response(50, session_id=b"connection-1"),
            _volc_response(150),
            _volc_response(152),
        ]
    )
    received = {}
    tts = VolcengineTTS(_config())

    def factory(endpoint, headers):
        received["endpoint"] = endpoint
        received["headers"] = headers
        return transport

    tts._realtime_transport_factory = factory
    session = tts.open_stream(tts.list_voices()[0])
    session.finish()

    assert received["endpoint"] == "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
    assert received["headers"]["X-Api-Key"] == "test-key"
    assert received["headers"]["X-Api-Resource-Id"] == "seed-tts-2.0"
    assert received["headers"]["X-Api-Connect-Id"]
    assert [_volc_event(frame) for frame in transport.sent] == [1, 100, 102]
    assert transport.closed is True


def test_realtime_session_rejects_failure_status_in_session_finished():
    """A failed final status must not silently look like completed audio."""
    transport = _FakeRealtimeTransport(
        [
            _volc_response(50, session_id=b"connection-1"),
            _volc_response(150),
            _volc_response(
                152,
                json.dumps(
                    {"status_code": 55000000, "message": "finalization failed"}
                ).encode("utf-8"),
            ),
        ]
    )
    tts = VolcengineTTS(_config())
    tts._realtime_transport_factory = lambda endpoint, headers: transport

    session = tts.open_stream(tts.list_voices()[0])
    with pytest.raises(TTSError, match="finalization failed"):
        session.finish()

    assert transport.closed is True


def test_realtime_connection_failed_preserves_provider_status_and_message():
    """Collapsing ConnectionFailed into an event mismatch hides the cause."""
    transport = _FakeRealtimeTransport(
        [
            _volc_response(
                51,
                json.dumps(
                    {"status_code": 40100000, "message": "unauthorized"}
                ).encode("utf-8"),
                session_id=b"connection-1",
            ),
        ]
    )
    tts = VolcengineTTS(_config())
    tts._realtime_transport_factory = lambda endpoint, headers: transport

    with pytest.raises(TTSError, match="40100000.*unauthorized"):
        tts.open_stream(tts.list_voices()[0])

    assert transport.closed is True


def test_realtime_cancel_linearizes_with_task_request_send():
    """A cancellation cannot be overtaken by an already-gated TaskRequest."""
    transport = _GatedTaskRequestTransport(
        [
            _volc_response(50, session_id=b"connection-1"),
            _volc_response(150),
        ]
    )
    tts = VolcengineTTS(_config())
    tts._realtime_transport_factory = lambda endpoint, headers: transport
    session = tts.open_stream(tts.list_voices()[0])

    sender = threading.Thread(target=lambda: session.send_text("racing text"))
    canceller = threading.Thread(target=session.cancel)
    sender.start()
    assert transport.task_request_started.wait(timeout=1)
    canceller.start()
    transport.release_task_request.set()
    sender.join(timeout=1)
    canceller.join(timeout=1)

    assert not sender.is_alive()
    assert not canceller.is_alive()
    assert [_volc_event(frame) for frame in transport.sent] == [1, 100, 200, 101]


def test_realtime_cancel_discards_audio_received_before_reader_enqueue():
    """Audio that reaches the reader after cancellation must never be queued."""
    transport = _GatedAudioTransport(
        [
            _volc_response(50, session_id=b"connection-1"),
            _volc_response(150),
            _volc_response(352, b"\x01\x00", audio=True),
            _volc_response(152),
        ]
    )
    tts = VolcengineTTS(_config())
    tts._realtime_transport_factory = lambda endpoint, headers: transport
    session = tts.open_stream(tts.list_voices()[0])

    reader = threading.Thread(target=lambda: list(session.iter_audio()))
    reader.start()
    assert transport.audio_received.wait(timeout=1)
    session.cancel()
    transport.release_audio.set()
    reader.join(timeout=1)

    assert not reader.is_alive()
    assert session._reader_done.wait(timeout=1)
    assert list(session._audio) == []
    assert list(session.iter_audio()) == []
