# Voice Management Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an authenticated voice management page that lists every registered TTS voice, filters by provider/model/gender/age, edits persisted age overrides, and plays existing story line audio clips.

**Architecture:** Add `model` to the shared `VoiceConfig`, populate it from provider catalogs, and make a reusable `VoiceOverrideStore` apply age overrides whenever the registry exposes voices. Add a backend voice catalog service that aggregates registered voices with saved story line audio, expose filtered/paginated APIs, and add a Vue route that edits ages and plays clips without synthesizing new audio.

**Tech Stack:** Python 3.8, FastAPI, pytest, Vue 3, TypeScript, Vitest, existing `ProviderRegistry`, `ProjectManager`, and `FileResponse` audio routes.

**Spec:** `docs/superpowers/specs/2026-09-24-voice-management-design.md`

## Global Constraints

- Keep packaged provider `voices.json` files read-only; persist edits under `<data_dir>/config/voice-overrides.json`.
- Use `provider + model + voice_id` as the voice identity key.
- Use only story-generation line audio for previews; do not include voice-analysis samples.
- Preserve legacy `project.json` files that do not contain `model`.
- All voice-management APIs require the existing login check.
- Age values are limited to `child`, `teen`, `young_adult`, `middle_aged`, and `senior`.
- Audio responses must resolve only registered story line files under the configured project directory.
- Do not add a new runtime dependency; use the existing Python/Vue stack.

## Review Focus

- A voice ID shared by two providers or models must not receive another voice's age override; test this in the override/catalog task.
- A legacy project line without `model` must remain visible without being incorrectly assigned to a different model; test this in the story clip aggregation task.
- A malformed project file or missing line MP3 must not fail the entire voice list; test this in the aggregation task.
- A crafted clip ID/path must not read outside `project_dir`; test this in the audio route task.
- Saving an empty or multi-valued age list must preserve the normalized order and leave the catalog immutable; test this in the API/store task.

### Task 1: Extend voice identity with model metadata

**Files:**
- Modify: `src/storyteller/core/models.py:84-102`
- Modify: `src/storyteller/core/project.py:285-320`
- Modify: `src/storyteller/providers/aliyun/tts.py:452-464`
- Modify: `src/storyteller/providers/volcengine/tts.py:411-424`
- Modify: `src/storyteller/providers/registry.py:get_tts_model`
- Test: `tests/unit/test_models.py`, `tests/unit/test_project.py`, `tests/unit/test_aliyun_tts.py`, `tests/integration/test_volcengine_tts.py`

**Interfaces:**
- `VoiceConfig(..., model: Optional[str] = None)` stores the provider model/resource ID.
- `_voice_to_dict` and `_voice_from_dict` round-trip `model`, while old payloads default it to `None`.
- Provider `list_voices()` returns `VoiceConfig.model` from catalog metadata.
- `ProviderRegistry.get_tts_model(voice)` returns `voice.model` before provider runtime fallback.

- [ ] **Step 1: Write failing tests** for model construction, serialization, provider model mapping, and legacy payloads without `model`.
- [ ] **Step 2: Run the focused tests** with `pytest tests/unit/test_models.py tests/unit/test_project.py tests/unit/test_aliyun_tts.py tests/integration/test_volcengine_tts.py -q`; confirm failures mention missing model values.
- [ ] **Step 3: Add the optional model field and serialization/provider population** without changing other voice fields.
- [ ] **Step 4: Run the focused tests** and confirm they pass, then run `pytest tests/unit/test_registry.py -q`.
- [ ] **Step 5: Commit** with `git add src/storyteller/core/models.py src/storyteller/core/project.py src/storyteller/providers/aliyun/tts.py src/storyteller/providers/volcengine/tts.py src/storyteller/providers/registry.py tests/unit/test_models.py tests/unit/test_project.py tests/unit/test_aliyun_tts.py tests/integration/test_volcengine_tts.py && git commit -m "feat: preserve voice model identity"`.

### Task 2: Add persisted voice age overrides

**Files:**
- Create: `src/storyteller/core/voice_overrides.py`
- Modify: `src/storyteller/providers/registry.py:list_tts_voices`
- Test: `tests/unit/test_voice_overrides.py`, `tests/unit/test_registry.py`

**Interfaces:**
- `voice_key(voice: VoiceConfig) -> str` returns `provider|model|voice_id`, using `unknown` only when model is absent.
- `VoiceOverrideStore(path: Path)` exposes `get_age(key) -> Optional[list[str]]`, `set_age(key, ages) -> list[str]`, and `apply(voices) -> list[VoiceConfig]`.
- `ProviderRegistry` creates/uses the store under `<data_dir>/config/voice-overrides.json` and applies it to `list_tts_voices()` results.

- [ ] **Step 1: Write failing tests** for empty storage, multi-age normalization, duplicate removal, atomic persistence, provider/model isolation, and applying overrides without mutating provider-owned objects.
- [ ] **Step 2: Run `pytest tests/unit/test_voice_overrides.py tests/unit/test_registry.py -q`** and confirm the new store/imports fail.
- [ ] **Step 3: Implement `VoiceOverrideStore`** using `normalize_voice_ages`, JSON load/save, a temporary file in the same directory, and `os.replace`.
- [ ] **Step 4: Wire the store into registry voice listing** so all future matching consumers see the effective age values; preserve old behavior when no override file exists.
- [ ] **Step 5: Run focused tests** and verify packaged `voices.json` files are unchanged.
- [ ] **Step 6: Commit** with `git add src/storyteller/core/voice_overrides.py src/storyteller/providers/registry.py tests/unit/test_voice_overrides.py tests/unit/test_registry.py && git commit -m "feat: persist voice age overrides"`.

### Task 3: Build the story line clip catalog

**Files:**
- Create: `src/storyteller/web/voice_catalog.py`
- Test: `tests/unit/test_voice_catalog_service.py`

**Interfaces:**
- `VoiceClipCatalog(registry, project_manager)` exposes `list_voices()`, `filter_voices(provider=None, model=None, gender=None, age=None, page=1, page_size=50)`, `clips_for_voice(key)`, and `resolve_clip_audio(key, clip_id)`.
- A returned voice record contains `key`, `provider`, `model`, `voice_id`, `name`, `gender`, `age`, `category`, `description`, `clip_count`, and `has_clips`.
- A returned clip contains `clip_id`, `project_id`, `story_title`, `character_name`, `text`, `created_at`, `duration_ms`, and a server-generated audio URL identifier.

- [ ] **Step 1: Write failing tests** for all voices including voices without clips, provider/model/gender/age filters, story line aggregation, descending creation time, malformed project skipping, missing MP3 skipping, and legacy model fallback.
- [ ] **Step 2: Run `pytest tests/unit/test_voice_catalog_service.py -q`** and confirm the service is absent/failing.
- [ ] **Step 3: Implement catalog aggregation** by reading project states through `ProjectManager`, using only `script.lines[*].audio_path` or the safe `audio/<line_id>.mp3` convention, and joining clips by the voice key.
- [ ] **Step 4: Add safe path resolution** that rejects paths outside `project_dir` and uses a stable clip identifier instead of accepting a filesystem path from the client.
- [ ] **Step 5: Run focused tests** and confirm a broken project does not prevent other projects from appearing.
- [ ] **Step 6: Commit** with `git add src/storyteller/web/voice_catalog.py tests/unit/test_voice_catalog_service.py && git commit -m "feat: aggregate story voice clips"`.

### Task 4: Expose authenticated voice-management APIs

**Files:**
- Create: `src/storyteller/web/routes_voices.py`
- Modify: `src/storyteller/web/app.py` to mount the router and initialize the catalog service
- Test: `tests/web/test_voice_management_api.py`

**Interfaces:**
- `GET /api/voices?provider=&model=&gender=&age=&page=1&page_size=50` returns `{voices, page, page_size, total}`.
- `PATCH /api/voices/{voice_key}` accepts `{"age": ["child", "teen"]}` and returns the effective voice record.
- `GET /api/voices/{voice_key}/clips` returns `{clips}`.
- `GET /api/voices/{voice_key}/clips/{clip_id}/audio` returns `FileResponse` with `audio/mpeg`.

- [ ] **Step 1: Write failing API tests** for authentication, all-voice listing, each filter, invalid age values, successful override persistence, unknown voice/key, clips, and safe audio response.
- [ ] **Step 2: Run `pytest tests/web/test_voice_management_api.py -q`** and confirm route failures.
- [ ] **Step 3: Implement the router** with `require_login`, query validation, URL-decoded voice keys, and service calls; return 400 for invalid ages and 404 for unknown voices/clips.
- [ ] **Step 4: Register the service in `create_app`** using the runtime registry, configured `project_dir`, and `data_dir` override path.
- [ ] **Step 5: Run the API tests** and confirm no path traversal or unauthenticated access succeeds.
- [ ] **Step 6: Commit** with `git add src/storyteller/web/routes_voices.py src/storyteller/web/app.py tests/web/test_voice_management_api.py && git commit -m "feat: add voice management APIs"`.

### Task 5: Add frontend types, API client, route, and navigation

**Files:**
- Modify: `web/frontend/src/types.ts`
- Modify: `web/frontend/src/api.ts`
- Modify: `web/frontend/src/router.ts`
- Modify: `web/frontend/src/App.vue`
- Create: `web/frontend/src/views/VoiceManagementView.vue`
- Test: `web/frontend/src/views/VoiceManagementView.test.ts`

**Interfaces:**
- Add `ManagedVoice`, `VoiceClip`, `VoiceListResponse`, and `VoiceClipResponse` TypeScript interfaces matching the API records.
- Add `api.voices(filters)`, `api.updateVoiceAge(key, age)`, and `api.voiceClips(key)` methods.
- Add route `/voices` rendering `VoiceManagementView`.

- [ ] **Step 1: Write failing component tests** for route rendering, loading all voices, filter query construction, and navigation entry.
- [ ] **Step 2: Run `npm test -- --run src/views/VoiceManagementView.test.ts`** and confirm the view/API methods are missing.
- [ ] **Step 3: Add types and API methods** with URL encoding for voice keys and query parameters for filters/page.
- [ ] **Step 4: Add the route and `音色管理` navigation link** without changing existing route guards.
- [ ] **Step 5: Implement the initial view shell** with loading, error, empty, pagination, and filter states.
- [ ] **Step 6: Run the focused Vitest file** and confirm it passes.
- [ ] **Step 7: Commit** with `git add web/frontend/src/types.ts web/frontend/src/api.ts web/frontend/src/router.ts web/frontend/src/App.vue web/frontend/src/views/VoiceManagementView.vue web/frontend/src/views/VoiceManagementView.test.ts && git commit -m "feat: add voice management view"`.

### Task 6: Implement voice cards, age editing, and story clip playback

**Files:**
- Modify: `web/frontend/src/views/VoiceManagementView.vue`
- Modify: `web/frontend/src/styles.css`
- Test: `web/frontend/src/views/VoiceManagementView.test.ts`

**Interfaces:**
- The view keeps filter state, expanded voice key, selected age arrays, clip loading state, and per-voice save/error state locally.
- Saving calls `api.updateVoiceAge(key, selectedAges)` and updates only the matching card.
- Expanding calls `api.voiceClips(key)` and renders each returned clip with an audio source URL.

- [ ] **Step 1: Add failing tests** for provider/model/gender/age display, checkbox multi-select, save success, save failure rollback, no-clip state, clip metadata, and audio source rendering.
- [ ] **Step 2: Run the focused Vitest file** and confirm the new interactions fail.
- [ ] **Step 3: Implement the card layout** with metadata, age checkboxes, save action, clip list, native audio controls, and accessible labels.
- [ ] **Step 4: Add styles** consistent with existing navigation, cards, filter bars, and responsive layouts.
- [ ] **Step 5: Run `npm test -- --run src/views/VoiceManagementView.test.ts`** and confirm all view tests pass.
- [ ] **Step 6: Run `npm run build`** and confirm the generated SPA contains the new route assets.
- [ ] **Step 7: Commit** with `git add web/frontend/src/views/VoiceManagementView.vue web/frontend/src/styles.css web/frontend/src/views/VoiceManagementView.test.ts && git commit -m "feat: edit voice ages and play story clips"`.

### Task 7: Full verification and integration review

**Files:**
- Test only: existing backend and frontend test suites

- [ ] **Step 1: Run backend tests** with `.venv/bin/pytest -q` and record the complete result.
- [ ] **Step 2: Run frontend tests** with `npm test -- --run` from `web/frontend`.
- [ ] **Step 3: Run the frontend production build** with `npm run build` from `web/frontend`.
- [ ] **Step 4: Run `git diff --check` and inspect `git status --short`** for generated or accidental files.
- [ ] **Step 5: Manually verify** one filtered voice, one multi-age save, one voice with a story clip, one voice without a clip, and one unauthenticated API request.
- [ ] **Step 6: Commit any test-only fixes separately** using a message that names the failing behavior; do not squash the task commits.
