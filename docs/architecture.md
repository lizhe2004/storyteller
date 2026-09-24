# 系统架构

## 总体数据流

```text
主题
  → LLM 生成 Script(JSON)
  → ProjectManager 持久化 project.json
  → VoiceMatcher 为 characters 分配 voice_config
  → 每条 ScriptLine 选择 voice_config 并调用 TTS
  → 项目内音频片段
  → 拼接 story.<format>
  → 可选生成/缓存音效并混音
```

CLI 和 Web 共用模型、Provider registry、项目持久化和音频处理代码。CLI 由 `Pipeline.run/resume` 同步执行；Web 由 `StreamOrchestrator` 逐步发布剧本、角色和音频事件，最后复用 pipeline 的项目产物和混音逻辑。

## 核心边界

- `core/models.py`：`Script`、`Character`、`ScriptLine`、`VoiceConfig` 和 `SoundEffect` 等领域对象。
- `core/story_generator.py`：构造剧本提示词、解析 JSON、整理角色/台词/direction/声音 cue。
- `core/voice_matcher.py`：从 registry 音色元数据生成候选池并完成 LLM 或规则匹配。
- `providers/registry.py`：按配置注册 LLM、TTS、流式 TTS 和音效 Provider；核心流程不直接依赖厂商类名。
- `core/pipeline.py`：同步生成的编排、片段缓存、拼接和混音。
- `core/project.py`：项目目录、`project.json`、剧本 JSON 和项目音频的读写。
- `web/streaming.py`：Web 流式剧本/逐句 TTS/事件发布；`web/tts_scheduler.py` 控制流式会话资源。
- `web/routes_*.py`：认证、设置、故事、音色、音色分析和 WebSocket HTTP 边界。

## 持久化边界

项目根目录通常是 `<data_dir>/stories`。项目第一次保存时使用稳定的 `project_id` 目录；剧本生成后通常移动为 `<YYYY-MM-DD>-<title>`，`project.json` 内的 `project_id` 不变。目录内包含 `project.json`、`story.script.json`、逐句音频、最终 `story.<format>`，以及需要时的项目 `sounds/` 原始片段。

全局音效库位于 `<data_dir>/sounds`，由 `index.json` 维护；音色年龄/启用状态覆盖位于数据目录中的 voice override 文件。运行时设置位于 `<data_dir>/config/settings.json`。这些数据与代码镜像分离，应通过卷或备份保留。

## Provider 依赖方向

核心层只使用统一的 LLM/TTS/streaming-TTS/sound 接口和 `VoiceConfig`。Provider 负责将统一参数转换为厂商请求；例如项目的 `direction` 会作为 directives 进入 TTS 调用，Provider 再决定使用 instruction、context 或厂商专用字段。新增 Provider 时应扩展 registry、配置和音色元数据，不应在角色匹配规则中增加 provider 分支。
