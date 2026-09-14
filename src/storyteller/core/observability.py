from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import logging
import re
import time


def with_context(logger, **context):
    """Return a logger adapter carrying stable key/value context."""
    existing = getattr(logger, "extra", {}) if isinstance(logger, logging.LoggerAdapter) else {}
    merged = dict(existing)
    merged.update({key: value for key, value in context.items() if value is not None})
    base = logger.logger if isinstance(logger, logging.LoggerAdapter) else logger
    return logging.LoggerAdapter(base, merged)


def _format_value(value):
    return str(value).replace(" ", "_").replace("\n", "\\n")


def _safe_exception_message(exc):
    """Keep useful provider errors while removing URLs and line breaks."""
    message = str(exc or "")
    message = re.sub(r"https?://\S+", "[redacted_url]", message)
    return message.replace("\r", " ").replace("\n", " ")[:500]


def log_event(logger, level, event, *, context=None, **fields):
    """Write an event as a readable ``event=... key=value`` message."""
    adapter = with_context(logger, **(context or {}))
    values = {"event": event, **adapter.extra}
    values.update({key: value for key, value in fields.items() if value is not None})
    message = " ".join(
        "{}={}".format(key, _format_value(value))
        for key, value in values.items()
    )
    adapter.log(level, message)


@contextmanager
def timed_event(logger, event, *, context=None, level=logging.INFO, **fields):
    """Log start/completion or failure with a monotonic elapsed duration."""
    log_event(logger, level, "{}_started".format(event), context=context, **fields)
    started = time.perf_counter()
    try:
        yield
    except Exception as exc:
        duration = int((time.perf_counter() - started) * 1000)
        log_event(
            logger, logging.ERROR, "{}_failed".format(event), context=context,
            duration_ms=duration, error_type=type(exc).__name__,
            exception_message=_safe_exception_message(exc), **fields
        )
        raise
    else:
        duration = int((time.perf_counter() - started) * 1000)
        log_event(
            logger, level, "{}_completed".format(event), context=context,
            duration_ms=duration, **fields
        )


def server_time():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")
