# Observability Logging Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:verification-before-completion.

**Goal:** Ensure every user-visible streaming warning and important TTS degradation/failure has a structured server log with job/project/phase context.

**Architecture:** Keep WebSocket events for clients, and add a single streaming warning helper that emits the client event and structured server log together. Add missing scheduler/provider failure events only at component boundaries, preserving existing provider logs and business behavior.

**Tech Stack:** Python, `logging`, project `log_event`/`timed_event`, pytest.

### Task 1: Unify streaming warnings

**Files:** `src/storyteller/web/streaming.py`, `tests/web/test_websocket.py`.

- Add a structured warning helper carrying `event`, `phase`, `line_id`, exception type, and sanitized message.
- Route opening, start notice, sound, missing voice, realtime fallback, and line failure warnings through it.
- Add regression assertions that a realtime fallback produces a warning log as well as a WebSocket warning.

### Task 2: Cover scheduler failure boundaries

**Files:** `src/storyteller/web/tts_scheduler.py`, `tests/unit/test_tts_scheduler.py`.

- Log queue timeout, provider send failure, and session failure with provider/model/phase/line context.
- Preserve existing exception behavior and avoid duplicate success logs.

### Task 3: Verify the logging contract

**Files:** relevant logging tests.

- Assert warning events contain structured fields and sanitized exception text.
- Run focused tests, then the full suite.
