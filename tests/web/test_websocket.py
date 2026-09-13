import json

from fastapi.testclient import TestClient

from storyteller.core.config import Config
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
    assert events[-1]["type"] == "complete" and len(audio) > 0 and len(audio) % 2 == 0
