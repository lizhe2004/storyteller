# Web API 总览

## 本地访问和认证

默认地址是 `http://127.0.0.1:8000`。所有 HTTP API 使用 JSON 请求/响应（音频下载除外），浏览器前端通过同源请求自动携带 cookie。登录后 cookie 名称是 `storyteller_session`；脚本客户端也可以使用该 cookie。WebSocket `/ws` 和 `/ws/voice-analysis` 支持 cookie，也支持查询参数 `?token=<session-token>`。

除认证状态接口外，API 均要求有效会话。未登录的 HTTP 请求通常返回 `401` 和 `{"detail":"未登录"}`；前端遇到 401 会触发登出事件。Pydantic 请求校验错误返回 FastAPI 标准 `422`，业务拒绝通常返回 `{"detail":"..."}`。资源不存在一般是 `404`，无效筛选/路径是 `400`，provider 连接失败是 `502`，超时是 `504`。

## 路径分组

| 分组 | 入口 | 作用 | 认证 |
| --- | --- | --- | --- |
| 认证 | `/api/auth/status`, `/api/auth`, `/api/auth/setup`, `/api/auth/logout`, `/api/me` | 首次设置、登录、会话状态和退出 | 按接口；状态和登录公开 |
| 选项 | `GET /api/config/options` | 长度、复杂度、provider、LLM/TTS 模型下拉选项 | 是 |
| 设置 | `/api/settings` | 运行时配置、保存、历史、重置、provider 测试和模型列表 | 是 |
| 故事 | `/api/stories`, `/api/streaming-jobs/...` | 已保存故事、音频、分句音频和实时 MP3 | 是 |
| 音色 | `/api/voices` | 音色筛选、年龄/启用状态和试听片段 | 是 |
| 实时生成 | `WS /ws` | 创建/重连故事任务、JSON 事件和二进制 PCM | 是 |
| 音色分析 | `/api/voice-analysis/...`, `WS /ws/voice-analysis` | 音色分析任务及进度 | 当前路由注册本身不加 HTTP 登录依赖；WebSocket 校验会话 |

静态页面、`/assets/*` 和 history-mode 的无扩展路径由同一服务提供。缺失的带扩展名资源返回 404，不会被 SPA fallback 伪装成 HTML。

## 主要故事入口

- `GET /api/stories` → `{ "stories": [{ "id", "dir_name", "title", "state", "duration_ms", "created_at" }] }`。
- `GET /api/stories/{ref}` → 项目标题、主题、状态、角色摘要和 `lines`；无剧本返回 404。
- `GET /api/stories/{ref}/audio` → 返回已生成的 `mp3`、`wav`、`ogg` 或 `m4a`；没有完整音频返回 404。
- `GET /api/stories/{ref}/segments/{segment}` → 返回单句 MP3；`segment` 只允许字母、数字、下划线和连字符，可带 `.mp3`。
- `GET /api/streaming-jobs/{job_id}/audio` → `audio/mpeg` 流；任务不是 `native_mp3` 返回 409，缺少 ffmpeg 返回 503，响应带 `Cache-Control: no-store`。

## WebSocket `/ws`

客户端首次连接后发送 `{"type":"start", "topic":"...", "length":"medium", "complexity":"simple", "with_sound":false, "llm_model":{"provider":"...","model":"..."}, "tts_model":[{"provider":"...","model":"..."}], "audio_mode":"webaudio"}`。`tts_providers` 也可作为 provider 列表发送。`audio_mode` 只有 `native_mp3` 会启用原生 MP3，其余使用 Web Audio。

使用 `job_id` 重连时连接 URL 为 `/ws?job_id=...`；服务端会重放当前快照。客户端发送 `{"type":"cancel"}` 取消任务。服务端 JSON 事件包括 `ready`、`status`、`script_preview`、`characters_matched`、`script_ready`、`opening_text_delta`、`opening_audio_start/end/abort`、`start_notice`、`line_start`、`line_text_delta`、`line_end`、`warning`、`finalizing`、`complete`、`error` 和 `canceled`；音频帧作为二进制消息发送。无效 token 关闭码为 1008，找不到重连任务为 4404，限流为 1013。

详细操作流程见 [Web 使用指南](../web.md)。设置请求字段和响应示例见 [Settings API](settings.md)。
