# LLM Opening Streaming TTS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Web 故事生成改造成 opening、start_notice 和正式 line 共用统一的双向流式 TTS 编排，同时保留按 Provider/模型限流的普通 TTS 降级能力。

**Architecture:** 在现有 `TTSProvider` 之上增加 `StreamingTTSSession` 和 `StreamingTTSProvider`，由 `TTSScheduler` 按 `(provider, model)` 管理会话并提供有界队列。`StreamOrchestrator` 负责把 partialjson 产生的 opening/line 文本增量提交给会话，把已生成的音频按 `opening → start_notice → line_id` 顺序推送到现有 WebSocket；Provider 适配器只负责协议和 PCM 转换。

**Tech Stack:** Python 3.8+, FastAPI WebSocket, `partialjson`, asyncio/threading-compatible queues, requests, DashScope SDK（延迟导入）, Volcengine WebSocket 客户端, Vitest/TypeScript frontend tests, pytest。

**Spec:** `docs/superpowers/specs/2026-09-14-llm-opening-streaming-tts-design.md`

## Global Constraints

- `opening` 是等待期 filler，不属于 `lines`，不进入最终 `story.mp3`。
- `start_notice` 是固定开播提示，位于 opening 与正式 line 之间。
- opening 未生成或 opening TTS 失败不得让正式 line 整体退回普通逐行 TTS。
- 正式 line 只有在角色/音色确定后才提交 TTS 文本增量，不等待完整 line。
- 一个 TTS Provider 会话固定 Provider、模型、音色和音频参数；不同音色不得在同一会话中切换。
- WebSocket 音频标准保持 PCM s16le、mono、24000Hz。
- 每个 `(provider, model)` 使用独立 FIFO 队列和并发上限；队列满时对上游文本消费施加背压。
- API Key、签名 URL 和敏感请求头不得写入日志。
- 现有 HTTP Chunked/非实时 TTS 实现保留为降级路径，CLI 默认行为不改变。

## File Map

- Create `src/storyteller/core/streaming_tts.py`: Provider 无关的会话协议、事件和错误类型。
- Create `src/storyteller/web/tts_scheduler.py`: `(provider, model)` 维度的队列、并发槽位、速率限制和背压。
- Modify `src/storyteller/core/story_generator.py`: 增加 `opening` preview 字段、opening delta 回调和 prompt 规则。
- Modify `src/storyteller/providers/registry.py`: 注册和获取实时 TTS 能力及模型标识。
- Modify `src/storyteller/providers/volcengine/tts.py`: 增加双向 WebSocket session，保留 HTTP Chunked。
- Modify `src/storyteller/providers/aliyun/tts.py`: 增加 DashScope realtime session，保留 HTTP 实现。
- Modify `src/storyteller/providers/mock/tts.py`: 增加可控的实时 mock session。
- Modify `src/storyteller/web/streaming.py`: 替换 thinking/intro 主流程，接入 opening、start_notice、line delta、有序音频缓冲和降级。
- Modify `src/storyteller/web/fillers.py`: 移除旧 thinking LLM filler 主路径，仅保留固定 start_notice/cache 兼容能力。
- Modify `src/storyteller/core/config.py` and provider bootstrap/config tests: 增加调度器默认值和 Provider/模型覆盖配置。
- Modify `web/frontend/src/stores/player.ts`, `types.ts`, and related view tests: 识别 opening/start_notice 事件并维持有序 PCM 播放状态。
- Create or modify unit/integration/web tests listed in each task below。

### Task 1: Extend script streaming with opening deltas

**Files:**
- Modify: `src/storyteller/core/story_generator.py`
- Test: `tests/unit/test_story_generator.py`

**Interfaces:**
- Add `on_opening_delta: Optional[Callable[[str], None]]` to `generate_script_stream` (the project supports Python 3.8).
- Keep `on_preview` behavior unchanged for UI snapshots.
- Extend preview snapshots with `opening` while keeping final `Script` free of the temporary opening field.

- [ ] **Step 1: Write failing tests**

Add tests that feed chunks such as `{"title":"T","opening":"夜幕` and `降临","characters":[],"lines":[]}` and assert callbacks receive only `夜幕` then `降临`; repeated partialjson snapshots do not repeat text; a rewritten already-sent prefix reports an opening protocol error without changing the returned final script contract.

- [ ] **Step 2: Run the focused tests**

Run: `pytest tests/unit/test_story_generator.py -q`

Expected: the new callback/preview assertions fail before implementation.

- [ ] **Step 3: Implement minimal opening extraction**

Track `last_opening_text` separately from `last_preview`; after each `JSONParser` snapshot, validate that the current opening is a strict prefix extension, invoke the callback only with the suffix, and expose `opening` only in the preview dictionary. Keep `_script_from_json()` ignoring the temporary field.

- [ ] **Step 4: Update prompt and run tests**

Add the ordered `title → opening → characters → lines` instruction and the 15–35 Chinese-character constraints to the system prompt. Run: `pytest tests/unit/test_story_generator.py -q`.

Expected: PASS.

- [ ] **Step 5: Commit the isolated change**

Run: `git add src/storyteller/core/story_generator.py tests/unit/test_story_generator.py && git commit -m "feat: expose streaming story opening deltas"`

### Task 2: Add provider-independent streaming session contracts

**Files:**
- Create: `src/storyteller/core/streaming_tts.py`
- Modify: `src/storyteller/providers/registry.py`
- Modify: `src/storyteller/providers/mock/tts.py`
- Test: `tests/unit/test_streaming_contract.py`

**Interfaces:**
- `StreamingTTSSession.send_text(text: str) -> None`.
- `StreamingTTSSession.iter_audio() -> Iterator[StreamChunk]`.
- `StreamingTTSSession.finish() -> None` and `.cancel() -> None`.
- `StreamingTTSProvider.supports_text_streaming: bool` and `open_stream(voice, *, directives=None, context=None) -> StreamingTTSSession`.
- `ProviderRegistry.get_streaming_tts(name) -> StreamingTTSProvider | None`.

- [ ] **Step 1: Write failing contract tests**

Test that a mock session accepts multiple `send_text` calls, emits audio while text is still being submitted, requires `finish()` to close the stream, and that a provider without `open_stream` returns `None` from the registry.

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest tests/unit/test_streaming_contract.py -q`.

- [ ] **Step 3: Implement the contracts and mock session**

Use a bounded thread-safe queue for mock audio events, preserve `StreamChunk` and the existing 24kHz PCM contract, and translate session failures to `TTSError`.

- [ ] **Step 4: Run focused and existing provider tests**

Run: `pytest tests/unit/test_streaming_contract.py tests/unit/test_provider_abstractions.py tests/unit/test_registry.py -q`.

Expected: PASS without changing old `stream_synthesize` behavior.

- [ ] **Step 5: Commit**

Run: `git add src/storyteller/core/streaming_tts.py src/storyteller/providers/registry.py src/storyteller/providers/mock/tts.py tests/unit/test_streaming_contract.py && git commit -m "feat: add provider-independent streaming tts sessions"`

### Task 3: Implement the TTS scheduler and configuration

**Files:**
- Create: `src/storyteller/web/tts_scheduler.py`
- Modify: `src/storyteller/core/config.py`
- Modify: `src/storyteller/providers/registry.py`
- Test: `tests/unit/test_tts_scheduler.py`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- `SchedulerLimits(max_concurrent_sessions: int, max_text_chunks_per_second: Optional[float], queue_size: int, queue_timeout_seconds: float)`.
- `TTSScheduler.open(provider, model, voice, *, directives=None, context=None) -> ScheduledTTSSession`.
- `ScheduledTTSSession.send_text`, `iter_audio`, `finish`, `cancel`.
- Configuration paths: `tts.scheduler.default_max_concurrent_sessions`, `tts.scheduler.default_max_text_chunks_per_second`, `tts.scheduler.default_queue_size`, `tts.scheduler.default_queue_timeout_seconds`, and `tts.scheduler.limits.<provider>.<model>.*`.

- [ ] **Step 1: Write failing scheduler tests**

Use deterministic fake sessions to verify same `(provider, model)` cannot exceed the configured active count, different models do not block each other, FIFO order is preserved, queue timeout raises a typed scheduler error, and the text rate limiter delays submissions without dropping text.

- [ ] **Step 2: Run focused tests and observe failure**

Run: `pytest tests/unit/test_tts_scheduler.py tests/unit/test_config.py -q`.

- [ ] **Step 3: Implement scheduler primitives**

Create one queue/worker group per `(provider, model)`, acquire a semaphore before opening a provider session, use bounded text queues for backpressure, release the slot on finish/cancel/failure, and emit structured scheduler log events without text contents or credentials.

- [ ] **Step 4: Add config parsing and registry model lookup**

Read defaults from `Config`, resolve Provider catalog/model values for a `VoiceConfig`, and retain safe defaults when the configuration is absent.

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_tts_scheduler.py tests/unit/test_config.py tests/unit/test_registry.py -q`.

Expected: PASS.

- [ ] **Step 6: Commit**

Run: `git add src/storyteller/web/tts_scheduler.py src/storyteller/core/config.py src/storyteller/providers/registry.py tests/unit/test_tts_scheduler.py tests/unit/test_config.py && git commit -m "feat: add per-provider tts scheduling limits"`

### Task 4: Add Volcengine and Aliyun realtime adapters

**Files:**
- Modify: `src/storyteller/providers/volcengine/tts.py`
- Modify: `src/storyteller/providers/aliyun/tts.py`
- Test: `tests/integration/test_volcengine_tts.py`
- Test: `tests/unit/test_aliyun_tts.py`
- Test: `tests/unit/test_streaming_contract.py`

**Interfaces:**
- `VolcengineTTS.open_stream(...)` implements StartSession/TaskRequest/FinishSession and converts binary audio frames to standard `StreamChunk` values.
- `AliyunTTS.open_stream(...)` lazily imports `dashscope.audio.tts_v2.SpeechSynthesizer`, maps `streaming_call`/`streaming_complete`, and resamples 22.05kHz PCM to 24kHz.
- Existing `synthesize` and Volcengine HTTP `stream_synthesize` remain unchanged as fallback paths.

- [ ] **Step 1: Add protocol-level failing tests with fake transports**

Assert Volcengine emits the exact session/task/finish command order and surfaces server errors; assert Aliyun forwards every text chunk, waits for completion, forwards callback audio, and performs the 22.05kHz-to-24kHz conversion.

- [ ] **Step 2: Run focused tests**

Run: `pytest tests/integration/test_volcengine_tts.py tests/unit/test_aliyun_tts.py tests/unit/test_streaming_contract.py -q`.

- [ ] **Step 3: Implement Volcengine adapter**

Keep network construction isolated behind an injectable transport so unit tests do not require credentials or live access. Ensure `finish()` waits for `SessionFinished` and `cancel()` closes the socket.

- [ ] **Step 4: Implement Aliyun adapter**

Keep SDK import and client creation lazy; bridge callback bytes through a bounded queue and translate SDK errors to `TTSError` without logging API keys.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/integration/test_volcengine_tts.py tests/unit/test_aliyun_tts.py tests/unit/test_streaming_contract.py -q`.

Commit: `git add src/storyteller/providers/volcengine/tts.py src/storyteller/providers/aliyun/tts.py tests/integration/test_volcengine_tts.py tests/unit/test_aliyun_tts.py tests/unit/test_streaming_contract.py && git commit -m "feat: add realtime tts provider adapters"`

### Task 5: Replace filler orchestration with opening and start_notice

**Files:**
- Modify: `src/storyteller/web/fillers.py`
- Modify: `src/storyteller/web/streaming.py`
- Test: `tests/unit/test_web_jobs.py`
- Test: `tests/web/test_websocket.py`

**Interfaces:**
- `StreamOrchestrator` owns one scheduler per job and an ordered audio publisher.
- Opening callback receives text deltas from `StoryGenerator` and submits them immediately after the fixed host voice is selected.
- Events become `opening_text_delta`, `opening_audio_start/end/abort`, `start_notice`, `line_start`, `line_text_delta`, `line_end`, and `warning`; old `thinking` events are no longer emitted on the main path.

- [ ] **Step 1: Write failing mock WebSocket tests**

Assert event/audio order is `ready → script_preview(opening) → opening audio → start_notice → line audio → complete`; opening is absent from `script_ready` and final audio; missing/opening failure still reaches formal lines; line text deltas are not sent before role voice assignment.

- [ ] **Step 2: Run focused tests**

Run: `pytest tests/unit/test_web_jobs.py tests/web/test_websocket.py -q`.

- [ ] **Step 3: Implement opening lifecycle**

Remove the old extra LLM thinking generation from the primary path. Select the configured/fallback filler voice at task start, create the scheduled opening session on its first delta, consume audio concurrently, and use a preset/skip fallback without stopping the script or voice matching.

- [ ] **Step 4: Implement start_notice sequencing**

Retain the fixed text/cache, submit it through the scheduler using the host voice, and publish it only after opening has ended/been skipped and formal voice matching has completed.

- [ ] **Step 5: Implement ordered audio publishing and formal line sessions**

Create per-line bounded buffers keyed by line index. Allow line sessions to generate early, but publish binary frames only after opening and start_notice and only in line order. Submit each partialjson line text suffix to the assigned session; call `finish()` once the line closes; use the existing full-text TTS path only for unsupported/failed sessions.

- [ ] **Step 6: Preserve project artifacts and sound mixing**

Keep opening/start_notice outside `line_paths` and final mixing. Preserve existing sound-cue behavior by using the complete-line fallback whenever a line requires post-TTS cue mixing, unless a later implementation proves incremental mixing safe.

- [ ] **Step 7: Run WebSocket and regression tests**

Run: `pytest tests/unit/test_web_jobs.py tests/web/test_websocket.py tests/e2e/test_full_flow.py -q`.

- [ ] **Step 8: Commit**

Run: `git add src/storyteller/web/fillers.py src/storyteller/web/streaming.py tests/unit/test_web_jobs.py tests/web/test_websocket.py && git commit -m "feat: stream opening and ordered story tts"`

### Task 6: Update frontend event handling and playback state

**Files:**
- Modify: `web/frontend/src/types.ts`
- Modify: `web/frontend/src/stores/player.ts`
- Modify: affected story view components only where old `thinking`/`intro` labels are rendered.
- Test: `web/frontend/src/stores/player.test.ts`

**Interfaces:**
- Add typed event shapes for opening/start_notice/line text deltas while accepting the existing `ready`, `script_preview`, `script_ready`, `line_start`, `line_end`, `complete`, `warning`, and `error` events.
- Keep binary PCM handling unchanged; backend order is authoritative and the player may maintain a small playback buffer.

- [ ] **Step 1: Write failing store tests**

Feed opening and start_notice events plus binary frames into a fake WebSocket and assert the UI phase/message, filler text, line preview, warning state, and final URL are correct; assert old `thinking` labels are not required for completion.

- [ ] **Step 2: Run frontend tests and confirm failure**

Run: `npm --prefix web/frontend test -- --run`.

- [ ] **Step 3: Implement typed event/state handling**

Handle opening text incrementally, clear the filler only on opening end/abort, show start notice as the fixed pre-story state, and keep line index/duration updates compatible with the current audio timeline.

- [ ] **Step 4: Run frontend tests and build**

Run: `npm --prefix web/frontend test -- --run && npm --prefix web/frontend run build`.

Expected: PASS and a successful production build.

- [ ] **Step 5: Commit**

Run: `git add web/frontend/src/types.ts web/frontend/src/stores/player.ts web/frontend/src/views web/frontend/src/stores/player.test.ts && git commit -m "feat: handle opening and ordered streaming events"`

### Task 7: End-to-end verification and operational documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-09-14-llm-opening-streaming-tts-design.md` only if implementation details require a confirmed correction.
- Modify: `README.md` or `docs/deployment-docker.md` for scheduler configuration and realtime SDK requirements.
- Test: `tests/e2e/test_full_flow.py`, `tests/web/test_websocket.py`, all relevant unit tests.

- [ ] **Step 1: Run the complete backend suite**

Run: `pytest -q`.

- [ ] **Step 2: Run the complete frontend suite/build**

Run: `npm --prefix web/frontend test -- --run && npm --prefix web/frontend run build`.

- [ ] **Step 3: Run a mock WebSocket timing scenario**

Verify that line audio can finish generation before `start_notice` but cannot be pushed before it, and that a slow provider queue produces backpressure rather than unbounded memory growth.

- [ ] **Step 4: Run live provider smoke tests only with configured credentials**

Verify one opening and one multi-delta line against each configured realtime Provider; record first-audio latency, total time, queue wait, fallback count, and final PCM properties without logging credentials.

- [ ] **Step 5: Review logs and failure messages**

Confirm business events include `job_id`, `project_id`, phase, provider, model, voice_id, line_id where applicable, queue wait and duration; confirm API keys and signed URLs are absent.

- [ ] **Step 6: Commit documentation and closeout**

Run: `git add README.md docs/deployment-docker.md docs/superpowers/specs/2026-09-14-llm-opening-streaming-tts-design.md && git commit -m "docs: describe streaming tts scheduler configuration"`

## Self-Review Checklist

- Spec sections 3–4 are covered by Tasks 1, 5 and 6.
- Provider session boundaries, both realtime adapters, PCM conversion and fallback are covered by Tasks 2 and 4.
- Per-provider/model queue limits, QPS control and backpressure are covered by Task 3 and exercised again in Task 7.
- Opening/start_notice/line WebSocket ordering and exclusion from final audio are covered by Task 5 and the WebSocket tests.
- No task changes CLI behavior or removes existing non-realtime provider implementations.
- The plan contains no API key values, no unbounded queue, and no requirement to store opening in the formal script.
