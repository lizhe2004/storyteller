# 阿里云百炼 TTS

## 项目配置

主要配置项：`STORYTELLER_TTS_ALIYUN_API_KEY`、`STORYTELLER_TTS_ALIYUN_MODELS` 和可选的 `STORYTELLER_TTS_ALIYUN_WORKSPACE_ID`。TTS provider 名是 `aliyun`；模型白名单用于限制 catalog/模型调用。workspace 配置后，项目会派生 HTTP 专属域名和实时 WebSocket 地址。Sambert 需要 Python 3.9+，并在运行应用的同一环境安装 DashScope SDK（源码开发时可用 `python -m pip install -e '.[web,aliyun]'`）。macOS 下该扩展锁定经验证的 `cryptography` wheel，以避开 Anaconda OpenSSL 动态库符号冲突。目前 Sambert 仅支持北京地域。

阿里云 voice catalog 的 `voice_id` 是项目传给阿里云的音色标识；项目内部仍统一称为 `voice_id`，不另设 resource-id 音色概念。具体模型是否支持某个音色由 Provider 实现和厂商接口共同决定。

## 调用路径和指令

Qwen-Audio-TTS 同步合成使用阿里云 HTTP TTS；流式合成通过 DashScope realtime WebSocket。Sambert 同步及单向流式合成使用 DashScope Python SDK。项目把 `sambert` 作为一个模型，其下的 `sambert-zhide-v1`、`sambert-zhiyue-v1`、`sambert-beth-v1` 等具体 ID 作为音色；发起 SDK 请求时才将选中的音色 ID 作为底层 `model` 参数。配置模型白名单时填写 `sambert`。当前音色目录收录 SDK 文档中的 43 个 Sambert 音色；中文故事的自动匹配会过滤掉仅支持外语的音色，显式指定音色时仍可使用。Sambert 一次请求提交一段完整文本，不支持流式文本输入；项目会按 `send_text` 的文本段分别发起合成。

项目统一传入 `directives` 和 `context`。Qwen realtime 请求将指令映射成 `instruction`；Sambert 接口没有此参数，使用 Sambert 时指令不影响发声。上层不应在 direction 中写 `instruction`、JSON 或阿里云专用字段。

流式会话按 `send_text → finish/iter_audio` 生命周期运行，PCM 数据按项目统一采样率输出；Provider 内部处理厂商回调和必要的音频重采样。底层启动参数会记录在 Provider 日志中，敏感凭据不应写入日志。

## 常见问题

- 没有音色：检查 API key、模型白名单和 catalog 中的 voice_id。
- realtime 无法启动：检查 workspace ID、依赖和对应 WebSocket 地址。
- direction 没有改变语气：确认台词先生成 direction，且当前模型/音色支持 instruction 能力。

厂商原始资料：[`qwen-audio-tts-http-api.md`](../reference/tts/qwen-audio-tts-http-api.md)、[`qwen-audio-realtime-tts-user-guide.md`](../reference/tts/qwen-audio-realtime-tts-user-guide.md)、[`qwen-audio-tts-realtime-python-sdk.md`](../reference/tts/qwen-audio-tts-realtime-python-sdk.md)、[`Sambert/sdk接入.md`](../reference/tts/Sambert/sdk接入.md)。
