"""Per-provider/model scheduling for incremental TTS sessions."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging
import threading
import time
from typing import Optional

from ..core.exceptions import TTSError
from ..core.observability import _safe_exception_message, log_event
from ..core.streaming_tts import StreamingTTSSession
from ..core.tts import CHUNK_AUDIO


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SchedulerLimits:
    max_concurrent_sessions: int
    max_text_chunks_per_second: Optional[float]
    queue_size: int
    queue_timeout_seconds: Optional[float]


class SchedulerError(TTSError):
    """Base error raised by the streaming TTS scheduler."""


class SchedulerQueueTimeout(SchedulerError):
    """A session or text chunk waited longer than its configured limit."""


class _RateLimiter:
    def __init__(self, chunks_per_second, clock, sleep):
        self._interval = 1.0 / chunks_per_second if chunks_per_second else None
        self._clock = clock
        self._sleep = sleep
        self._next_allowed = None
        self._lock = threading.Lock()

    def wait(self):
        if self._interval is None:
            return
        with self._lock:
            now = self._clock()
            if self._next_allowed is None:
                self._next_allowed = now + self._interval
                return
            delay = self._next_allowed - now
            if delay > 0:
                self._sleep(delay)
                now = self._clock()
            self._next_allowed = max(now, self._next_allowed) + self._interval


class _SchedulerGroup:
    def __init__(self, limits, clock, sleep):
        self.limits = limits
        self._active = 0
        self._waiters = deque()
        self._next_waiter_sequence = 0
        self._changed = threading.Condition(threading.Lock())
        self.rate_limiter = _RateLimiter(
            limits.max_text_chunks_per_second, clock, sleep,
        )

    def acquire(self, timeout_seconds, *, priority=0):
        token = object()
        deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
        with self._changed:
            self._waiters.append((priority, self._next_waiter_sequence, token))
            self._next_waiter_sequence += 1
            self._waiters = deque(sorted(self._waiters, key=lambda item: (item[0], item[1])))
            while True:
                if self._waiters[0][2] is token and self._active < self.limits.max_concurrent_sessions:
                    self._waiters.popleft()
                    self._active += 1
                    self._changed.notify_all()
                    return
                if deadline is None:
                    self._changed.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    waiter = next(item for item in self._waiters if item[2] is token)
                    self._waiters.remove(waiter)
                    self._changed.notify_all()
                    raise SchedulerQueueTimeout("Timed out waiting for a TTS session slot")
                self._changed.wait(remaining)

    def release(self):
        with self._changed:
            if self._active:
                self._active -= 1
                self._changed.notify_all()


class ScheduledTTSSession(StreamingTTSSession):
    """A provider session whose text submission is bounded and scheduled."""

    _STOP = object()
    _CANCELLED = object()

    def __init__(self, session, group, limits, provider, model, *, phase=None, line_id=None):
        self._session = session
        self._group = group
        self._limits = limits
        self._provider = provider
        self._model = model
        self._phase = phase
        self._line_id = line_id
        self._texts = deque()
        self._text_changed = threading.Condition(threading.Lock())
        self._accepting = True
        self._cancelled = False
        self._released = False
        self._failure = None
        self._started_at = time.monotonic()
        self._first_audio_logged = False
        self._worker = threading.Thread(
            target=self._run, name="tts-scheduler", daemon=True,
        )
        self._worker.start()

    def send_text(self, text):
        with self._text_changed:
            self._raise_if_unavailable()
        self._group.rate_limiter.wait()
        self._enqueue_text(text)
        log_event(
            logger, logging.INFO, "tts_text_chunk_sent", provider=self._provider,
            model=self._model, text_length=len(text), phase=self._phase,
            line_id=self._line_id, message="文本进入TTS发送队列",
        )

    def iter_audio(self):
        try:
            for chunk in self._session.iter_audio():
                if chunk.kind == CHUNK_AUDIO and not self._first_audio_logged:
                    self._first_audio_logged = True
                    log_event(
                        logger, logging.INFO, "tts_first_audio_received",
                        provider=self._provider, model=self._model,
                        phase=self._phase, line_id=self._line_id,
                        first_audio_wait_ms=int(
                            (time.monotonic() - self._started_at) * 1000
                        ),
                        audio_bytes=len(chunk.data),
                        message="已收到TTS提供商首个音频块",
                    )
                yield chunk
        except Exception as exc:
            self._fail(exc)
            raise

    def finish(self):
        with self._text_changed:
            if self._cancelled:
                if self._failure is not None:
                    raise SchedulerError("Scheduled TTS session failed") from self._failure
                return
            self._accepting = False
            self._text_changed.notify_all()
        self._worker.join()
        with self._text_changed:
            if self._failure is not None:
                raise SchedulerError("Scheduled TTS session failed") from self._failure

    def cancel(self):
        with self._text_changed:
            if self._cancelled:
                return
            self._accepting = False
            self._cancelled = True
            self._texts.clear()
            self._text_changed.notify_all()
        try:
            self._session.cancel()
        finally:
            self._release()
        log_event(
            logger, logging.INFO, "tts_session_finished", provider=self._provider,
            model=self._model, status="cancelled", message="TTS会话已取消",
            phase=self._phase, line_id=self._line_id,
        )

    def _run(self):
        try:
            while True:
                text = self._take_text()
                if text is self._CANCELLED:
                    return
                if text is self._STOP:
                    self._session.finish()
                    self._release()
                    log_event(
                        logger, logging.INFO, "tts_session_finished",
                        provider=self._provider, model=self._model, status="finished",
                        message="TTS会话正常结束", phase=self._phase, line_id=self._line_id,
                    )
                    return
                self._session.send_text(text)
                log_event(
                    logger, logging.INFO, "tts_provider_text_sent",
                    provider=self._provider, model=self._model,
                    text_length=len(text), message="文本已真正发送到TTS提供商",
                    phase=self._phase, line_id=self._line_id,
                )
        except Exception as exc:
            self._fail(exc)

    def _enqueue_text(self, text):
        timeout = self._limits.queue_timeout_seconds
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._text_changed:
            self._raise_if_unavailable()
            while len(self._texts) >= self._limits.queue_size:
                if deadline is None:
                    self._text_changed.wait()
                    self._raise_if_unavailable()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SchedulerQueueTimeout(
                        "Timed out waiting for TTS text buffer capacity"
                    )
                self._text_changed.wait(remaining)
                self._raise_if_unavailable()
            self._texts.append(text)
            self._text_changed.notify_all()

    def _take_text(self):
        with self._text_changed:
            while True:
                if self._cancelled:
                    return self._CANCELLED
                if self._texts:
                    text = self._texts.popleft()
                    self._text_changed.notify_all()
                    return text
                if not self._accepting:
                    return self._STOP
                self._text_changed.wait()

    def _fail(self, exc):
        with self._text_changed:
            if self._failure is not None:
                return
            self._failure = exc
            self._accepting = False
            self._cancelled = True
            self._texts.clear()
            self._text_changed.notify_all()
        try:
            self._session.cancel()
        finally:
            self._release()
        log_event(
            logger, logging.ERROR, "tts_session_finished", provider=self._provider,
            model=self._model, status="failed", error_type=type(exc).__name__,
            exception_message=_safe_exception_message(exc),
            message="TTS会话失败", phase=self._phase, line_id=self._line_id,
        )

    def _release(self):
        with self._text_changed:
            if self._released:
                return
            self._released = True
        self._group.release()

    def _raise_if_unavailable(self):
        if self._failure is not None:
            raise SchedulerError("Scheduled TTS session failed") from self._failure
        if not self._accepting:
            raise SchedulerError("Scheduled TTS session is closed")


class TTSScheduler:
    """Open incremental TTS sessions subject to per-provider/model limits."""

    _SAFE_DEFAULTS = SchedulerLimits(1, None, 16, None)

    def __init__(self, registry, config, *, clock=None, sleep=None):
        self._registry = registry
        self._config = config
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._groups = {}
        self._groups_lock = threading.Lock()

    def open(self, provider, model, voice, *, directives=None, context=None,
             phase=None, line_id=None):
        limits = self._limits_for(provider, model)
        group = self._group_for(provider, model, limits)
        started = time.monotonic()
        log_event(
            logger, logging.INFO, "tts_session_queued", provider=provider,
            model=model, voice_id=voice.voice_id, phase=phase, line_id=line_id,
            message="TTS会话进入排队",
        )
        try:
            priority = -1 if phase in ("opening", "start_notice") else 0
            group.acquire(limits.queue_timeout_seconds, priority=priority)
        except Exception as exc:
            log_event(
                logger, logging.ERROR, "tts_queue_wait_failed",
                provider=provider, model=model, voice_id=voice.voice_id,
                queue_timeout_seconds=limits.queue_timeout_seconds,
                error_type=type(exc).__name__,
                exception_message=_safe_exception_message(exc),
                phase=phase, line_id=line_id,
                message="TTS会话等待调度槽位失败",
            )
            raise
        wait_ms = int((time.monotonic() - started) * 1000)
        log_event(
            logger, logging.INFO, "tts_queue_wait_finished", provider=provider,
            model=model, voice_id=voice.voice_id, queue_wait_ms=wait_ms,
            phase=phase, line_id=line_id, message="TTS会话获得调度槽位",
        )
        try:
            stream_provider = self._registry.get_streaming_tts(provider)
            if stream_provider is None:
                raise SchedulerError("TTS provider does not support text streaming: {}".format(provider))
            session = stream_provider.open_stream(
                voice, directives=directives, context=context,
            )
        except Exception as exc:
            group.release()
            log_event(
                logger, logging.ERROR, "tts_session_start_failed",
                provider=provider, model=model, voice_id=voice.voice_id,
                error_type=type(exc).__name__,
                exception_message=_safe_exception_message(exc),
                phase=phase, line_id=line_id,
                message="TTS会话启动失败",
            )
            raise
        log_event(
            logger, logging.INFO, "tts_session_started", provider=provider,
            model=model, voice_id=voice.voice_id, phase=phase, line_id=line_id,
            message="TTS会话已启动",
        )
        try:
            return ScheduledTTSSession(
                session, group, limits, provider, model,
                phase=phase, line_id=line_id,
            )
        except Exception:
            try:
                session.cancel()
            except Exception:
                logger.exception(
                    "Failed to cancel TTS provider session after scheduler startup failure"
                )
            finally:
                group.release()
            raise

    def _group_for(self, provider, model, limits):
        key = (provider, model)
        with self._groups_lock:
            group = self._groups.get(key)
            if group is None:
                group = _SchedulerGroup(limits, self._clock, self._sleep)
                self._groups[key] = group
            return group

    def _limits_for(self, provider, model):
        defaults = self._SAFE_DEFAULTS
        configured_defaults = {
            "max_concurrent_sessions": self._config.get(
                "tts.scheduler.default_max_concurrent_sessions",
                defaults.max_concurrent_sessions,
            ),
            "max_text_chunks_per_second": self._config.get(
                "tts.scheduler.default_max_text_chunks_per_second",
                defaults.max_text_chunks_per_second,
            ),
            "queue_size": self._config.get(
                "tts.scheduler.default_queue_size", defaults.queue_size,
            ),
            "queue_timeout_seconds": self._config.get(
                "tts.scheduler.default_queue_timeout_seconds",
                defaults.queue_timeout_seconds,
            ),
        }
        configured = self._config.get(
            "tts.scheduler.limits.{}.{}".format(provider, model), {},
        ) or {}
        # Per-provider overrides (env-friendly) sit between global defaults and
        # the finer-grained (provider, model) programmatic overrides.
        provider_configured = self._config.get(
            "tts.scheduler.provider_limits.{}".format(provider), {},
        ) or {}
        if isinstance(provider_configured, dict):
            for key, value in provider_configured.items():
                if value is not None:
                    configured_defaults[key] = value
        configured_defaults.update(configured)
        return SchedulerLimits(
            _positive_int(configured_defaults["max_concurrent_sessions"], defaults.max_concurrent_sessions),
            _positive_float_or_none(configured_defaults["max_text_chunks_per_second"]),
            _positive_int(configured_defaults["queue_size"], defaults.queue_size),
            _positive_float_or_none_with_fallback(
                configured_defaults["queue_timeout_seconds"],
                defaults.queue_timeout_seconds,
            ),
        )


def _positive_int(value, fallback):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def _positive_float_or_none(value):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _positive_float_or_none_with_fallback(value, fallback):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else None
