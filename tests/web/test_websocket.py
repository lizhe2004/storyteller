import json

from fastapi.testclient import TestClient

from storyteller.core.config import Config
from storyteller.core.exceptions import TTSError
from storyteller.core.tts import CHUNK_AUDIO, StreamChunk
from storyteller.providers.mock.llm import DEFAULT_SCRIPT, MockLLMProvider
from storyteller.providers.mock.tts import MockStreamingTTS
from storyteller.web.app import create_app
from storyteller.web.fillers import START_NOTICE


def test_ws_streams_pcm_and_completes(tmp_path):
    cfg = Config()
    cfg.set("web.passwords", ["pw"]); cfg.set("web.secret", "x")
    cfg.set("web.rate_limit_per_min", 0); cfg.set("data_dir", str(tmp_path))
    cfg.set("project_dir", str(tmp_path / "stories")); cfg.set("voice_matcher", "rule")
    cfg.set("tts.providers", ["mock"]); cfg.set("tts.provider_config.mock", {"type": "mock"})
    cfg.set("llm.providers", ["mock"]); cfg.set("llm.provider_config.mock", {"type": "mock"})
    cfg.set("web.filler_voice", "mock:narrator_01")
    app = create_app(cfg)
    audio = bytearray(); events = []
    with TestClient(app) as client:
        token = app.state.issuer.issue()
        with client.websocket_connect("/ws?token=" + token) as ws:
            ws.send_json({"type": "start", "topic": "小恐龙", "tts_providers": ["mock"]})
            while True:
                message = ws.receive()
                if message.get("bytes") is not None:
                    audio.extend(message["bytes"])
                    continue
                event = json.loads(message["text"]); events.append(event)
                if event["type"] in ("complete", "error", "canceled"):
                    break
    ready = next(e for e in events if e["type"] == "ready")
    assert ready["audio"] == {"encoding": "pcm_s16le", "sample_rate": 24000, "channels": 1}
    assert ready["server_time"]
    assert any(e["type"] == "script_preview" for e in events)
    assert events[-1]["type"] == "complete" and len(audio) > 0 and len(audio) % 2 == 0


def test_ws_streams_opening_start_notice_then_ordered_line_audio(tmp_path, monkeypatch):
    cfg = Config()
    cfg.set("web.passwords", ["pw"]); cfg.set("web.secret", "x")
    cfg.set("web.rate_limit_per_min", 0); cfg.set("data_dir", str(tmp_path))
    cfg.set("project_dir", str(tmp_path / "stories")); cfg.set("voice_matcher", "rule")
    cfg.set("tts.providers", ["mock"]); cfg.set("tts.provider_config.mock", {"type": "mock"})
    cfg.set("llm.providers", ["mock"]); cfg.set("llm.provider_config.mock", {"type": "mock"})
    cfg.set("web.filler_voice", "mock:narrator_01")
    app = create_app(cfg)
    script = {
        "title": DEFAULT_SCRIPT["title"],
        "opening": "夜幕降临，小橘发现公园里亮起了神秘的灯。",
        "characters": DEFAULT_SCRIPT["characters"],
        "lines": DEFAULT_SCRIPT["lines"],
    }
    monkeypatch.setattr(
        MockLLMProvider,
        "chat",
        lambda self, *args, **kwargs: json.dumps(script, ensure_ascii=False),
    )
    markers = {
        script["opening"]: ("opening", b"\x01\x00" * 240),
        START_NOTICE: ("notice", b"\x02\x00" * 240),
        script["lines"][0]["text"]: ("line-1", b"\x03\x00" * 240),
        script["lines"][1]["text"]: ("line-2", b"\x04\x00" * 240),
    }
    marker_names = list(markers.values()) + [("other-line", b"\x05\x00" * 240)]
    original_stream_chunk = MockStreamingTTS._stream_chunk

    def marked_stream_chunk(self, text, voice, **kwargs):
        original_stream_chunk(self, text, voice, **kwargs)
        if text in script["opening"]:
            return StreamChunk(CHUNK_AUDIO, markers[script["opening"]][1])
        if text in markers:
            return StreamChunk(CHUNK_AUDIO, markers[text][1])
        return StreamChunk(CHUNK_AUDIO, b"\x05\x00" * 240)

    monkeypatch.setattr(MockStreamingTTS, "_stream_chunk", marked_stream_chunk)

    timeline, events = [], []
    with TestClient(app) as client:
        token = app.state.issuer.issue()
        with client.websocket_connect("/ws?token=" + token) as ws:
            ws.send_json({"type": "start", "topic": "小恐龙", "tts_providers": ["mock"]})
            while True:
                message = ws.receive()
                if message.get("bytes") is not None:
                    timeline.append(next(
                        name for name, marker in marker_names
                        if message["bytes"] == marker
                    ))
                    continue
                event = json.loads(message["text"])
                events.append(event)
                timeline.append(event["type"])
                if event["type"] in ("complete", "error", "canceled"):
                    break

    def position(event_type):
        return timeline.index(event_type)

    preview = next(event for event in events if event["type"] == "script_preview" and event["opening"])
    script_ready = next(event for event in events if event["type"] == "script_ready")
    first_line_start = next(index for index, event in enumerate(events) if event["type"] == "line_start")
    first_line_delta = next(index for index, event in enumerate(events) if event["type"] == "line_text_delta")

    assert preview["opening"] in script["opening"]
    assert any(event["type"] == "script_preview" and event["opening"] == script["opening"] for event in events)
    assert "opening" not in script_ready
    assert position("ready") < position("script_preview") < position("opening_text_delta")
    assert position("script_preview") < position("opening_audio_start") < position("opening")
    # Live opening: its audio already reached the client before the finalized script.
    assert position("opening") < timeline.index("script_ready")
    assert position("opening") < position("opening_audio_end") < position("start_notice")
    assert position("start_notice") < position("notice") < position("line_start")
    assert position("line_start") < position("line_text_delta") < position("line-1") < position("line-2")
    assert first_line_start < first_line_delta
    assert not any(event["type"].startswith("filler_") for event in events)
    assert not any(event.get("kind") == "thinking" for event in events)
    assert events[-1]["duration_ms"] < 600  # opening PCM is excluded from story.mp3
    assert timeline[-1] == "complete"


def test_ws_without_opening_still_starts_notice_and_formal_lines(tmp_path):
    cfg = Config()
    cfg.set("web.passwords", ["pw"]); cfg.set("web.secret", "x")
    cfg.set("web.rate_limit_per_min", 0); cfg.set("data_dir", str(tmp_path))
    cfg.set("project_dir", str(tmp_path / "stories")); cfg.set("voice_matcher", "rule")
    cfg.set("tts.providers", ["mock"]); cfg.set("tts.provider_config.mock", {"type": "mock"})
    cfg.set("llm.providers", ["mock"]); cfg.set("llm.provider_config.mock", {"type": "mock"})
    cfg.set("web.filler_voice", "mock:narrator_01")
    app = create_app(cfg)

    event_types = []
    with TestClient(app) as client:
        token = app.state.issuer.issue()
        with client.websocket_connect("/ws?token=" + token) as ws:
            ws.send_json({"type": "start", "topic": "小恐龙", "tts_providers": ["mock"]})
            while True:
                message = ws.receive()
                if message.get("bytes") is not None:
                    continue
                event = json.loads(message["text"])
                event_types.append(event["type"])
                if event["type"] in ("complete", "error", "canceled"):
                    break

    assert "opening_text_delta" not in event_types
    assert event_types.index("start_notice") < event_types.index("line_start")
    assert "line_text_delta" in event_types
    assert event_types[-1] == "complete"


def test_ws_opening_realtime_failure_falls_back_to_whole_file_tts(tmp_path, monkeypatch):
    cfg = Config()
    cfg.set("web.passwords", ["pw"]); cfg.set("web.secret", "x")
    cfg.set("web.rate_limit_per_min", 0); cfg.set("data_dir", str(tmp_path))
    cfg.set("project_dir", str(tmp_path / "stories")); cfg.set("voice_matcher", "rule")
    cfg.set("tts.providers", ["mock"]); cfg.set("tts.provider_config.mock", {"type": "mock"})
    cfg.set("llm.providers", ["mock"]); cfg.set("llm.provider_config.mock", {"type": "mock"})
    cfg.set("web.filler_voice", "mock:narrator_01")
    script = {
        "title": DEFAULT_SCRIPT["title"],
        "opening": "夜幕降临，小橘发现公园里亮起了神秘的灯。",
        "characters": DEFAULT_SCRIPT["characters"],
        "lines": DEFAULT_SCRIPT["lines"],
    }
    monkeypatch.setattr(
        MockLLMProvider,
        "chat",
        lambda self, *args, **kwargs: json.dumps(script, ensure_ascii=False),
    )
    original_open_stream = MockStreamingTTS.open_stream
    original_synthesize = MockStreamingTTS.synthesize
    attempts, synth_texts = [], []

    def fail_only_opening(self, voice, **kwargs):
        attempts.append(voice.voice_id)
        if len(attempts) == 1:
            raise TTSError("opening unavailable")
        return original_open_stream(self, voice, **kwargs)

    def record_synthesis(self, text, voice, out, **kwargs):
        synth_texts.append(text)
        return original_synthesize(self, text, voice, out, **kwargs)

    monkeypatch.setattr(MockStreamingTTS, "open_stream", fail_only_opening)
    monkeypatch.setattr(MockStreamingTTS, "synthesize", record_synthesis)
    app = create_app(cfg)
    timeline, event_types = [], []
    with TestClient(app) as client:
        token = app.state.issuer.issue()
        with client.websocket_connect("/ws?token=" + token) as ws:
            ws.send_json({"type": "start", "topic": "小恐龙", "tts_providers": ["mock"]})
            while True:
                message = ws.receive()
                if message.get("bytes") is not None:
                    timeline.append("bytes")
                    continue
                event = json.loads(message["text"])
                event_types.append(event["type"])
                timeline.append(event["type"])
                if event["type"] in ("complete", "error", "canceled"):
                    break

    # Whole-file TTS produced the full opening; notice/lines stayed realtime.
    assert script["opening"] in synth_texts
    assert "opening_audio_abort" not in event_types
    assert "opening_audio_end" in event_types
    start_audio = timeline.index("opening_audio_start")
    start_notice = timeline.index("start_notice")
    assert "bytes" in timeline[start_audio:start_notice]  # fallback opening is heard first
    assert event_types.index("opening_audio_end") < event_types.index("start_notice")
    assert event_types.index("start_notice") < event_types.index("line_start")
    assert len(attempts) >= 3
    assert event_types[-1] == "complete"


def test_ws_opening_fallback_unavailable_aborts_opening_but_keeps_lines(tmp_path, monkeypatch):
    cfg = Config()
    cfg.set("web.passwords", ["pw"]); cfg.set("web.secret", "x")
    cfg.set("web.rate_limit_per_min", 0); cfg.set("data_dir", str(tmp_path))
    cfg.set("project_dir", str(tmp_path / "stories")); cfg.set("voice_matcher", "rule")
    cfg.set("tts.providers", ["mock"]); cfg.set("tts.provider_config.mock", {"type": "mock"})
    cfg.set("llm.providers", ["mock"]); cfg.set("llm.provider_config.mock", {"type": "mock"})
    cfg.set("web.filler_voice", "mock:narrator_01")
    script = {
        "title": DEFAULT_SCRIPT["title"],
        "opening": "夜幕降临，小橘发现公园里亮起了神秘的灯。",
        "characters": DEFAULT_SCRIPT["characters"],
        "lines": DEFAULT_SCRIPT["lines"],
    }
    monkeypatch.setattr(
        MockLLMProvider,
        "chat",
        lambda self, *args, **kwargs: json.dumps(script, ensure_ascii=False),
    )
    original_open_stream = MockStreamingTTS.open_stream
    attempts = []

    def fail_only_opening(self, voice, **kwargs):
        attempts.append(voice.voice_id)
        if len(attempts) == 1:
            raise TTSError("opening unavailable")
        return original_open_stream(self, voice, **kwargs)

    def synth_fails(self, text, voice, out, **kwargs):
        raise TTSError("opening fallback down")

    monkeypatch.setattr(MockStreamingTTS, "open_stream", fail_only_opening)
    monkeypatch.setattr(MockStreamingTTS, "synthesize", synth_fails)
    app = create_app(cfg)
    event_types = []
    with TestClient(app) as client:
        token = app.state.issuer.issue()
        with client.websocket_connect("/ws?token=" + token) as ws:
            ws.send_json({"type": "start", "topic": "小恐龙", "tts_providers": ["mock"]})
            while True:
                message = ws.receive()
                if message.get("bytes") is not None:
                    continue
                event = json.loads(message["text"])
                event_types.append(event["type"])
                if event["type"] in ("complete", "error", "canceled"):
                    break

    assert "opening_audio_abort" in event_types
    assert event_types.index("start_notice") < event_types.index("line_start")
    assert len(attempts) >= 3  # notice and formal lines still use realtime sessions
    assert event_types[-1] == "complete"


def test_ws_partial_opening_audio_is_released_without_whole_file_retry(tmp_path, monkeypatch):
    cfg = Config()
    cfg.set("web.passwords", ["pw"]); cfg.set("web.secret", "x")
    cfg.set("web.rate_limit_per_min", 0); cfg.set("data_dir", str(tmp_path))
    cfg.set("project_dir", str(tmp_path / "stories")); cfg.set("voice_matcher", "rule")
    cfg.set("tts.providers", ["mock"]); cfg.set("tts.provider_config.mock", {"type": "mock"})
    cfg.set("llm.providers", ["mock"]); cfg.set("llm.provider_config.mock", {"type": "mock"})
    cfg.set("web.filler_voice", "mock:narrator_01")
    script = dict(DEFAULT_SCRIPT, opening="夜幕降临，小橘发现公园里亮起了神秘的灯。")
    monkeypatch.setattr(
        MockLLMProvider,
        "chat",
        lambda self, *args, **kwargs: json.dumps(script, ensure_ascii=False),
    )
    original_open_stream = MockStreamingTTS.open_stream
    original_synthesize = MockStreamingTTS.synthesize
    attempts, synth_texts = [], []

    class PartialOpeningSession:
        def __init__(self, inner):
            self._inner = inner

        def send_text(self, text):
            self._inner.send_text(text)

        def finish(self):
            self._inner.finish()

        def cancel(self):
            self._inner.cancel()

        def iter_audio(self):
            iterator = self._inner.iter_audio()
            yield next(iterator)
            raise TTSError("opening cut short")

    def fail_first_session(self, voice, **kwargs):
        attempts.append(voice.voice_id)
        session = original_open_stream(self, voice, **kwargs)
        return PartialOpeningSession(session) if len(attempts) == 1 else session

    def record_synthesis(self, text, voice, out, **kwargs):
        synth_texts.append(text)
        return original_synthesize(self, text, voice, out, **kwargs)

    monkeypatch.setattr(MockStreamingTTS, "open_stream", fail_first_session)
    monkeypatch.setattr(MockStreamingTTS, "synthesize", record_synthesis)
    app = create_app(cfg)
    event_types = []
    with TestClient(app) as client:
        token = app.state.issuer.issue()
        with client.websocket_connect("/ws?token=" + token) as ws:
            ws.send_json({"type": "start", "topic": "小恐龙", "tts_providers": ["mock"]})
            while True:
                message = ws.receive()
                if message.get("bytes") is None:
                    event = json.loads(message["text"])
                    event_types.append(event["type"])
                    if event["type"] in ("complete", "error", "canceled"):
                        break

    assert "opening_audio_abort" in event_types
    assert script["opening"] not in synth_texts  # already-played opening is not re-spoken
    assert event_types.index("start_notice") < event_types.index("line_start")
    assert event_types[-1] == "complete"


def test_ws_partial_realtime_line_failure_discards_partial_bytes_before_fallback(tmp_path, monkeypatch):
    """Streaming a partial line directly would duplicate it when file TTS takes over."""
    cfg = Config()
    cfg.set("web.passwords", ["pw"]); cfg.set("web.secret", "x")
    cfg.set("web.rate_limit_per_min", 0); cfg.set("data_dir", str(tmp_path))
    cfg.set("project_dir", str(tmp_path / "stories")); cfg.set("voice_matcher", "rule")
    cfg.set("tts.providers", ["mock"]); cfg.set("tts.provider_config.mock", {"type": "mock"})
    cfg.set("llm.providers", ["mock"]); cfg.set("llm.provider_config.mock", {"type": "mock"})
    cfg.set("web.filler_voice", "mock:narrator_01")
    script = dict(DEFAULT_SCRIPT, opening="开场", lines=DEFAULT_SCRIPT["lines"][:2])
    monkeypatch.setattr(MockLLMProvider, "chat", lambda self, *args, **kwargs: json.dumps(script, ensure_ascii=False))
    original_open_stream = MockStreamingTTS.open_stream
    original_stream_chunk = MockStreamingTTS._stream_chunk
    original_synthesize = MockStreamingTTS.synthesize
    attempts, fallback_texts, received_audio = [], [], []
    partial_marker = b"\x7f\x7f" * 240

    class PartialFailureSession:
        def __init__(self, inner):
            self._inner = inner

        def send_text(self, text):
            self._inner.send_text(text)

        def finish(self):
            self._inner.finish()

        def cancel(self):
            self._inner.cancel()

        def iter_audio(self):
            iterator = self._inner.iter_audio()
            yield next(iterator)
            raise TTSError("partial line failure")

    def fail_first_formal_session(self, voice, **kwargs):
        attempts.append(voice.voice_id)
        session = original_open_stream(self, voice, **kwargs)
        return PartialFailureSession(session) if len(attempts) == 3 else session

    def marked_line_chunk(self, text, voice, **kwargs):
        original_stream_chunk(self, text, voice, **kwargs)
        if text == script["lines"][0]["text"]:
            return StreamChunk(CHUNK_AUDIO, partial_marker)
        return StreamChunk(CHUNK_AUDIO, b"\x01\x00" * 240)

    def record_fallback(self, text, voice, out, **kwargs):
        fallback_texts.append(text)
        return original_synthesize(self, text, voice, out, **kwargs)

    monkeypatch.setattr(MockStreamingTTS, "open_stream", fail_first_formal_session)
    monkeypatch.setattr(MockStreamingTTS, "_stream_chunk", marked_line_chunk)
    monkeypatch.setattr(MockStreamingTTS, "synthesize", record_fallback)
    app = create_app(cfg)
    with TestClient(app) as client:
        token = app.state.issuer.issue()
        with client.websocket_connect("/ws?token=" + token) as ws:
            ws.send_json({"type": "start", "topic": "小恐龙", "tts_providers": ["mock"]})
            while True:
                message = ws.receive()
                if message.get("bytes") is not None:
                    received_audio.append(message["bytes"])
                    continue
                event = json.loads(message["text"])
                if event["type"] in ("complete", "error", "canceled"):
                    break

    assert script["lines"][0]["text"] in fallback_texts
    assert partial_marker not in received_audio


def test_ws_empty_start_notice_realtime_audio_uses_cached_fallback(tmp_path, monkeypatch):
    """An empty notice session is a realtime failure, not a successful silent notice."""
    cfg = Config()
    cfg.set("web.passwords", ["pw"]); cfg.set("web.secret", "x")
    cfg.set("web.rate_limit_per_min", 0); cfg.set("data_dir", str(tmp_path))
    cfg.set("project_dir", str(tmp_path / "stories")); cfg.set("voice_matcher", "rule")
    cfg.set("tts.providers", ["mock"]); cfg.set("tts.provider_config.mock", {"type": "mock"})
    cfg.set("llm.providers", ["mock"]); cfg.set("llm.provider_config.mock", {"type": "mock"})
    cfg.set("web.filler_voice", "mock:narrator_01")
    original_open_stream = MockStreamingTTS.open_stream
    original_synthesize = MockStreamingTTS.synthesize
    attempts, synth_texts, event_types = [], [], []
    script = dict(DEFAULT_SCRIPT, opening="开场")
    monkeypatch.setattr(
        MockLLMProvider,
        "chat",
        lambda self, *args, **kwargs: json.dumps(script, ensure_ascii=False),
    )

    class EmptyAudioSession:
        def send_text(self, text):
            pass

        def finish(self):
            pass

        def cancel(self):
            pass

        def iter_audio(self):
            return iter(())

    def empty_notice_session(self, voice, **kwargs):
        attempts.append(voice.voice_id)
        if len(attempts) == 2:
            return EmptyAudioSession()
        return original_open_stream(self, voice, **kwargs)

    def record_synthesis(self, text, voice, out, **kwargs):
        synth_texts.append(text)
        return original_synthesize(self, text, voice, out, **kwargs)

    monkeypatch.setattr(MockStreamingTTS, "open_stream", empty_notice_session)
    monkeypatch.setattr(MockStreamingTTS, "synthesize", record_synthesis)
    app = create_app(cfg)
    with TestClient(app) as client:
        token = app.state.issuer.issue()
        with client.websocket_connect("/ws?token=" + token) as ws:
            ws.send_json({"type": "start", "topic": "小恐龙", "tts_providers": ["mock"]})
            while True:
                message = ws.receive()
                if message.get("bytes") is not None:
                    continue
                event = json.loads(message["text"])
                event_types.append(event["type"])
                if event["type"] in ("complete", "error", "canceled"):
                    break

    assert START_NOTICE in synth_texts
    assert "warning" in event_types
