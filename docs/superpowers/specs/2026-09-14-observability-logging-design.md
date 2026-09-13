# 故事生成日志与可观测性设计

## 目标

补齐 CLI 和 Web 生成流程的日志，使每个任务都能回答：任务在哪个阶段、调用了哪个外部 provider、耗时多少、是否保存/导出成功，以及异常发生在哪里。

## 范围

- 控制台实时日志
- `data_dir/logs/storyteller.log` 传统文本文件日志
- Web Job 的 `job_id`、`project_id` 链路字段
- LLM、TTS、音色匹配、项目保存、脚本/音频导出的开始、完成、失败和耗时日志
- WebSocket 关键事件的服务端时间

不引入数据库日志、ELK 或 OpenTelemetry；不默认记录完整 Prompt、完整剧本和完整模型响应。

## 日志输出

### 控制台

使用可读文本格式，包含时间、级别、logger、任务链路字段、阶段和事件摘要。控制台保留面向用户的 CLI 进度输出，但底层阶段和外部调用统一使用 Python `logging`，避免业务代码散落 `print()`。

### 文件

使用传统文本格式写入 `data_dir/logs/storyteller.log`，并使用滚动文件 handler 限制单文件大小和备份数量。每条记录使用统一格式，至少包含时间、级别、logger、事件和可用的任务链路字段：

```text
2026-09-14 23:49:31,123 INFO storyteller.web job=job_xxx project=proj_xxx phase=voices event=llm_request_completed operation=voice_assignment duration_ms=19042
```

字段仍采用 `key=value` 形式，便于人工阅读，也方便以后用 `rg`、日志采集器或简单脚本检索。

外部调用额外记录 provider、model、operation、候选数量、角色数量或 line_id 等低敏元数据。完整 Prompt 和响应仅在 DEBUG 下以截断文本或长度形式辅助诊断。

## 事件模型

统一使用事件名记录以下节点：

- `job_started`、`job_completed`、`job_failed`
- `phase_started`、`phase_completed`
- `llm_request_started`、`llm_request_completed`、`llm_request_failed`
- `llm_stream_started`、`llm_stream_completed`
- `voice_matching_started`、`voice_matching_completed`
- `tts_request_started`、`tts_request_completed`、`tts_request_failed`
- `project_saved`、`script_exported`、`audio_exported`
- `websocket_event_sent`

耗时事件使用 `started_at`、`completed_at` 和 `duration_ms`。异常日志保留 Python 堆栈；发给 WebSocket 客户端的错误仍使用简短、安全的消息。

## WebSocket 时间信息

关键 WebSocket 业务事件增加 `server_time`，必要时增加 `job_id` 和 `project_id`，用于区分服务端处理耗时、网络传输延迟和前端渲染延迟。预览事件不记录完整内容到日志，只记录事件类型和快照规模。

## 重点诊断链路

音色阶段至少能够形成如下链路：

```text
voice_matching_started
llm_request_started(operation=voice_assignment)
llm_request_completed(duration_ms=...)
project_saved(duration_ms=...)
script_exported(duration_ms=...)
websocket_event_sent(event=script_ready)
```

## 失败与兼容

- 日志初始化必须幂等，避免 CLI、Web worker 或测试重复添加 handler。
- 日志目录自动创建；文件不可写时不应阻断故事生成，至少保留控制台日志。
- 旧调用方不需要传递日志参数；链路字段通过上下文或显式 job context 注入。
- 测试验证日志初始化、JSONL 字段、耗时事件和 WebSocket `server_time`。
