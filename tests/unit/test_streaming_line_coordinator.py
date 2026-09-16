from types import SimpleNamespace

from storyteller.web.streaming import _IncrementalLineCoordinator, _emit_stream_warning


class _FakePipeline:
    def _find_narrator_voice(self, script, char_voice_map):
        return next(iter(char_voice_map.values()))

    def voice_for_line(self, line, char_voice_map, narrator):
        return char_voice_map.get(line.character_id) or narrator


class _FakeOrchestrator:
    pipeline = _FakePipeline()


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
