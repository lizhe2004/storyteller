# WebSocket API

## 故事生成 `/ws`

连接需要 session cookie 或 `?token=`。新任务连接后发送：

```json
{
  "type": "start",
  "topic": "月亮下的小狐狸",
  "length": "medium",
  "complexity": "simple",
  "with_sound": false,
  "llm_model": {"provider": "writer", "model": "story-model"},
  "tts_model": [{"provider": "aliyun", "model": "voice-model"}],
  "audio_mode": "webaudio"
}
```

`audio_mode` 为 `native_mp3` 时，最终可从 streaming-job audio 路径播放；其他值使用 PCM Web Audio。客户端发送 `{"type":"cancel"}` 取消任务。手动重连使用 `/ws?job_id=<id>`，服务端会重放 `ready`、状态快照和已知剧本事件；任务不存在关闭码为 4404。无效认证为 1008，连接限流为 1013。

JSON 事件带 `type`；正常新任务事件通常还带 `server_time`，但重连时服务端补发的状态快照可能不带该字段。二进制帧是 `pcm_s16le`，采样率和声道数以 `ready.audio` 为准。事件及字段完整表见 [API 总览](overview.md)。

## 音色分析 `/ws/voice-analysis`

该连接也支持 cookie 或 token。客户端发送 `{"type":"subscribe","job_ids":["analysis_..."]}`，服务端返回 `ready` 和包含 job snapshot 的 `progress` 事件；任务进入终态后订阅结束。详情见 API 总览和音色管理文档。

## 生命周期

服务端先校验认证和限流，再接受连接。流式编排负责生成 opening、剧本预览、角色匹配、line 文本和音频；底层 TTS session 结束后发布 `line_end`。任务完成时发布 `complete`，取消/异常时发布 `canceled`/`error`。客户端不应把 WebSocket 连接关闭误认为项目数据已删除，应查询故事书架确认持久化结果。

