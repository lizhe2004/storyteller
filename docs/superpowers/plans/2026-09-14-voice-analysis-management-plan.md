# 历史音色分析管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent Web-managed background job that analyzes historical TTS samples with Gemini, persists resumable results, and exposes list polling plus a dedicated detail WebSocket.

**Architecture:** Add a filesystem-backed `VoiceAnalysisManager` independent from the audio `JobManager` and `/ws` playback protocol. REST creates/reads/controls analysis jobs; the list page polls summaries and the detail page loads a snapshot then subscribes to `/ws/voice-analysis` for JSON-only progress events. Gemini integration remains behind a provider adapter and never writes `voices.json` automatically.

**Tech Stack:** Python, FastAPI, asyncio/thread executor, existing filesystem project storage, Vue 3 + TypeScript, Vitest, pytest, browser-use CDP.

**Spec:** `docs/superpowers/specs/2026-09-14-voice-analysis-management-design.md`

## Global Constraints

- Do not reuse the audio generation `/ws` endpoint or send PCM on the analysis WebSocket.
- Closing the browser must not cancel a running analysis job.
- Persist manifest, sample associations, raw/normalized results, summaries, and suggestions under `.storyteller/voice-analysis/<job_id>/`.
- Reuse completed work only when `sample_id + model + prompt_version + analysis_config_version` matches.
- Analyze project-generated TTS audio only; never expose API keys to the browser or logs.
- Do not modify `voices.json` automatically; suggestions require explicit approval.
- Preserve current backend and frontend behavior and keep existing tests passing.

---

### Task 1: Define analysis job persistence and sample inventory

**Files:**
- Create: `src/storyteller/web/voice_analysis.py`
- Modify: `src/storyteller/core/project.py` only if a reusable project scanner is needed
- Test: `tests/unit/test_voice_analysis.py`

**Interfaces:**
- `VoiceAnalysisManager.create_job(options) -> VoiceAnalysisJob`
- `VoiceAnalysisManager.get_job(job_id) -> VoiceAnalysisJob | None`
- `VoiceAnalysisManager.list_jobs() -> list[dict]`
- `VoiceAnalysisManager.resume(job_id)`, `cancel(job_id)`, `retry(job_id)`
- `VoiceAnalysisJob.snapshot() -> dict`
- `build_sample_inventory(stories_root, catalog_loader, limit) -> list[dict]`

- [ ] Write failing tests for scanning `story.script.json`, matching audio paths to lines and characters, retaining `catalog_snapshot`, deterministic per-voice sampling capped at 10 by default and 20 maximum, and manifest persistence.
- [ ] Run `pytest tests/unit/test_voice_analysis.py -q` and verify the new tests fail for missing manager/inventory behavior.
- [ ] Implement the job directory, manifest schema, inventory scanner, stratified deterministic sampler, and atomic JSON writes. Store each sample result in its own file and keep terminal/error counters in the manifest.
- [ ] Run the focused tests and verify they pass.
- [ ] Add tests for resume identity (`sample_id`, model, prompt, config versions), cancellation, retrying only failed samples, and missing/corrupt audio being recorded as skipped or failed rather than aborting the whole inventory.
- [ ] Run `pytest tests/unit/test_voice_analysis.py -q` again.

### Task 2: Add Gemini audio analysis adapter and normalization

**Files:**
- Create: `src/storyteller/providers/gemini/llm.py`
- Create: `src/storyteller/providers/gemini/__init__.py`
- Modify: `src/storyteller/providers/registry.py`
- Modify: `pyproject.toml`
- Test: `tests/unit/test_gemini_audio_analysis.py`

**Interfaces:**
- `GeminiAudioAnalyzer.analyze_sample(sample, include_thoughts=False) -> dict`
- `normalize_voice_analysis(payload) -> dict`
- `GeminiAudioAnalyzer.summarize_voice(samples, catalog_snapshot) -> dict`

- [ ] Write failing tests using a fake HTTP session for audio MIME/base64 payloads, model selection, structured JSON response extraction, optional thought-summary extraction, API-key redaction, and invalid JSON handling.
- [ ] Run the focused tests and verify failure.
- [ ] Implement the adapter using the Google Gemini REST API with `gemini-3.5-flash-lite` for one-call-per-voice analysis and summary. Pass raw audio, role metadata, line text, and catalog snapshot in the same request, with an explicit audio-only observation phase before comparison. Normalize age labels into the project enum and retain `evidence`, confidence, raw response, and thought summary separately.
- [ ] Run the focused tests and verify pass, including quota/error classification.

### Task 3: Run resumable analysis stages and publish events

**Files:**
- Modify: `src/storyteller/web/voice_analysis.py`
- Create: `tests/unit/test_voice_analysis_runner.py`

**Interfaces:**
- `VoiceAnalysisManager.submit(job_id) -> None`
- `VoiceAnalysisManager.subscribe(job_ids) -> asyncio.Queue`
- Event types: `ready`, `snapshot`, `progress`, `sample_ready`, `voice_summary_ready`, `suggestion_ready`, `complete`, `failed`, `canceled`.

- [ ] Write failing tests for stage transitions, progress counts, independent sample failures, event payloads containing `job_id`, and continuation after manager restart from the manifest.
- [ ] Run focused tests and verify failure.
- [ ] Implement a bounded worker pool, stage runner, subscription queues, atomic progress updates, retries with quota-aware errors, and shutdown-safe task handling. Use persisted snapshots as the source of truth and make event delivery best-effort.
- [ ] Run focused tests and verify pass.

### Task 4: Add REST routes and independent analysis WebSocket

**Files:**
- Create: `src/storyteller/web/routes_voice_analysis.py`
- Modify: `src/storyteller/web/app.py`
- Test: `tests/unit/test_voice_analysis_routes.py`

**Interfaces:**
- REST routes under `/api/voice-analysis/jobs` as defined in the spec.
- JSON-only WebSocket `/ws/voice-analysis` with `subscribe` messages and snapshot/progress events.

- [ ] Write failing FastAPI tests for create/list/detail/resume/cancel/retry, authentication, invalid job IDs, subscription snapshots, multiple job IDs on one socket, disconnect without cancellation, and absence of PCM/binary messages.
- [ ] Run focused tests and verify failure.
- [ ] Implement routes, authentication reuse, manager registration in app state, one socket multiplexing by `job_id`, and initial snapshot before live events. Do not alter existing `/ws` behavior.
- [ ] Run focused route tests and the existing WebSocket contract tests.

### Task 5: Build analysis list/detail pages with polling and reconnect

**Files:**
- Modify: `web/frontend/src/api.ts`
- Modify: `web/frontend/src/types.ts`
- Modify: `web/frontend/src/router.ts`
- Modify: `web/frontend/src/App.vue`
- Create: `web/frontend/src/views/VoiceAnalysisListView.vue`
- Create: `web/frontend/src/views/VoiceAnalysisDetailView.vue`
- Create: `web/frontend/src/composables/useVoiceAnalysis.ts`
- Test: `web/frontend/src/views/voiceAnalysis.test.ts`

**Interfaces:**
- `api.voiceAnalysisJobs()`, `api.createVoiceAnalysisJob()`, `api.voiceAnalysisJob(id)`, and control methods.
- `useVoiceAnalysis(jobId)` loads REST snapshot, connects to `/ws/voice-analysis`, handles progress events, and falls back to polling on disconnect.

- [ ] Write failing Vitest tests for list polling while jobs are active, stopping polling for terminal jobs, detail snapshot-before-WebSocket behavior, reconnect fallback, and rendering success/failure counts.
- [ ] Run `npm test -- --run src/views/voiceAnalysis.test.ts` and verify failure.
- [ ] Implement the list route with a 3-second active-job poll and the detail route with snapshot loading plus dedicated JSON WebSocket. Add navigation without touching the story audio page.
- [ ] Run focused frontend tests, then `npm test -- --run` and `npm run build`.

### Task 6: Add suggestion approval workflow and verification

**Files:**
- Modify: `src/storyteller/web/voice_analysis.py`
- Modify: `src/storyteller/web/routes_voice_analysis.py`
- Modify: `web/frontend/src/views/VoiceAnalysisDetailView.vue`
- Test: `tests/unit/test_voice_analysis_suggestions.py`
- Test: `web/frontend/src/views/voiceAnalysis.test.ts`

- [ ] Write failing tests for suggestion list, approve/reject/edit validation, audit metadata, and ensuring approval targets a catalog record without silently changing unrelated fields.
- [ ] Run focused tests and verify failure.
- [ ] Implement explicit review actions and catalog update preview/approval with a backup or version record. Keep original declaration and analysis snapshot available.
- [ ] Run focused backend and frontend tests.
- [ ] Run full `.venv/bin/pytest -q`, frontend tests/build, `git diff --check`, and a browser-use smoke test against a running local server: create a job, observe list progress, open detail, close/reopen detail, and confirm snapshot plus subsequent progress.

## Plan Review Checklist

- [ ] Confirm no task reuses the audio playback WebSocket.
- [ ] Confirm a closed browser cannot cancel the backend worker.
- [ ] Confirm all result writes are resumable and versioned.
- [ ] Confirm no API key or raw authorization header reaches frontend events/logs.
- [ ] Confirm `voices.json` changes require explicit user approval.
