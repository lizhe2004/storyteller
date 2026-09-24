# Provider 适配总览

## 项目抽象

项目按能力注册 Provider，而不是把业务逻辑绑定到厂商：LLM、同步 TTS、流式 TTS 和音效分别注册到 `ProviderRegistry`。配置决定哪些内置实现进入本次进程；TTS 音色由各实现提供标准元数据，再由 registry 聚合。

核心统一字段包括：

- `provider`：registry 中的适配器名称；
- `model`：项目用于区分服务模型/资源的名称；
- `voice_id`：具体音色目录标识；
- `language`、`gender`、`age`、`category`、`description`、`tags`：匹配和管理页面使用的元数据；
- `direction`：台词的自然语言演法指令；
- `context`：最近的故事文本，用于连续语气。

`resource_id` 是部分厂商接口的服务入口字段，不是项目统一的音色字段。项目会在 Provider 内部把它映射为厂商请求所需值。

## 新增 Provider 的边界

实现对应的 LLM/TTS/streaming-TTS/sound 接口，提供配置读取、错误转换、音色列表和能力声明，然后在 bootstrap/registry 注册。匹配器只消费标准音色元数据；不要在候选池规则中针对 provider 或模型名称写特殊分支。

项目 Provider 文档说明“项目已实现的适配”；厂商 API 的完整字段和限制见 [`docs/reference/tts/`](../reference/tts/)。
