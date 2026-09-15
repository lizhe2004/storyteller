import json

from fastapi.testclient import TestClient

from storyteller.core.config import Config
from storyteller.core.exceptions import TTSError
from storyteller.providers.mock.llm import DEFAULT_SCRIPT, MockLLMProvider
from storyteller.providers.mock.tts import MockStreamingTTS
from storyteller.web.app import create_app


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

    timeline, events = [], []
    with TestClient(app) as client:
        token = app.state.issuer.issue()
        with client.websocket_connect("/ws?token=" + token) as ws:
            ws.send_json({"type": "start", "topic": "小恐龙", "tts_providers": ["mock"]})
            while True:
                message = ws.receive()
                if message.get("bytes") is not None:
                    timeline.append("audio")
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
    assert position("opening_text_delta") < position("opening_audio_start")
    assert position("opening_audio_start") < position("opening_audio_end") < position("start_notice")
    assert position("start_notice") < position("line_start") < position("line_text_delta")
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


def test_ws_opening_stream_failure_does_not_block_start_notice_or_lines(tmp_path, monkeypatch):
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

    monkeypatch.setattr(MockStreamingTTS, "open_stream", fail_only_opening)
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
    assert event_types.index("opening_audio_abort") < event_types.index("start_notice")
    assert event_types.index("start_notice") < event_types.index("line_start")
    assert event_types[-1] == "complete"
