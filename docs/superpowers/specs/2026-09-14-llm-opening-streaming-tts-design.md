# LLM 故事开场白流式 TTS 设计

- 日期：2026-09-14
- 状态：待评审
- 范围：在现有 Web 流式故事生成基础上，让 LLM 生成的正式故事开场白尽早进入 TTS，并支持 Provider 无关的文本增量输入与音频增量输出。

## 1. 背景与问题

当前 Web 生成流程已经支持剧本流式预览，但正式故事音频仍在完整剧本生成、音色匹配完成后才开始逐行合成。当前等待期间有独立的 `thinking` 和固定 `start_notice` 开播提示语。新方案中的 `opening` 是原 `thinking` 功能的替代物：它是等待期间播放的独立语音，不是正式剧本正文。`start_notice` 保留，用于提示正式故事即将开始。

当前线上 TTS 能力如下：

| Provider | 当前实现 | 输入 | 输出 |
| --- | --- | --- | --- |
| 火山引擎 | HTTP Chunked 单向流式 | 完整文本 | 音频分块 |
| 阿里云 | HTTP 非实时 | 完整文本 | 完整音频文件 |

两家接口的实时能力已经完成最小真实调用验证：阿里云 Qwen-Audio-TTS Plus 和火山引擎双向 WebSocket 均支持一次提交文本并流式返回音频；两者也都支持在同一个会话中追加文本。

本次设计的目标不是把业务绑定到某一家 Provider，而是把“最早可用的故事文本”接入统一的 TTS 流式会话。

## 2. 目标与非目标

### 2.1 目标

1. LLM 在剧本流中优先生成一段等待期间播放的故事开场白 `opening`，替代原来的 `thinking` 口播。
2. `opening` 在 `partialjson` 解析出新增文本后，立即使用任务启动时确定的主持人音色进入 TTS；不等待正式角色音色匹配。
3. 根据实际匹配到的音色，自动选择对应 Provider 的流式 TTS 会话。
4. 阿里云、火山引擎和未来 Provider 对上层暴露统一的 `send_text()` / `finish()` 能力。
5. 开场白音频与后续正文音频在浏览器端使用同一 PCM 音频线缆标准播放。
6. Provider 不支持实时文本输入时，自动降级为完整句子合成，不影响故事生成。
7. `opening` 只属于等待期填充语音，不写入正式剧本的 `lines`，也不进入最终 `story.mp3`。
8. 对不同 Provider、不同模型分别限制并行 TTS 会话数量，并通过队列避免触发 Provider 的并发/QPS 限制。

### 2.2 非目标

1. 不把 LLM 隐藏思考过程转换为语音。
2. 不要求每个 LLM token 都直接发送给 TTS。
3. 不改变 CLI 的默认生成行为。
4. 不要求不同角色共用同一个 TTS 会话。
5. 不在本阶段实现直播 seek、音频回放缓存或多用户会话复用。

## 3. 用户可见行为

目标事件顺序如下：

```text
开始任务
  ↓
确定 opening 使用的主持人音色
  ↓
LLM 先流式输出 title / opening，再继续输出 characters / lines
  ↓
partialjson 解析到 opening 的新增文本片段
  ↓
立即把 opening 文本 delta 发送给 TTS
  ↓
opening 音频流式播放
  ↓
角色信息完成后开始正式角色音色匹配
  ↓
正式音色匹配完成后，等待 opening 音频结束并播放 start_notice
  ↓
每个 line 的角色和音色确定后，文本 delta 进入对应 TTS 会话
  ↓
音频帧按 opening → start_notice → line 顺序推送到前端 WebSocket
```

`opening` 的含义和要求：

- 它是原 `thinking` 口播的替代内容，是等待期独立播放的故事开场白；
- 它不是正式剧本正文，不要求出现在 `lines[0]`，也不要求写入最终故事音频；
- 模型应将它生成成完整、有画面感、适合等待期播放的开场句，建议 15～35 个汉字；
- TTS 不等待开场句完整；任务启动时确定主持人音色后，先发送已经产生的文本，再把后续新增文本按 delta 持续发送；
- opening 只出现在等待期口播事件和对应音频中；
- 不得出现“正在生成”“让我想一想”等旧式等待提示文本。

`thinking` 和 `start_notice` 的处理：

- 新方案不再单独生成原来的 `thinking` 语音，`opening` 取代它；
- `start_notice` 保留为 opening 之后、正式角色音色匹配完成且正式故事第一句之前的独立固定开播提示语，使用 opening 的主持人音色并通过同一套 Provider 能力合成或读取缓存音频；
- opening 尚未产生时只展示文本状态，不再额外调用一次 LLM 生成旧式 thinking 文本；
- opening 尚未产生或 opening 实时 TTS 失败时，不阻塞正式剧本流程；可使用预设 opening 或跳过 opening，随后继续播放 `start_notice`。正式台词仍按角色音色和文本增量进入双向流式 TTS；只有对应 Provider 不支持实时输入或正式实时会话失败时，才对对应音频任务降级为普通 TTS。

## 4. LLM 流式剧本协议

### 4.1 结构

LLM 流式输出协议增加临时的 `opening` 字段：

```json
{
  "title": "故事标题",
  "opening": "夜幕降临，四只小猫发现积木城亮起了红色警报！",
  "characters": [],
  "lines": []
}
```

`opening` 与 `lines` 没有包含关系。它是等待期独立口播字段，不参与正式剧本行的去重、字幕、逐行音频或最终故事音频。项目最终保存的正式剧本 JSON 不保存该临时字段，或者将其放入单独的运行元数据而不作为故事正文。

### 4.2 partialjson 处理规则

后端持续解析 LLM 增量输出。只要 `partialjson` 能够读出 opening 字符串的新增前缀，就触发 `opening_text_delta`，不等待字段闭合、句末标点或“内容稳定”：

1. `opening` 字段存在；
2. `partialjson` 能够返回当前已经解析出的字符串前缀；
3. 当前值比上一次已发送值更长，且旧值是新值的前缀；
4. 新增部分经过 JSON 转义还原后非空。

每次只发送新增 delta。partialjson 重复解析出相同内容时不得重复推送；如果模型改写了已经发送的前缀，不能回撤已发送音频，应记录协议异常并停止 opening 实时会话，随后使用预设 opening 或跳过 opening。该异常不应导致正式台词整体退回普通逐行 TTS。字段闭合后，只校验 opening 自身是否满足长度和内容要求。

### 4.3 Prompt 要求

剧本提示词需要明确：

> 按以下顺序生成：标题、等待期故事开场白、角色信息、正文台词。优先尽快输出等待期故事开场白；它用于在正式角色音色匹配期间播放，控制在 15～35 个汉字以内，不属于正文台词，也不会进入最终故事音频。生成过程中允许系统按已经产生的文字增量合成语音，因此不要改写已经输出的开头。

模型可以继续流式生成正文，但 `opening` 不得被后续内容重新改写。如果模型没有输出 opening，后端不额外生成旧式 thinking filler；可以使用预设 opening 或跳过 opening，随后继续执行 `start_notice` 和正式台词的双向流式 TTS。

## 5. Provider 无关的 TTS 会话

### 5.1 新的抽象

在现有 `TTSProvider` 之外增加面向 Web 的会话抽象：

```python
class StreamingTTSSession(Protocol):
    def send_text(self, text: str) -> None: ...
    def iter_audio(self) -> Iterator[StreamChunk]: ...
    def finish(self) -> None: ...
    def cancel(self) -> None: ...

class StreamingTTSProvider(TTSProvider):
    supports_text_streaming: bool

    def open_stream(self, voice, *, directives=None, context=None) -> StreamingTTSSession: ...
```

上层只依赖 `open_stream()`、`send_text()`、`finish()` 和音频块迭代，不出现 `aliyun`、`volcengine` 等 Provider 名称。会话必须支持发送文本和接收音频并发进行：`send_text()` 不能等待整段音频完成，音频消费也不能阻塞后续文本发送。

### 5.2 会话边界

- 一个会话固定一个 Provider、模型和音色；
- 不同角色或不同音色不得复用同一个会话；
- `opening` 是等待期主持人口播，因此使用预先选定的主持人/旁白音色会话；
- 角色台词仍按角色音色分别建立会话或按行处理；
- 会话结束必须显式调用 `finish()`，确保尾部文本被合成；
- Provider 报错时立即关闭会话，并根据能力降级到普通 `synthesize()`。

### 5.3 火山引擎适配

新增双向 WebSocket Provider 能力：

- 连接 `wss://openspeech.bytedance.com/api/v3/tts/bidirection`；
- `StartSession` 固定模型、speaker、音频格式；
- 每次 `send_text()` 对应一个 `TaskRequest`；
- `TTSResponse` 二进制音频直接转为标准 PCM；
- `finish()` 发送 `FinishSession` 并等待 `SessionFinished`；
- 连接级事件和错误转换为统一 Provider 事件。

现有 HTTP Chunked 单向实现保留，作为旧配置和降级路径，不被删除。

### 5.4 阿里云适配

新增 DashScope Qwen-Audio-TTS 实时 WebSocket Provider 能力：

- 延迟导入 `dashscope.audio.tts_v2.SpeechSynthesizer`；
- 通过回调接收 `on_data(bytes)`，用队列桥接到统一音频迭代器；
- `send_text()` 调用 `streaming_call(text)`；
- `finish()` 调用 `streaming_complete()`；
- 原生 22.05kHz PCM 在适配层重采样到 24kHz；
- 只有配置实时 WebSocket endpoint 且 SDK 可用时才启用该能力；
- 当前 HTTP 非实时实现保留为默认降级路径。

### 5.5 统一音频线缆

浏览器 WebSocket 音频线缆保持现有标准：

```text
PCM s16le / mono / 24000Hz
```

Provider 的原生采样率、MP3/PCM 差异和 WebSocket 帧格式全部隐藏在适配层。前端不根据 Provider 或行类型切换解码器。

### 5.6 TTS 调度器

Provider 适配器之上增加统一的 `TTSScheduler`，以 `(provider, model)` 作为资源隔离键：

- 每个 `(provider, model)` 拥有独立的 FIFO 等待队列；
- 每个队列配置独立的 `max_concurrent_sessions`，限制同时运行的 TTS 会话数；
- opening、start_notice 和正式 line 的 TTS 请求都必须经过调度器，不能绕过队列直接建立会话；
- 会话获得配额后一直占用一个并行槽位，直到 `finish()`、`cancel()` 或失败释放；
- 队列等待期间，文本 delta 进入有界缓冲；达到上限后暂停上游文本消费，形成背压；
- 可选配置 `max_text_chunks_per_second`，限制同一 `(provider, model)` 的文本提交频率，避免单纯控制并发仍触发 QPS；
- Provider 返回限流错误时，调度器按退避策略重试或转入普通 TTS 降级，不让其他 Provider 的队列被阻塞；
- 不同 Provider 或不同模型之间互不占用并行额度。

调度配置建议支持全局默认值和 Provider/模型覆盖值，例如：

```text
tts.scheduler.default_max_concurrent_sessions
tts.scheduler.default_max_text_chunks_per_second
tts.scheduler.limits.<provider>.<model>.max_concurrent_sessions
tts.scheduler.limits.<provider>.<model>.max_text_chunks_per_second
```

## 6. 编排流程

### 6.1 后端阶段

1. 创建任务并发送 `ready`。
2. 启动 LLM 剧本流，不再单独启动原来的 thinking filler 语音。
3. partialjson 解析出 opening 的新增 delta 后，发送 `script_preview` 更新并缓存文本。
4. 任务启动时先确定 opening 使用的主持人/旁白音色；opening 的第一个 delta 到达后向 `TTSScheduler` 提交会话请求。
5. 会话获得对应 `(provider, model)` 配额后，每次解析到 opening 新增 delta，就调用 `send_text(delta)`；音频块立即推送到浏览器，同时累积为等待期 filler 音频缓存，不写入正式故事项目。
6. 当角色集合完整后，立即启动 VoiceMatcher，不等待所有 lines 生成完成；该过程与 opening TTS 并行。
7. opening 文本发送完成后调用 `finish()`，等待 opening 尾部音频；正式音色匹配完成后，确保 `start_notice` 排在 opening 音频之后进入播放队列。
8. 正式音色匹配完成后，只要任一 line 的 `line_id`、`character_id`/旁白标识和对应正式音色确定，就立即向 `TTSScheduler` 提交该 line 的 TTS 会话，不必等待 `start_notice` 播放。
9. 该 line 的文本通过 partialjson 持续解析；每次获得新增文本 delta，就按短语或小块调用 `send_text(delta)`，不等待完整 line，也不要求等待完整句子。
10. line 音频可以在 opening 或 `start_notice` 播放期间提前生成，但必须按 `opening → start_notice → line_id` 的顺序推送到前端 WebSocket；后续 line 音频不能越过前一个 line。前端收到后再自行进入播放缓冲队列。
11. 后端需要同时限制 TTS 调度队列和有序音频缓冲区的大小；任一缓冲达到上限时都要对文本消费施加背压，避免长时间等待造成无限缓存。
12. 每个 line 的文本发送完成后调用对应会话的 `finish()`，等待该 line 的尾部音频。
13. 生成并保存逐行 MP3、最终 `story.mp3`，发送 `complete`。

### 6.2 与现有逐行流程的兼容

opening 和正式 line 都使用文本 delta 驱动实时 TTS；opening 使用任务启动时确定的主持人音色，正式 line 使用 VoiceMatcher 完成后的角色音色。

opening 通过实时会话生成的音频只属于等待期 filler，不影响后续正式剧本逐行 TTS。每个 line 的实时会话只合成该 line 已发送的文本 delta，不得重复合成。需要分别记录 opening 和 line 的发送状态：

```json
{
  "opening_tts": {
    "mode": "streaming_session",
    "provider": "...",
    "text_sent_length": 24,
    "included_in_story": false
  },
  "line_tts": {
    "line_id": "1",
    "text_sent_length": 18,
    "included_in_story": true
  }
}
```

## 7. 失败与降级

### 7.1 opening 失败

- partialjson 始终无法得到 opening：发送 warning，使用预设 opening 或跳过 opening，不阻塞正式剧本生成和音色匹配；
- opening TTS 失败：发送 warning，停止 opening 实时会话，使用预设 opening 或跳过 opening；正式台词仍继续使用双向流式 TTS；
- opening 音色匹配失败：使用任务开始时选定的主持人/旁白音色，不阻塞完整故事生成；
- opening 已发送的前缀发生变化：不能回撤音频，记录协议异常并停止 opening 实时会话，使用预设 opening 或跳过 opening；正式台词不因此整体降级；

### 7.2 实时 Provider 失败

- 建连失败：记录 Provider、模型、音色、会话阶段和错误码，不记录 API Key；
- 首段发送失败：当前句回退普通 `synthesize()`；
- 会话中途失败：保存已收到的 PCM，当前行改走普通接口，后续文本重新按行处理；
- `finish()` 超时：标记当前会话异常，保留已生成音频并继续宽松模式；
- 阿里云免费额度、模型配额或实时 endpoint 不可用时，自动回退现有 HTTP 实现。
- 调度队列等待超时：记录队列等待时长，当前 line 使用普通 TTS 或跳过并发送 warning，不能无限等待。

### 7.3 播放一致性

`opening_text_delta`、`line_start` 必须由前端时间轴明确区分：

- opening 音频属于等待期 filler，不计入正式故事字幕、行时长和最终音频；
- opening 已发送的 PCM 不回放补发；
- opening 尚未产生时只更新状态，不产生独立 thinking filler 音频。

## 8. 日志与可观测性

新增业务层日志事件：

```text
opening_text_delta
opening_voice_ready
tts_session_started
tts_session_queued
tts_queue_wait_finished
tts_text_chunk_sent
tts_first_audio_received
tts_session_finished
tts_session_fallback
```

每条日志至少包含：`job_id`、`project_id`、`phase`、`provider`、`model`、`voice_id`、`line_id`、`text_length`、`duration_ms`。日志不得记录完整 API Key、签名 URL 或完整敏感请求头。

重点指标：

- `opening_detected_at - job_started_at`
- `first_audio_at - opening_detected_at`
- `first_audio_at - tts_session_started_at`
- `tts_queue_wait_ms`
- 按 `(provider, model)` 统计 active sessions、队列长度、限流次数和降级次数；
- opening 总合成时长；
- 实时会话失败率及降级率。

## 9. 测试与验收

### 9.1 单元测试

- partialjson 逐步输入时只推送新增的 `opening_text_delta`，相同内容不重复推送；
- opening 缺失、超长、重复值、转义未闭合以及无标点时仍可增量发送的场景；
- Provider 无关 session 契约测试；
- `TTSScheduler` 按 `(provider, model)` 隔离队列、并行槽位、队列超时和背压；
- 不同 Provider/模型互不阻塞，同一 Provider/模型不超过配置的并行会话数；
- 文本提交速率达到上限时按配置节流，队列满时暂停上游文本消费；
- 火山 StartSession/TaskRequest/FinishSession 协议帧和音频帧解析；
- 阿里云回调到队列、完成、错误和超时；
- 22.05kHz → 24kHz 重采样输出；
- 实时会话失败后普通 TTS 降级；
- opening 不重复合成、不进入最终音频；每个 line 的已发送 delta 不重复合成。

### 9.2 集成测试

- Mock LLM 流式输出 title、opening 和正文；
- Mock Provider 记录 `send_text()` 顺序并生成确定性 PCM；
- 验证事件顺序：

```text
ready → status → script_preview(opening) → opening 音频 → start_notice → line_start/text_delta/audio/line_end → complete
```

- 验证不生成 thinking filler，opening 尚未产生时只推送状态；验证 line TTS 可以提前生成，但 WebSocket 音频推送顺序仍为 opening → start_notice → line；
- 验证非实时 Provider 的逐行回退路径。

### 9.3 真机验证

使用 100 字测试文本分别验证：

- opening 一次提交时的首音延迟；
- 多个短语连续提交时的首音延迟和句间连续性；
- 阿里云 Plus 实时接口；
- 火山引擎双向 WebSocket 接口；
- 当前 HTTP 降级接口；
- iPhone Safari 和桌面 Chrome 的音频播放。

参考基线（当前最小实测，不作为硬编码阈值）：

| 模式 | 阿里云 Plus 首音 | 火山双向首音 |
| --- | ---: | ---: |
| 100 字一次提交 | 约 0.66 秒 | 约 0.67 秒 |
| 每 50ms 提交 1 字 | 约 2.08 秒 | 约 5.43 秒 |

验收重点是首音与降级可用性，不要求两家 Provider 的绝对耗时相同。

## 10. 分期实施建议

### P1：opening、line 增量 TTS 和统一会话抽象

- 扩展流式输出协议和 partialjson preview；
- 增加 opening 增量检测、前缀去重和运行状态字段；
- 抽象 Provider 无关 StreamingTTSSession；
- opening 使用主持人音色立即流式合成；
- 角色信息完成后启动 VoiceMatcher；
- 每个 line 在角色和音色确定后按文本 delta 流式合成，并按 line 顺序排队推送；
- 保持普通逐行 TTS 作为降级路径，移除 thinking filler 主路径；start_notice 保持独立。

### P2：火山双向实时适配

- 新增 WebSocket 双向 adapter；
- opening 接入实时文本输入；
- 完成连接、会话、音频帧和错误处理；
- 保留 HTTP Chunked 降级。

### P3：阿里云实时适配

- 增加 DashScope SDK 和 endpoint 配置；
- 实现 callback → queue → 24k PCM；
- Plus/Flash 配置和配额错误降级；
- 完成实时/非实时能力探测。

### P4：多 line 并行与播放调度优化

- 优化多个 line 的并行 TTS 会话数量和资源上限；
- 优化不同角色切换时的会话复用与关闭时机；
- 优化 line 音频有序缓冲，避免后续 line 长时间占用内存；
- 完成前端行级字幕、播放队列与实时音频的时序验证。

## 11. 未决决策

1. 实时 Provider 配置是否由运行时设置页面暴露 endpoint、model 和启用开关。
