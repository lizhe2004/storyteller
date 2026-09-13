# Observability Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add readable console and rotating text-file logs that trace each CLI/Web generation job, including phase, provider calls, persistence, WebSocket events, and elapsed time.

**Architecture:** Extend the existing Python logging setup with an idempotent console handler and a rotating file handler under `data_dir/logs`. Use `LoggerAdapter`-style context fields formatted as `key=value`; instrument the Web job and core provider boundaries with explicit start/completed/failed events and monotonic durations. Keep user-facing CLI progress and WebSocket messages separate from diagnostic logs, while adding server timestamps to important WebSocket events.

**Tech Stack:** Python `logging`, `logging.handlers.RotatingFileHandler`, `time.perf_counter`, FastAPI WebSocket, pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-observability-logging-design.md`

## Global Constraints

- File logs use traditional text format, not JSONL.
- File path is `data_dir/logs/storyteller.log` with size-based rotation.
- Log fields use `key=value` tokens and include available `job_id`, `project_id`, `phase`, and `duration_ms`.
- Full prompts and full model responses are not logged by default.
- File logging failures must not stop story generation; console logging remains available.
- Existing user-facing progress output and WebSocket event contracts remain compatible.

---

### Task 1: Add idempotent console/file logging setup

**Files:**
- Modify: `src/storyteller/core/config.py` to expose log file/rotation settings through defaults and environment loading.
- Modify: `src/storyteller/core/utils.py` to configure handlers and a key-value formatter.
- Test: `tests/unit/test_logging.py`

**Interfaces:**
- Produces `setup_logging(level="info", log_dir=None)` that can be called repeatedly without duplicate handlers.
- Produces `get_logger(name, **context)` or equivalent context helper used by later tasks.

- [ ] **Step 1: Write failing tests** for a console record, a file record under a temporary directory, key-value context fields, and repeated setup not duplicating handlers.
- [ ] **Step 2: Run `pytest tests/unit/test_logging.py -q` and verify the tests fail because file logging/context support is absent.
- [ ] **Step 3: Implement an idempotent setup with a normal text formatter, `RotatingFileHandler`, UTF-8 encoding, and safe fallback when the file handler cannot be created.
- [ ] **Step 4: Run `pytest tests/unit/test_logging.py -q` and verify all logging tests pass.
- [ ] **Step 5: Run existing unit tests that construct `Pipeline` to ensure logging setup does not duplicate output or break tests.

### Task 2: Add structured timing/context helpers

**Files:**
- Create: `src/storyteller/core/observability.py`
- Test: `tests/unit/test_observability.py`

**Interfaces:**
- `log_event(logger, level, event, *, context=None, **fields)` emits a readable `event=... key=value` message.
- `timed_event(logger, event, *, context=None, level=logging.INFO, **fields)` is a context manager that emits started/completed events and `duration_ms`; exceptions emit failed events and re-raise.
- `with_context(logger, **context)` returns a logger adapter that adds stable fields.

- [ ] **Step 1: Write failing tests for completed timing, failed timing with exception information, and merged context fields.
- [ ] **Step 2: Run `pytest tests/unit/test_observability.py -q` and verify failure.
- [ ] **Step 3: Implement the helpers using `time.perf_counter()` for durations and `datetime.now().astimezone()` for event timestamps.
- [ ] **Step 4: Run the focused tests and verify pass.

### Task 3: Instrument LLM and TTS provider boundaries

**Files:**
- Modify: `src/storyteller/providers/volcengine/llm.py`
- Modify: `src/storyteller/providers/openai_compatible/llm.py`
- Modify: `src/storyteller/providers/volcengine/tts.py`
- Modify: `src/storyteller/providers/openai_compatible/tts.py`
- Modify: `src/storyteller/providers/aliyun/tts.py`
- Test: existing provider integration tests plus `tests/unit/test_observability.py` additions

**Interfaces:**
- Each provider logs operation start/completion/failure with `provider`, `model` or `voice_id`, and request-specific metadata.
- Streaming operations log one start and one completion/failure event per request, not one event per token/audio chunk.

- [ ] **Step 1: Add tests around fake sessions asserting provider calls still return the same content/audio and emit timing records without logging prompt/response bodies at INFO.
- [ ] **Step 2: Run the focused provider tests and verify the new assertions fail.
- [ ] **Step 3: Add timing wrappers around HTTP calls and streaming iteration; preserve existing exception translation and timeout behavior.
- [ ] **Step 4: Run all provider integration tests and verify pass.

### Task 4: Instrument pipeline persistence and CLI progress

**Files:**
- Modify: `src/storyteller/core/pipeline.py`
- Modify: `src/storyteller/core/project.py`
- Test: `tests/unit/test_project.py` and relevant `tests/e2e/test_pipeline.py`

**Interfaces:**
- Project save/export logs include `project_id`, state, output path, and `duration_ms`.
- Pipeline phase logs include script generation, voice matching, audio generation, finalizing, and completion/failure.
- Existing `progress_level` behavior remains unchanged for user-facing output.

- [ ] **Step 1: Add tests verifying save/export operations emit named events and that `_log_progress` remains quiet in `quiet` mode.
- [ ] **Step 2: Run focused tests and verify failure.
- [ ] **Step 3: Replace diagnostic `print()` calls with logger events while retaining intentional CLI progress output; wrap save/export and phase boundaries with timing helpers.
- [ ] **Step 4: Run pipeline tests and verify pass.

### Task 5: Instrument Web jobs and add server timestamps to WebSocket events

**Files:**
- Modify: `src/storyteller/web/jobs.py`
- Modify: `src/storyteller/web/streaming.py`
- Modify: `src/storyteller/web/routes_ws.py`
- Test: `tests/web/test_websocket.py`

**Interfaces:**
- Each Web job has a logger context containing `job_id` and, once created, `project_id`.
- `script_preview`, `script_ready`, `status`, `line_start`, `line_end`, `finalizing`, `complete`, and `error` events include `server_time` without changing existing fields.
- Voice matching emits separate timing records so the gap between `phase=voices` and `script_ready` is diagnosable.

- [ ] **Step 1: Add WebSocket regression assertions for `server_time`, job/project identifiers where available, and the `voice_matching_started`/`voice_matching_completed` log events using a test log handler.
- [ ] **Step 2: Run `pytest tests/web/test_websocket.py -q` and verify failure.
- [ ] **Step 3: Add event enrichment at the Job boundary and timing logs around script generation, voice matching, persistence, `script_ready`, and each audio line; do not log every preview payload.
- [ ] **Step 4: Run WebSocket tests and verify pass.

### Task 6: Full verification and documentation

**Files:**
- Modify: `README.md` with log location, log-level configuration, and the command to inspect a job timeline.
- Test: full `tests/` suite and frontend tests/build because WebSocket payloads are consumed by the frontend.

- [ ] **Step 1: Run `.venv/bin/pytest -q`.
- [ ] **Step 2: Run `npm test -- --run && npm run build` in `web/frontend`.
- [ ] **Step 3: Manually inspect a generated `.storyteller/logs/storyteller.log` sample for readable fields and the voices-stage timeline.
- [ ] **Step 4: Update README with the verified paths and examples only.
- [ ] **Step 5: Re-run both test suites after documentation changes and review `git diff` for unrelated modifications.
