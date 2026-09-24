# 常见故障排查

## 配置和认证

- 没有 LLM/TTS provider：检查变量名、`.env` 所在目录、TTS allowlist 和 `list-voices` 输出。
- 401/登录失败：确认 Web 密码/初始化码、cookie、secret 和 Docker 数据卷未被替换。
- provider 连接 502/504：先查看底层 provider 日志，再确认模型、resource id、workspace 和网络。

## 音色和匹配

- 候选池过少：检查角色 gender/age、音色年龄数组、分类偏好和音色是否被禁用。
- 模型总选同一音色：查看完整候选池和 `voice_matching_prompt`；通过音色管理禁用高频音色后重新生成任务。
- 分配结果异常：同时查看候选池日志和 `voice_matching_llm_response`，确认序号没有越界或重复。

## 流式 TTS

- WebSocket 1008：会话 token/cookie 无效；重新登录。
- 4404：使用 `job_id` 重连时任务已不在内存；从故事书架检查落盘项目。
- 排队超时：检查 `(provider, model)` 的并发、queue size、queue timeout 和限速配置。
- 没有实时音频：查看 `tts_provider_session_started` 和 Provider 错误；必要时使用原生 MP3/HTTP 路径。

## 音频和 Docker

- 无法拼接：检查 ffmpeg 是否安装以及逐句片段是否存在。
- 音效为空或不入库：生成音频可能不可读/近乎静音，检查项目 `sounds/` 原始文件和音效 provider 日志。
- 容器重启后数据消失：确认 `./docker-data:/data` 挂载和 `STORYTELLER_DATA_DIR=/data`。
