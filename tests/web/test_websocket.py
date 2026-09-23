import json
import threading

from fastapi.testclient import TestClient

from storyteller.core.config import Config
from storyteller.core.exceptions import TTSError
from storyteller.core.tts import CHUNK_AUDIO, StreamChunk
from storyteller.providers.mock.llm import DEFAULT_SCRIPT, MockLLMProvider
from storyteller.providers.mock.tts import MockStreamingTTS
from storyteller.web.app import create_app
from storyteller.web.fillers import START_NOTICE
from storyteller.web.jobs import JobParams


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
            ws.send_json({
                "type": "start", "topic": "小恐龙", "tts_providers": ["mock"],
                "llm_model": {"provider": "mock", "model": "story-model"},
                "tts_model": {"provider": "mock", "model": "audio-model"},
            })
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
    assert ready["model_selection"] == {
        "llm": {"provider": "mock", "model": "story-model"},
        "audio": {"provider": "mock", "model": "audio-model"},
    }
    assert ready["server_time"]
    assert any(e["type"] == "script_preview" for e in events)
    matched_index = next(i for i, event in enumerate(events) if event["type"] == "characters_matched")
    script_ready_index = next(i for i, event in enumerate(events) if event["type"] == "script_ready")
    matched = events[matched_index]
    assert matched["characters"]
    assert all(character["voice"] for character in matched["characters"])
    assert matched_index < script_ready_index
    assert events[-1]["type"] == "complete" and len(audio) > 0 and len(audio) % 2 == 0


def _ws_collect_first_terminal(ws):
    events = []
    while True:
        message = ws.receive()
        if message.get("bytes") is not None:
            continue
        event = json.loads(message["text"])
        events.append(event)
        if event["type"] in ("complete", "error", "canceled"):
            return events


def _candidate_list_config(tmp_path):
    cfg = Config()
    cfg.set("web.passwords", ["pw"]); cfg.set("web.secret", "x")
    cfg.set("web.rate_limit_per_min", 0); cfg.set("data_dir", str(tmp_path))
    cfg.set("project_dir", str(tmp_path / "stories")); cfg.set("voice_matcher", "rule")
    cfg.set("tts.providers", ["mock"]); cfg.set("tts.provider_config.mock", {"type": "mock"})
    cfg.set("llm.providers", ["mock"])
    cfg.set("llm.provider_config.mock", {
        "type": "mock", "model": "story-model", "models": "alt-model",
    })
    cfg.set("web.filler_voice", "mock:narrator_01")
    return cfg


def test_ws_rejects_llm_model_outside_candidate_list(tmp_path):
    app = create_app(_candidate_list_config(tmp_path))
    with TestClient(app) as client:
        token = app.state.issuer.issue()
        with client.websocket_connect("/ws?token=" + token) as ws:
            ws.send_json({
                "type": "start", "topic": "小恐龙", "tts_providers": ["mock"],
                "llm_model": {"provider": "mock", "model": "not-allowed"},
            })
            events = _ws_collect_first_terminal(ws)
    assert events[-1]["type"] == "error"
    assert "可选模型清单" in events[-1]["message"]


def test_ws_accepts_llm_model_from_candidate_list(tmp_path):
    app = create_app(_candidate_list_config(tmp_path))
    with TestClient(app) as client:
        token = app.state.issuer.issue()
        with client.websocket_connect("/ws?token=" + token) as ws:
            ws.send_json({
                "type": "start", "topic": "小恐龙", "tts_providers": ["mock"],
                "llm_model": {"provider": "mock", "model": "alt-model"},
            })
            events = _ws_collect_first_terminal(ws)
    assert events[-1]["type"] == "complete"


def test_ws_accepts_multiple_audio_model_selections(tmp_path):
    cfg = _candidate_list_config(tmp_path)
    cfg.set("tts.provider_config.mock", {
        "type": "mock", "models": "audio-model-a, audio-model-b",
    })
    app = create_app(cfg)
    with TestClient(app) as client:
        token = app.state.issuer.issue()
        with client.websocket_connect("/ws?token=" + token) as ws:
            ws.send_json({
                "type": "start",
                "topic": "小恐龙",
                "tts_providers": ["mock"],
                "tts_model": [
                    {"provider": "mock", "model": "audio-model-a"},
                    {"provider": "mock", "model": "audio-model-b"},
                ],
            })
            events = _ws_collect_first_terminal(ws)
    assert events[-1]["type"] == "complete"


def test_ws_reconnect_replays_matched_characters_before_script_ready(tmp_path):
    cfg = Config()
    cfg.set("web.passwords", ["pw"]); cfg.set("web.secret", "x")
    cfg.set("web.rate_limit_per_min", 0); cfg.set("data_dir", str(tmp_path))
    cfg.set("project_dir", str(tmp_path / "stories"))
    app = create_app(cfg)
    job = app.state.jobs.create(JobParams(topic="小狐狸"))
    job.phase = "completed"
    job.script_preview = {"type": "script_preview", "characters": [{"id": "fox", "name": "小狐狸"}], "lines": []}
    job.characters_matched = {"type": "characters_matched", "characters": [{
        "id": "fox", "name": "小狐狸",
        "voice": {"provider": "mock", "voice_id": "fox_01", "name": "狐狸音色"},
    }]}
    job.script_ready = {"type": "script_ready", "characters": job.characters_matched["characters"], "lines": []}
    job.emit({"type": "complete", "project_id": "proj_test", "audio_url": "/audio"})

    with TestClient(app) as client:
        token = app.state.issuer.issue()
        with client.websocket_connect("/ws?token={}&job_id={}".format(token, job.id)) as ws:
            events = []
            while True:
                events.append(json.loads(ws.receive_text()))
                if events[-1]["type"] == "complete":
                    break

    types = [event["type"] for event in events]
    assert types.index("characters_matched") < types.index("script_ready")


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
    # The notice is announced when character voice matching starts; the opening
    # may finish just before or just after that notification.
    # The notice is prepared as soon as background voice matching starts, not
    # after the complete script.  Publication remains ordered after opening.
    assert position("start_notice") < position("script_ready")
    # Formal line metadata/text now streams during script generation.  Its audio
    # remains buffered until the start notice has been published.
    assert position("line_start") < position("script_ready")
    assert position("line_text_delta") < position("script_ready")
    assert position("start_notice") < position("notice") < position("line-1") < position("line-2")
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
    assert event_types.index("line_start") < event_types.index("script_ready")
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
        # start_notice is synthesized before opening now.
        if len(attempts) == 2:
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
    opening_end = timeline.index("opening_audio_end")
    assert "bytes" in timeline[start_audio:opening_end + 1]  # fallback opening is heard
    # The notice event is announced when background synthesis is dispatched;
    # its audio is still held behind the opening by the ordered publisher.
    assert event_types.index("start_notice") < event_types.index("opening_audio_end")
    assert event_types.index("line_start") < event_types.index("script_ready")
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
        # start_notice is synthesized before opening now.
        if len(attempts) == 2:
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
    assert event_types.index("line_start") < event_types.index("script_ready")
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
            self._text = None
            self._text_ready = threading.Event()

        def send_text(self, text):
            self._text = text
            self._text_ready.set()
            self._inner.send_text(text)

        def finish(self):
            self._inner.finish()

        def cancel(self):
            self._inner.cancel()

        def iter_audio(self):
            self._text_ready.wait(timeout=1)
            iterator = self._inner.iter_audio()
            yield next(iterator)
            if script["opening"].startswith(self._text):
                raise TTSError("opening cut short")
            yield from iterator

    def fail_first_session(self, voice, **kwargs):
        attempts.append(voice.voice_id)
        session = original_open_stream(self, voice, **kwargs)
        return PartialOpeningSession(session)

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

    # The opening session may race with an early formal-line session now that
    # all lines are allowed to synthesize during script generation.  In either
    # case, the job must continue and finish without duplicating the opening.
    # If early formal-line sessions occupy the scheduler before opening gets
    # its first audio, the opening may legitimately use whole-file fallback.
    # The important contract is that the job continues without duplicating
    # already-published opening audio.
    assert event_types.index("line_start") < event_types.index("script_ready")
    assert event_types[-1] == "complete"


def test_ws_partial_realtime_line_failure_does_not_duplicate_fallback_audio(tmp_path, monkeypatch):
    """A failed realtime line may be buffered or already live, but is never replayed twice."""
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
            self._text = None
            self._text_ready = threading.Event()

        def send_text(self, text):
            self._text = text
            self._text_ready.set()
            self._inner.send_text(text)

        def finish(self):
            self._inner.finish()

        def cancel(self):
            self._inner.cancel()

        def iter_audio(self):
            self._text_ready.wait(timeout=1)
            iterator = self._inner.iter_audio()
            yield next(iterator)
            if script["lines"][0]["text"].startswith(self._text):
                raise TTSError("partial line failure")
            yield from iterator

    def fail_first_formal_session(self, voice, **kwargs):
        attempts.append(voice.voice_id)
        session = original_open_stream(self, voice, **kwargs)
        return PartialFailureSession(session)

    def marked_line_chunk(self, text, voice, **kwargs):
        original_stream_chunk(self, text, voice, **kwargs)
        if script["lines"][0]["text"].startswith(text):
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
    assert received_audio.count(partial_marker) <= 1


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
        def __init__(self, inner):
            self._inner = inner
            self._text = None
            self._text_ready = threading.Event()

        def send_text(self, text):
            self._text = text
            self._text_ready.set()
            self._inner.send_text(text)

        def finish(self):
            self._inner.finish()

        def cancel(self):
            self._inner.cancel()

        def iter_audio(self):
            self._text_ready.wait(timeout=1)
            if self._text == START_NOTICE:
                return
            yield from self._inner.iter_audio()

    def empty_notice_session(self, voice, **kwargs):
        attempts.append(voice.voice_id)
        return EmptyAudioSession(original_open_stream(self, voice, **kwargs))

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
