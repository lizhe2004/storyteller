import logging

import pytest

from storyteller.core.observability import log_event, timed_event, with_context


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def test_log_event_merges_context_and_fields():
    logger = logging.getLogger("test.observability")
    capture = _Capture()
    logger.addHandler(capture)
    logger.setLevel(logging.INFO)
    try:
        log_event(
            with_context(logger, job_id="job_1"),
            logging.INFO,
            "phase_started",
            phase="voices",
        )
    finally:
        logger.removeHandler(capture)

    assert capture.messages == [
        "event=phase_started job_id=job_1 phase=voices"
    ]


def test_timed_event_logs_completion_and_failure():
    logger = logging.getLogger("test.observability.timing")
    capture = _Capture()
    logger.addHandler(capture)
    logger.setLevel(logging.INFO)
    try:
        with timed_event(logger, "save", project_id="proj_1"):
            pass
        with pytest.raises(RuntimeError):
            with timed_event(logger, "llm", provider="mock"):
                raise RuntimeError("boom")
    finally:
        logger.removeHandler(capture)

    assert capture.messages[0].startswith("event=save_started project_id=proj_1")
    assert "event=save_completed" in capture.messages[1]
    assert "duration_ms=" in capture.messages[1]
    assert "event=llm_started provider=mock" in capture.messages[2]
    assert "event=llm_failed" in capture.messages[3]
    assert "provider=mock" in capture.messages[3]
    assert "duration_ms=" in capture.messages[3]
    assert "exception_message=boom" in capture.messages[3]


def test_timed_event_redacts_urls_from_exception_messages():
    logger = logging.getLogger("test.observability.redaction")
    capture = _Capture()
    logger.addHandler(capture)
    logger.setLevel(logging.INFO)
    try:
        with pytest.raises(RuntimeError):
            with timed_event(logger, "tts", provider="aliyun"):
                raise RuntimeError("HTTP 403 https://example.com/audio?token=secret")
    finally:
        logger.removeHandler(capture)

    assert "exception_message=HTTP_403_[redacted_url]" in capture.messages[1]
    assert "secret" not in capture.messages[1]
