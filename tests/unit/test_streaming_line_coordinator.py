from types import SimpleNamespace

from storyteller.core.tts import CHUNK_AUDIO, StreamChunk
from storyteller.web.streaming import (
    StreamOrchestrator,
    _IncrementalLineCoordinator,
    _emit_stream_warning,
)


class _FakePipeline:
    def _find_narrator_voice(self, script, char_voice_map):
        return next(iter(char_voice_map.values()))

    def voice_for_line(self, line, char_voice_map, narrator):
        return char_voice_map.get(line.character_id) or narrator


class _FakeOrchestrator:
    pipeline = _FakePipeline()

    def __init__(self):
        self.open_calls = []

    def _open_session(self, scheduler, voice, **kwargs):
        self.open_calls.append(kwargs)
        return _FakeSession()


class _FakeSession:
    def send_text(self, text):
        pass

    def iter_audio(self):
        yield StreamChunk(CHUNK_AUDIO, b"\x00\x00")

    def finish(self):
        pass

    def cancel(self):
        pass


class _FakeLease:
    def publish(self, data):
        pass

    def commit(self):
        pass

    def abort(self):
        pass


class _FakeJob:
    id = "job_1"
    project_id = "proj_1"
    phase = "line"
    total = 2

    def emit(self, event):
        self.events = getattr(self, "events", [])
        self.events.append(event)


class _FakePublisher:
    def add_phase(self, key, *, live=False):
        pass

    def lease(self, key):
        return _FakeLease()


def test_open_session_logs_non_sensitive_session_parameters(caplog):
    class _Registry:
        def get_tts_model(self, voice):
            return "tts-model-1"

    class _Scheduler:
        def open(self, *args, **kwargs):
            return "session"

    orchestrator = object.__new__(StreamOrchestrator)
    orchestrator.registry = _Registry()
    voice = SimpleNamespace(
        provider="volcengine",
        voice_id="voice-1",
        language="zh-CN",
        speed=1.0,
        pitch=1.0,
        volume=1.0,
    )

    with caplog.at_level("INFO", logger="storyteller.web.streaming"):
        result = orchestrator._open_session(
            _Scheduler(),
            voice,
            directives=["请低沉缓慢地叙述"],
            context=None,
            phase="line",
            line_id="line-1",
        )

    assert result == "session"
    message = caplog.records[-1].getMessage()
    assert "event=tts_session_started" in message
    assert '"provider":"volcengine"' in message
    assert '"model":"tts-model-1"' in message
    assert '"voice_id":"voice-1"' in message
    assert "请低沉缓慢地叙述" in message
    assert "api_key" not in message.lower()


def test_new_streamed_line_inherits_provisional_voice_context():
    voice = object()
    coordinator = _IncrementalLineCoordinator(
        _FakeOrchestrator(), _FakeJob(), _FakePublisher(), object(), {}
    )

    coordinator.set_provisional_voice_context(
        SimpleNamespace(characters=[SimpleNamespace(id="hero", voice_config=voice)])
    )
    coordinator._maybe_start = lambda index: None

    coordinator.on_delta(
        1,
        {"line_id": "2", "line_type": "dialogue", "character_id": "hero"},
        "第二句",
    )

    assert coordinator._voices[1] is voice


def test_incremental_tts_passes_direction_when_it_is_available():
    voice = object()
    orchestrator = _FakeOrchestrator()
    coordinator = _IncrementalLineCoordinator(
        orchestrator, _FakeJob(), _FakePublisher(), object(), {}
    )
    coordinator._voices[0] = voice

    coordinator.on_delta(
        0,
        {
            "line_id": "1",
            "line_type": "narration",
            "direction": "请低沉缓慢地叙述",
        },
        "第一句",
    )
    coordinator.on_complete(0, {})
    coordinator.wait(0)

    assert orchestrator.open_calls[0]["directives"] == ["请低沉缓慢地叙述"]
    assert orchestrator.open_calls[0]["context"] is None


def test_incremental_tts_starts_without_direction_when_missing():
    voice = object()
    orchestrator = _FakeOrchestrator()
    coordinator = _IncrementalLineCoordinator(
        orchestrator, _FakeJob(), _FakePublisher(), object(), {}
    )
    coordinator._voices[0] = voice

    coordinator.on_delta(
        0,
        {"line_id": "1", "line_type": "narration"},
        "没有指令的台词",
    )
    coordinator.on_complete(0, {})
    coordinator.wait(0)

    assert orchestrator.open_calls[0]["directives"] is None
    assert orchestrator.open_calls[0]["context"] is None


def test_stream_warning_is_emitted_to_client_and_structured_log(caplog):
    job = _FakeJob()
    error = TimeoutError("TTS slot unavailable")

    with caplog.at_level("WARNING", logger="storyteller.web.streaming"):
        _emit_stream_warning(
            job,
            "实时语音降级：TTS slot unavailable",
            event="tts_line_realtime_fallback",
            phase="line",
            line_id="4",
            exc=error,
        )

    assert job.events == [{
        "type": "warning",
        "line_id": "4",
        "message": "实时语音降级：TTS slot unavailable",
    }]
    message = caplog.records[-1].getMessage()
    assert "event=tts_line_realtime_fallback" in message
    assert "job_id=job_1" in message
    assert "project_id=proj_1" in message
    assert "line_id=4" in message
    assert "error_type=TimeoutError" in message
