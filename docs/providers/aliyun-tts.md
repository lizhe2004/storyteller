# 阿里云百炼 TTS

## 项目配置

主要配置项：`STORYTELLER_TTS_ALIYUN_API_KEY`、`STORYTELLER_TTS_ALIYUN_MODELS` 和可选的 `STORYTELLER_TTS_ALIYUN_WORKSPACE_ID`。TTS provider 名是 `aliyun`；模型白名单用于限制 catalog/模型调用。workspace 配置后，项目会派生 HTTP 专属域名和实时 WebSocket 地址。

阿里云 voice catalog 的 `voice_id` 是项目传给阿里云的音色标识；项目内部仍统一称为 `voice_id`，不另设 resource-id 音色概念。具体模型是否支持某个音色由 Provider 实现和厂商接口共同决定。

## 调用路径和指令

同步合成使用阿里云 HTTP TTS；流式合成通过 DashScope realtime WebSocket。项目统一传入 `directives` 和 `context`，阿里云适配器再将其拼接/映射到厂商 realtime 请求能接受的 instruction/context 结构。上层不应在 direction 中写 `instruction`、JSON 或阿里云专用字段。

流式会话按 `send_text → finish/iter_audio` 生命周期运行，PCM 数据按项目统一采样率输出；Provider 内部处理厂商回调和必要的音频重采样。底层启动参数会记录在 Provider 日志中，敏感凭据不应写入日志。

## 常见问题

- 没有音色：检查 API key、模型白名单和 catalog 中的 voice_id。
- realtime 无法启动：检查 workspace ID、依赖和对应 WebSocket 地址。
- direction 没有改变语气：确认台词先生成 direction，且当前模型/音色支持 instruction 能力。

厂商原始资料：[`qwen-audio-tts-http-api.md`](../reference/tts/qwen-audio-tts-http-api.md)、[`qwen-audio-realtime-tts-user-guide.md`](../reference/tts/qwen-audio-realtime-tts-user-guide.md)、[`qwen-audio-tts-realtime-python-sdk.md`](../reference/tts/qwen-audio-tts-realtime-python-sdk.md)。
