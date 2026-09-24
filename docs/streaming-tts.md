# 流式 TTS

## 调用模型

一次流式会话对应一个 `(provider, model, voice)`。统一接口是：

```python
session = provider.open_stream(voice, directives=[direction], context=[previous_text])
session.send_text(text_chunk)
for chunk in session.iter_audio():
    consume(chunk)
session.finish()
```

取消时调用 `cancel()`；`finish()` 表示不再接受文本，但允许已排队音频排空。Provider 适配器把 `directives` 和 `context` 转成厂商所需的 instruction、context_texts 或其他请求字段，核心调度器不使用厂商字段名。

## direction 和 text 的顺序

剧本提示词要求每个 narration/dialogue line 先生成 `direction`，再生成 `text`。流式解析时，只有拿到 line 的 direction 后才启动该 line 的 TTS session；随后增量发送 text。若模型异常地先输出 text、没有 direction，系统把 direction 视为空，仍按无 direction 的默认 TTS 请求生成，不能因为缺少 direction 阻塞整条台词。

direction 必须是自包含的自然语言语气/情绪指令，不应包含供应商专用的 `instruction` 或 `context_texts` 格式，也不应重复台词原文。context 是最近的故事文本，用于保持语气连续，不等同于当前 line 的 direction。

## 调度器

`TTSScheduler` 以 `(provider, model)` 分组限制实时会话：

- `max_concurrent_sessions`：同时占用的 Provider 会话数；
- `max_text_chunks_per_second`：发送文本块的速率限制；
- `queue_size`：单会话待发送文本队列容量；
- `queue_timeout_seconds`：等待会话槽位或文本队列的超时。

队列满时发送方等待，形成背压；取消会清空排队文本、取消底层 session 并释放槽位。opening/start notice 具有更高优先级，避免开场长期排队。排队超时、Provider 启动失败或底层音频迭代失败会通过 Web 任务错误事件暴露。

## 观测和排查

底层日志会记录 `tts_session_queued`、`tts_queue_wait_finished`、`tts_session_started`、`tts_text_chunk_sent`、`tts_provider_text_sent`、`tts_first_audio_received` 和 `tts_session_finished`。这些事件包含 provider、model、voice_id、phase 和可能的 line_id；查一次流式故障时应结合 job_id、project_id 和 session 日志。
