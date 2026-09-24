# 火山引擎 TTS

## 项目配置

主要配置项：`STORYTELLER_TTS_VOLCENGINE_API_KEY`、`STORYTELLER_TTS_VOLCENGINE_RESOURCE_ID` 和可选 model 配置。TTS provider 名是 `volcengine`。这里的 `resource_id` 是火山引擎 TTS 接口用于选择资源/服务版本的字段；它不是项目的 `voice_id`，也不是角色音色名。

voices catalog 中每条记录的 `voice_id` 是具体 speaker，记录也可以带 `model` 供调度器按 `(provider, model)` 分组。新增模型或音色应更新标准 catalog 元数据，而不是修改匹配器的 provider 分支。

## 调用路径和指令

同步调用使用火山单向 HTTP 流式接口；实时逐句播放使用双向 WebSocket。项目将 line 的 `direction` 和最近文本 context 作为统一参数传入，火山适配器把它们放入请求的 `context_texts`/相关 additions 字段。`resource_id`、speaker、audio parameters 和 post-process 等厂商字段只在 Provider 内部组装。

实时 session 先连接、启动 session，再发送 text task；`finish` 等待服务端完成事件，`cancel` 关闭会话。底层日志会记录脱敏后的 session 参数，用于定位 resource id、voice id、采样率和会话失败问题。

## 常见问题

- 认证失败：确认 TTS key 与 LLM key 分开配置。
- 资源/模型错误：确认 `RESOURCE_ID` 与账号可用的火山资源匹配。
- 音色不存在：确认 catalog 的完整 `voice_id`，不要把展示名或 resource id 当 voice id。
- WebSocket 超时：检查网络、Provider 日志和 scheduler 的会话/排队限制。

厂商原始资料：[`火山引擎单向流式tts http.md`](../reference/tts/火山引擎单向流式tts http.md)、[`火山引擎双向流式tts websocket.md`](../reference/tts/火山引擎双向流式tts websocket.md)、[`火山引擎语音指令与引用上下文.md`](../reference/tts/火山引擎语音指令与引用上下文.md)。
