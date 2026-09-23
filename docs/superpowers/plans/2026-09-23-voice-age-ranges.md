# 音色多年龄适用范围 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将音色的适用年龄从单值升级为兼容旧数据的数组，并让匹配、provider、CLI、WebSocket、LLM 上下文和前端展示支持年龄范围。

**Architecture:** 保留 `VoiceConfig.age` 字段名，在核心模型构造边界统一规范化为 `list[str]`；角色的 `Character.age` 继续是单值。匹配器使用角色年龄与音色年龄数组的包含关系，provider 只负责提供原始数据，序列化/API/CLI/UI 统一消费规范化后的数组。

**Tech Stack:** Python 3.8 dataclasses、pytest、FastAPI/WebSocket、Vue 3、TypeScript、Vitest、Vite。

**Spec:** `docs/superpowers/specs/2026-09-23-voice-age-ranges-design.md`

## Global Constraints

- 保留音色字段名 `age`；新值统一为数组，角色 `age` 保持单值。
- 旧的字符串年龄必须转换为单元素数组，不能让历史项目加载失败。
- 空数组表示未标注年龄，不得被当作所有年龄都精准匹配。
- 允许的年龄枚举为 `child`, `teen`, `young_adult`, `middle_aged`, `senior`。
- 不引入新的运行时依赖，不实现人工匹配反馈功能。

## Review Focus

- 旧项目 JSON 中的字符串 `voice_config.age` 能否加载并重新保存为数组；测试放在 Task 1。
- 多年龄音色是否能匹配每一个覆盖的角色年龄，同时不会匹配不重叠的年龄；测试放在 Task 2。
- 年龄为空或包含未知值时是否安全降级而不是扩大为全匹配；测试放在 Task 1 和 Task 2。
- LLM 候选上下文是否明确表达多个年龄，避免模型把数组理解成单一年龄；测试放在 Task 2。
- WebSocket、CLI 和前端是否能同时处理数组年龄及历史字符串事件；测试放在 Task 3。

### Task 1: Core VoiceConfig normalization and project persistence

**Files:**
- Modify: `src/storyteller/core/models.py:63-78`
- Modify: `src/storyteller/core/project.py:270-325`
- Test: `tests/unit/test_models.py`
- Test: `tests/unit/test_project.py` or the existing project serialization test file containing `_voice_from_dict` coverage

**Interfaces:**
- Produces `VoiceConfig.age: list[str]` for every newly constructed voice.
- Produces one shared normalizer, for example `normalize_voice_ages(value) -> list[str]`, used by the dataclass and project deserializer.

- [ ] **Step 1: Write failing model tests**

Add tests that construct `VoiceConfig(age=["child", "teen", "teen"])` and expect `age == ["child", "teen"]`; construct `VoiceConfig(age="child")` and expect `age == ["child"]`; construct with `None` and an unknown value and expect an empty/filtered list.

- [ ] **Step 2: Run the focused model tests and verify the expected failure**

Run: `.venv/bin/pytest -q tests/unit/test_models.py`

Expected: FAIL because the current dataclass preserves scalar strings and has no age normalization.

- [ ] **Step 3: Implement the normalizer and dataclass normalization**

Add a shared normalizer near the voice model. It must accept `None`, a string, or a list/tuple; filter values to `_AGE_BANDS` or the model-level equivalent; preserve declaration order; remove duplicates; and return a new list. Use `__post_init__` on `VoiceConfig` so provider-created objects and direct test objects receive the same canonical shape.

- [ ] **Step 4: Update project serialization and deserialization**

Keep `_voice_to_dict` writing `list(vc.age or [])`. Let `_voice_from_dict` pass the raw value to `VoiceConfig` so old scalar values are normalized at the single model boundary. Add round-trip coverage for both old scalar JSON and new array JSON.

- [ ] **Step 5: Run the focused tests and the relevant project tests**

Run: `.venv/bin/pytest -q tests/unit/test_models.py tests/unit/test_project.py`

Expected: PASS, including existing serialization behavior.

### Task 2: Multi-age matching, provider catalogs, and LLM context

**Files:**
- Modify: `src/storyteller/core/voice_matcher.py:45-220, 270-410`
- Modify: `src/storyteller/providers/mock/tts.py:18-58`
- Modify: `src/storyteller/providers/aliyun/tts.py:449-466`
- Modify: `src/storyteller/providers/volcengine/tts.py:409-430`
- Modify: `src/storyteller/providers/openai_compatible/tts.py:60-78`
- Modify: provider catalog data files discovered by `load_voice_catalog()` if they contain age values
- Test: `tests/unit/test_voice_matcher.py`
- Test: provider-specific catalog tests under `tests/unit/` and `tests/integration/`

**Interfaces:**
- Consumes canonical `VoiceConfig.age: list[str]`.
- Produces matching candidates using `character_age in voice.age`.
- Produces LLM candidate text such as `儿童 / 少年` for a multi-age voice.

- [ ] **Step 1: Write failing matcher tests**

Add a test voice with `age=["child", "teen"]` and verify a child role and a teen role can both select it. Add a voice with `age=["young_adult", "middle_aged"]` and verify it is not an exact age candidate for a senior role. Add a test that an empty-age voice remains available only through the existing fallback path, not the age-specific pool. Update existing scalar test fixtures to either use one-element arrays or rely on normalization.

- [ ] **Step 2: Run the matcher tests and verify they fail for the old equality logic**

Run: `.venv/bin/pytest -q tests/unit/test_voice_matcher.py`

Expected: FAIL at assertions involving multi-age candidate eligibility or sorting.

- [ ] **Step 3: Implement age-aware candidate filtering and sorting**

Replace scalar comparisons with membership checks. Keep gender filtering unchanged. Update `_voice_sort_key`, age-distance helpers, and candidate sampling so a multi-age voice gets the minimum distance across its declared age bands. Ensure empty age arrays are treated as unknown rather than as a universal match.

- [ ] **Step 4: Update LLM candidate rendering**

Render normalized ages with the existing Chinese labels joined by `、` or `/`, and retain the current character age as a single requirement. Update the LLM prompt wording to say a voice may cover multiple adjacent age bands.

- [ ] **Step 5: Update provider fixtures and catalog conversion**

Change representative provider catalog records to demonstrate overlapping ranges (for example Mock child/teen). Provider constructors should pass raw age values into `VoiceConfig`; they must not each implement separate conversion logic. Add/adjust tests proving scalar catalog records remain accepted and array records are emitted as arrays.

- [ ] **Step 6: Run matcher and provider tests**

Run: `.venv/bin/pytest -q tests/unit/test_voice_matcher.py tests/unit/test_models.py tests/unit/test_aliyun_tts.py tests/integration/test_volcengine_tts.py`

Expected: PASS.

### Task 3: CLI, WebSocket schema, and frontend age-range display

**Files:**
- Modify: `src/storyteller/cli/main.py:330-385`
- Modify: `src/storyteller/web/streaming.py:78-105`
- Modify: `web/frontend/src/types.ts:1-4`
- Modify: `web/frontend/src/views/HomeView.vue` voice detail formatting
- Modify: `web/frontend/src/views/HomeView.test.ts`
- Modify: `tests/web/test_websocket.py`
- Modify: `tests/e2e/test_cli.py` and/or existing CLI voice-list tests
- Test: `web/frontend/src/views/HomeView.test.ts`

**Interfaces:**
- WebSocket voice payload has `voice.age: string[]` and character payload keeps `age: string | null`.
- Frontend accepts the canonical array and tolerates a legacy scalar event at the rendering boundary if one is received from an older server.

- [ ] **Step 1: Write failing output and UI tests**

Extend the WebSocket test to assert the matched voice age is an array. Extend CLI tests to assert JSON output contains an array and table output joins multiple Chinese labels. Extend the HomeView test fixture with `voice.age: ['child', 'teen']` and assert the popover contains both `儿童` and `少年`.

- [ ] **Step 2: Run the focused output/UI tests and verify failure**

Run: `.venv/bin/pytest -q tests/web/test_websocket.py::test_ws_streams_pcm_and_completes tests/e2e/test_cli.py`; `npm test -- --run src/views/HomeView.test.ts`

Expected: FAIL because the current event/type/UI paths use scalar ages.

- [ ] **Step 3: Update WebSocket serialization**

In `_characters_matched_event`, serialize `voice.age` as a copied list and leave the role-level `character.age` scalar. Preserve provider/model/voice metadata already exposed by the event.

- [ ] **Step 4: Update CLI output**

Keep `_voice_row` JSON-compatible with the list value. Add a helper that maps each age code through `_AGE_CN` and joins them with ` / ` for `_print_voice_table`; do not call scalar dictionary lookup on the list.

- [ ] **Step 5: Update frontend types and rendering**

Change the voice age type to `string[]`. Add a small runtime formatter that accepts an array and, for compatibility, wraps a scalar string before mapping labels. Render the joined labels in the existing voice popover.

- [ ] **Step 6: Run the focused output/UI tests**

Run: `.venv/bin/pytest -q tests/web/test_websocket.py::test_ws_streams_pcm_and_completes tests/e2e/test_cli.py`; `npm test -- --run src/views/HomeView.test.ts`

Expected: PASS.

### Task 4: Full verification and integration checks

**Files:**
- Test: all existing Python test files affected by the age model
- Test: all frontend Vitest files

- [ ] **Step 1: Run the full frontend suite and production build**

Run from `web/frontend`: `npm test -- --run` and `npm run build`.

Expected: all frontend tests pass and Vite produces the static bundle.

- [ ] **Step 2: Run the full backend suite**

Run from the repository root: `.venv/bin/pytest -q`.

Expected: all backend tests pass. If an unrelated known flaky test fails, record its exact test name and failure rather than masking it.

- [ ] **Step 3: Run repository hygiene checks**

Run: `git diff --check` and `git status --short`.

Expected: no whitespace errors; only intended source, test, and documentation files are changed.

- [ ] **Step 4: Review serialized compatibility manually**

Inspect one legacy project fixture with scalar `voice_config.age` and one current generated event with array age. Confirm loading, matching, WebSocket encoding, CLI output, and frontend rendering all use the intended shape.

