# LLM Provider

## 选择和配置

LLM 一次运行选择一个 provider。`STORYTELLER_LLM_PROVIDER` 明确指定时使用该 provider；未指定时只有唯一已发现 provider 才会自动成为默认值，多个 provider 时必须明确选择。模型名由 provider 配置或 Web/CLI 选择传入。

项目内置火山引擎、Gemini、mock 和 OpenAI-compatible 等实现。OpenAI-compatible 需要 provider 类型、base URL、API key 和 model；具体字段以运行时 `provider_schemas` 为准。

## 角色匹配中的 LLM

角色匹配提示词包含剧本角色的 gender、age、description、voice_preferences，以及已经筛选的候选音色。模型只返回候选序号分配；核心代码再校验 character id、序号、性别/年龄约束和重复分配。完整匹配规则见 [角色与音色匹配](../voice-matching.md)。

LLM 请求、完整提示词、模型响应和耗时都可以通过任务日志关联。API key 只从环境/runtime settings 读取，不应写进 prompt、项目 JSON 或日志。
