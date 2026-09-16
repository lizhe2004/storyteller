import logging
import threading
import time

import pytest

from storyteller.core.config import Config
from storyteller.core.models import VoiceConfig
from storyteller.core.tts import CHUNK_AUDIO, StreamChunk
from storyteller.web.tts_scheduler import (
    SchedulerError,
    SchedulerLimits,
    SchedulerQueueTimeout,
    TTSScheduler,
)


class RecordingSession:
    def __init__(self, provider, key):
        self.provider = provider
        self.key = key
        self.sent = []
        self._closed = False
        self.cancel_calls = 0
        self.finish_calls = 0

    def send_text(self, text):
        if self.provider.fail_next_send:
            self.provider.fail_next_send = False
            raise RuntimeError("send failed")
        if self.provider.block_first_send and not self.sent:
            self.provider.first_send_started.set()
            assert self.provider.release_first_send.wait(timeout=1)
        self.sent.append(text)

    def iter_audio(self):
        if self.provider.emit_audio:
            return iter([StreamChunk(CHUNK_AUDIO, b"\x01\x00")])
        if self.provider.fail_next_audio:
            self.provider.fail_next_audio = False

            def fail_during_iteration():
                raise RuntimeError("audio iteration failed")
                yield  # pragma: no cover

            return fail_during_iteration()
        return iter(())

    def finish(self):
        self.finish_calls += 1
        if self.provider.fail_next_finish:
            self.provider.fail_next_finish = False
            raise RuntimeError("finish failed")
        self._close()

    def cancel(self):
        self.cancel_calls += 1
        self._close()

    def _close(self):
        if not self._closed:
            self._closed = True
            self.provider.closed(self.key)


class RecordingProvider:
    def __init__(self):
        self.opened = []
        self.active = {}
        self.max_active = {}
        self.active_count = 0
        self.max_active_count = 0
        self.sessions = []
        self.block_first_send = False
        self.first_send_started = threading.Event()
        self.release_first_send = threading.Event()
        self.fail_next_open = False
        self.fail_next_send = False
        self.fail_next_finish = False
        self.fail_next_audio = False
        self.emit_audio = False

    def open_stream(self, voice, *, directives=None, context=None):
        if self.fail_next_open:
            self.fail_next_open = False
            raise RuntimeError("open failed")
        key = (voice.provider, voice.voice_id)
        self.active[key] = self.active.get(key, 0) + 1
        self.max_active[key] = max(self.max_active.get(key, 0), self.active[key])
        self.active_count += 1
        self.max_active_count = max(self.max_active_count, self.active_count)
        self.opened.append(key)
        session = RecordingSession(self, key)
        self.sessions.append(session)
        return session

    def closed(self, key):
        self.active[key] -= 1
        self.active_count -= 1


class FakeRegistry:
    def __init__(self, provider):
        self.provider = provider

    def get_streaming_tts(self, name):
        assert name == "fake"
        return self.provider


class FakeClock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


def _scheduler(limits, provider=None, **kwargs):
    config = Config()
    config.set(
        "tts.scheduler.limits.fake.model-a",
        {
            "max_concurrent_sessions": limits.max_concurrent_sessions,
            "max_text_chunks_per_second": limits.max_text_chunks_per_second,
            "queue_size": limits.queue_size,
            "queue_timeout_seconds": limits.queue_timeout_seconds,
        },
    )
    return TTSScheduler(FakeRegistry(provider or RecordingProvider()), config, **kwargs)


def _voice(voice_id="voice-a"):
    return VoiceConfig(provider="fake", voice_id=voice_id)


def test_logs_text_when_scheduler_worker_sends_it_to_provider(caplog):
    """The provider-send event must not be emitted merely by enqueueing text."""
    provider = RecordingProvider()
    scheduler = _scheduler(SchedulerLimits(1, None, 2, 0.5), provider)
    session = scheduler.open("fake", "model-a", _voice())
    caplog.set_level(logging.INFO, logger="storyteller.web.tts_scheduler")

    session.send_text("真正发送")
    _wait_for(lambda: provider.sessions[0].sent == ["真正发送"])
    session.finish()

    assert any(
        "event=tts_provider_text_sent" in record.getMessage()
        and "text_length=4" in record.getMessage()
        and "message=文本已真正发送到TTS提供商" in record.getMessage()
        for record in caplog.records
    )


def test_logs_when_first_audio_chunk_arrives_from_provider(caplog):
    provider = RecordingProvider()
    provider.emit_audio = True
    scheduler = _scheduler(SchedulerLimits(1, None, 2, None), provider)
    session = scheduler.open("fake", "model-a", _voice(), phase="line", line_id="1")
    caplog.set_level(logging.INFO, logger="storyteller.web.tts_scheduler")

    assert list(session.iter_audio()) == [StreamChunk(CHUNK_AUDIO, b"\x01\x00")]
    session.cancel()

    assert any(
        "event=tts_first_audio_received" in record.getMessage()
        and "provider=fake" in record.getMessage()
        and "model=model-a" in record.getMessage()
        and "phase=line" in record.getMessage()
        and "line_id=1" in record.getMessage()
        and "first_audio_wait_ms=" in record.getMessage()
        for record in caplog.records
    )


def test_limits_resolve_with_defaults_provider_then_model_precedence():
    config = Config()
    config.set("tts.scheduler.default_queue_size", 10)
    config.set(
        "tts.scheduler.provider_limits.aliyun",
        {"max_concurrent_sessions": 2, "queue_size": 20},
    )
    # Model id contains a dot; model overrides win but fall back to provider/defaults.
    config.set(
        "tts.scheduler.limits.aliyun.seed-tts-2.0",
        {"max_concurrent_sessions": 4},
    )
    scheduler = TTSScheduler(FakeRegistry(RecordingProvider()), config)

    dotted = scheduler._limits_for("aliyun", "seed-tts-2.0")
    assert dotted.max_concurrent_sessions == 4   # model override wins
    assert dotted.queue_size == 20               # inherited from provider level

    other = scheduler._limits_for("aliyun", "seed-tts-1.0")
    assert other.max_concurrent_sessions == 2    # provider level
    assert other.queue_size == 20

    bare = scheduler._limits_for("volcengine", "anything")
    assert bare.max_concurrent_sessions == 1     # global defaults
    assert bare.queue_size == 10


def _wait_for(predicate):
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.001)
    assert predicate()


def _wait_for_waiters(scheduler, count):
    _wait_for(
        lambda: len(scheduler._groups[("fake", "model-a")]._waiters) == count
    )


def test_same_provider_model_never_exceeds_its_session_limit():
    """Removing the shared-key slot gate must let two active sessions through."""
    provider = RecordingProvider()
    scheduler = _scheduler(SchedulerLimits(1, None, 2, 0.5), provider)
    first = scheduler.open("fake", "model-a", _voice("voice-a"))
    second_opened = threading.Event()
    holder = []

    def open_second():
        holder.append(scheduler.open("fake", "model-a", _voice("voice-b")))
        second_opened.set()

    thread = threading.Thread(target=open_second)
    thread.start()
    _wait_for_waiters(scheduler, 1)
    assert not second_opened.wait(0.02)

    first.finish()
    assert second_opened.wait(1)
    holder[0].finish()
    thread.join(timeout=1)


def test_session_queue_waits_indefinitely_when_timeout_is_disabled():
    provider = RecordingProvider()
    scheduler = _scheduler(SchedulerLimits(1, None, 2, None), provider)
    first = scheduler.open("fake", "model-a", _voice("first"))
    holder = []

    thread = threading.Thread(
        target=lambda: holder.append(scheduler.open("fake", "model-a", _voice("second")))
    )
    thread.start()
    _wait_for_waiters(scheduler, 1)
    assert thread.is_alive()

    first.finish()
    thread.join(timeout=1)
    assert not thread.is_alive()
    holder[0].finish()


def test_opening_session_jumps_ahead_of_waiting_line_sessions():
    provider = RecordingProvider()
    scheduler = _scheduler(SchedulerLimits(1, None, 2, None), provider)
    first_line = scheduler.open(
        "fake", "model-a", _voice("line-1"), phase="line", line_id="1"
    )
    waiting_line = []
    opening = []

    line_thread = threading.Thread(target=lambda: waiting_line.append(
        scheduler.open("fake", "model-a", _voice("line-2"), phase="line", line_id="2")
    ))
    opening_thread = threading.Thread(target=lambda: opening.append(
        scheduler.open("fake", "model-a", _voice("opening"), phase="opening")
    ))
    line_thread.start()
    _wait_for_waiters(scheduler, 1)
    opening_thread.start()
    _wait_for_waiters(scheduler, 2)

    first_line.finish()
    opening_thread.join(timeout=1)
    assert not opening_thread.is_alive()
    assert provider.opened[-1] == ("fake", "opening")

    opening[0].finish()
    line_thread.join(timeout=1)
    assert not line_thread.is_alive()
    assert provider.opened[-1] == ("fake", "line-2")
    waiting_line[0].finish()

    assert provider.max_active_count == 1


def test_different_models_do_not_share_a_session_limit():
    """Keying capacity only by provider must make the second open block."""
    provider = RecordingProvider()
    scheduler = _scheduler(SchedulerLimits(1, None, 2, 0.5), provider)
    first = scheduler.open("fake", "model-a", _voice("voice-a"))

    other = scheduler.open("fake", "model-b", _voice("voice-b"))

    first.finish()
    other.finish()
    assert len(provider.sessions) == 2


def test_waiting_sessions_open_in_fifo_order():
    """Changing the waiting queue to LIFO must open the later caller first."""
    provider = RecordingProvider()
    scheduler = _scheduler(SchedulerLimits(1, None, 3, 0.5), provider)
    first = scheduler.open("fake", "model-a", _voice("first"))
    opened = []

    def queued(voice_id):
        session = scheduler.open("fake", "model-a", _voice(voice_id))
        opened.append((voice_id, session))

    second = threading.Thread(target=queued, args=("second",))
    third = threading.Thread(target=queued, args=("third",))
    second.start()
    _wait_for_waiters(scheduler, 1)
    third.start()
    _wait_for_waiters(scheduler, 2)

    first.finish()
    _wait_for(lambda: len(opened) == 1)
    assert opened[0][0] == "second"
    opened[0][1].finish()
    _wait_for(lambda: len(opened) == 2)
    assert opened[1][0] == "third"
    opened[1][1].finish()
    second.join(timeout=1)
    third.join(timeout=1)


def test_queue_timeout_raises_a_typed_scheduler_error(caplog):
    """Dropping a timed-out waiter or raising a generic error must fail."""
    scheduler = _scheduler(SchedulerLimits(1, None, 2, 0.01))
    first = scheduler.open("fake", "model-a", _voice())

    caplog.set_level(logging.ERROR, logger="storyteller.web.tts_scheduler")
    with pytest.raises(SchedulerQueueTimeout):
        scheduler.open("fake", "model-a", _voice("waiting"))

    assert any(
        "event=tts_queue_wait_failed" in record.getMessage()
        and "voice_id=waiting" in record.getMessage()
        and "error_type=SchedulerQueueTimeout" in record.getMessage()
        for record in caplog.records
    )
    first.cancel()


def test_full_text_buffer_applies_backpressure_without_unbounded_growth():
    """Replacing the bounded text queue with an unbounded one must fail."""
    provider = RecordingProvider()
    provider.block_first_send = True
    scheduler = _scheduler(SchedulerLimits(1, None, 1, 0.01), provider)
    session = scheduler.open("fake", "model-a", _voice())

    session.send_text("first")
    assert provider.first_send_started.wait(1)
    session.send_text("second")
    with pytest.raises(SchedulerQueueTimeout):
        session.send_text("third")

    provider.release_first_send.set()
    session.finish()
    assert provider.sessions[0].sent == ["first", "second"]


def test_cancel_rejects_a_sender_waiting_for_text_buffer_capacity():
    """Letting a blocked sender enqueue after cancel must fail."""
    provider = RecordingProvider()
    provider.block_first_send = True
    scheduler = _scheduler(SchedulerLimits(1, None, 1, 0.5), provider)
    session = scheduler.open("fake", "model-a", _voice())

    session.send_text("first")
    assert provider.first_send_started.wait(1)
    session.send_text("second")
    outcome = []
    completed = threading.Event()

    def send_waiting_text():
        try:
            session.send_text("third")
        except SchedulerError as exc:
            outcome.append(exc)
        finally:
            completed.set()

    thread = threading.Thread(target=send_waiting_text)
    thread.start()
    assert not completed.wait(0.02)

    session.cancel()

    assert completed.wait(1)
    assert len(outcome) == 1
    provider.release_first_send.set()
    thread.join(timeout=1)


def test_cancel_does_not_finish_the_underlying_session_after_an_inflight_send():
    """Treating cancellation as finish can drain audio the caller discarded."""
    provider = RecordingProvider()
    provider.block_first_send = True
    scheduler = _scheduler(SchedulerLimits(1, None, 1, 0.5), provider)
    session = scheduler.open("fake", "model-a", _voice())

    session.send_text("first")
    assert provider.first_send_started.wait(1)
    session.cancel()
    provider.release_first_send.set()
    _wait_for(lambda: provider.sessions[0].sent == ["first"])

    assert provider.sessions[0].cancel_calls == 1
    assert provider.sessions[0].finish_calls == 0


def test_text_rate_limit_delays_each_chunk_without_dropping_it():
    """Skipping the rate limiter must remove the recorded half-second delay."""
    provider = RecordingProvider()
    clock = FakeClock()
    scheduler = _scheduler(
        SchedulerLimits(1, 2.0, 2, 0.5),
        provider,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )
    session = scheduler.open("fake", "model-a", _voice())

    session.send_text("first")
    session.send_text("second")
    session.finish()

    assert clock.sleeps == [0.5]
    assert provider.sessions[0].sent == ["first", "second"]


def test_finish_is_idempotent_after_the_session_has_drained():
    """Treating a completed session as a send error must not break cleanup."""
    scheduler = _scheduler(SchedulerLimits(1, None, 2, 0.5))
    session = scheduler.open("fake", "model-a", _voice())

    session.finish()
    session.finish()


def test_provider_open_failure_releases_the_same_key_slot_for_retry(caplog):
    """Keeping a failed provider open in the FIFO gate must block a retry."""
    provider = RecordingProvider()
    provider.fail_next_open = True
    scheduler = _scheduler(SchedulerLimits(1, None, 2, 0.05), provider)

    caplog.set_level(logging.ERROR, logger="storyteller.web.tts_scheduler")
    with pytest.raises(RuntimeError, match="open failed"):
        scheduler.open("fake", "model-a", _voice())

    assert any(
        "event=tts_session_start_failed" in record.getMessage()
        and "error_type=RuntimeError" in record.getMessage()
        and "exception_message=open_failed" in record.getMessage()
        for record in caplog.records
    )
    recovered = scheduler.open("fake", "model-a", _voice())
    recovered.finish()


def test_worker_send_failure_releases_the_same_key_slot_for_retry():
    """Omitting worker-failure release must make the next same-key open time out."""
    provider = RecordingProvider()
    provider.fail_next_send = True
    scheduler = _scheduler(SchedulerLimits(1, None, 2, 0.05), provider)
    session = scheduler.open("fake", "model-a", _voice())

    session.send_text("will fail")
    _wait_for(lambda: provider.sessions[0].cancel_calls == 1)

    recovered = scheduler.open("fake", "model-a", _voice())
    recovered.finish()


def test_worker_finish_failure_releases_the_same_key_slot_for_retry():
    """Omitting finish-failure release must make the next same-key open time out."""
    provider = RecordingProvider()
    provider.fail_next_finish = True
    scheduler = _scheduler(SchedulerLimits(1, None, 2, 0.05), provider)
    session = scheduler.open("fake", "model-a", _voice())

    with pytest.raises(SchedulerError, match="session failed"):
        session.finish()

    recovered = scheduler.open("fake", "model-a", _voice())
    recovered.finish()


def test_audio_iteration_failure_releases_the_same_key_slot_for_retry():
    """Omitting audio-failure release must make the next same-key open time out."""
    provider = RecordingProvider()
    provider.fail_next_audio = True
    scheduler = _scheduler(SchedulerLimits(1, None, 2, 0.05), provider)
    session = scheduler.open("fake", "model-a", _voice())

    with pytest.raises(RuntimeError, match="audio iteration failed"):
        list(session.iter_audio())

    recovered = scheduler.open("fake", "model-a", _voice())
    recovered.finish()


def test_worker_start_failure_closes_provider_session_and_releases_slot(monkeypatch):
    """Leaving an opened session behind after worker startup failure blocks reuse."""
    provider = RecordingProvider()
    scheduler = _scheduler(SchedulerLimits(1, None, 2, 0.05), provider)

    def fail_to_start_worker(self):
        raise RuntimeError("worker start failed")

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", fail_to_start_worker)
        with pytest.raises(RuntimeError, match="worker start failed"):
            scheduler.open("fake", "model-a", _voice())

    recovered = scheduler.open("fake", "model-a", _voice())
    recovered.finish()
    assert provider.sessions[0].cancel_calls == 1
