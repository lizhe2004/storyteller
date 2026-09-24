# Web API 总览

## 本地访问、响应格式和认证

默认地址是 `http://127.0.0.1:8000`。HTTP API 没有统一使用一种响应格式：普通查询和修改接口返回 JSON；`POST /api/auth`、`POST /api/auth/setup` 和 `POST /api/auth/logout` 成功时返回没有响应体的 `204 No Content`；故事、分句、音色片段和实时 MP3 接口返回音频字节。需要 JSON 请求体的接口会在各节单独标明。

浏览器前端通过同源请求自动携带 `storyteller_session` cookie。脚本客户端也可以保存并发送该 cookie。认证要求按端点定义，不应假设所有 `/api/*` 都需要会话：认证端点和 `GET /api/me` 是公开的，voice-analysis HTTP 路由当前也是公开的；settings、stories、streaming audio、voices 和 options 需要有效会话。WebSocket `/ws` 和 `/ws/voice-analysis` 校验 cookie，也接受查询参数 `?token=<session-token>`。

需要认证的 HTTP 端点在未登录时返回 `401` 和 `{"detail":"未登录"}`。公开端点不会仅因缺少 cookie 返回 401；`GET /api/me` 会返回 `{"authenticated":false}`。Pydantic 请求校验错误使用 FastAPI 的 `422` 格式，显式业务错误通常是 `{"detail":"..."}`。以下各节列出端点特有的常见错误。

## 路径分组

| 分组 | 入口 | 作用 | HTTP 认证 |
| --- | --- | --- | --- |
| 认证 | `/api/auth/status`, `/api/auth`, `/api/auth/setup`, `/api/auth/logout`, `/api/me` | 首次设置、登录、会话状态和退出 | 均公开；`/api/me` 只报告 cookie 是否有效 |
| 选项 | `GET /api/config/options` | 长度、复杂度、provider、LLM/TTS 模型下拉选项 | 需要会话 |
| 设置 | `/api/settings` | 运行时配置、保存、历史、重置、provider 测试和模型列表 | 需要会话 |
| 故事 | `/api/stories`, `/api/streaming-jobs/...` | 已保存故事、音频、分句音频和实时 MP3 | 需要会话 |
| 音色 | `/api/voices` | 音色筛选、年龄/启用状态和试听片段 | 需要会话 |
| 实时生成 | `WS /ws` | 创建或手动重连故事任务、JSON 事件和二进制 PCM | 握手后校验会话 token |
| 音色分析 | `/api/voice-analysis/jobs...`, `WS /ws/voice-analysis` | 音色分析任务、建议和进度 | HTTP 当前公开；WebSocket 校验会话 token |

静态页面、`/assets/*` 和 history-mode 的无扩展路径由同一服务提供。缺失的带扩展名资源返回 404，不会被 SPA fallback 伪装成 HTML。

## 认证端点

### `GET /api/auth/status`

- 认证：公开；未登录时行为相同。
- 请求：无请求体。
- `200` JSON：`setup_required` 表示尚未配置密码，`setup_available` 表示当前进程仍持有可用的一次性初始化码。
- 相关错误：没有端点特有的业务错误。

### `POST /api/auth`

- 认证：公开；用于创建会话。
- JSON 请求：`password`（字符串，必填）。
- 成功：`204 No Content`，无 JSON 响应体；响应设置 HttpOnly 的 `storyteller_session` cookie。
- 相关错误：尚未完成首次设置为 `409`，密码错误为 `401`，请求频率过高为 `429`，字段缺失或类型不符为 `422`。

### `POST /api/auth/setup`

- 认证：公开；只在首次设置期间可用。
- JSON 请求：`code`（日志中的一次性初始化码）和 `password`（字符串），均必填。
- 成功：`204 No Content`，无 JSON 响应体；保存密码哈希和新 secret，并设置会话 cookie。
- 相关错误：初始化码错误为 `401`，密码少于 8 个字符或 schema 校验失败为 `422`，首次设置已完成或初始化码已失效为 `409`，请求频率过高为 `429`。

### `POST /api/auth/logout`

- 认证：公开；无有效会话也可以调用。
- 请求：无请求体。
- 成功：`204 No Content`，无 JSON 响应体；删除 `storyteller_session` cookie。
- 相关错误：没有端点特有的业务错误。

### `GET /api/me`

- 认证：公开。
- 请求：无请求体。
- `200` JSON：`authenticated`（布尔值）。没有、过期或无效 cookie 时返回 `false`，而不是 401。
- 相关错误：没有端点特有的业务错误。

## 生成选项

### `GET /api/config/options`

- 认证：需要有效会话；未登录返回 `401`。
- 请求：无请求体。
- `200` JSON：
  - `lengths`：`short`、`medium`、`long`；
  - `complexities`：`simple`、`medium`、`rich`；
  - `tts_providers`：对象数组，每项含 `name`；
  - `sound_enabled`：是否启用音效；
  - `llm_models`：每项含 `provider`、`model`、`label`、`is_default`；
  - `audio_models`：每项含 `provider`、`model`、`label`。

该响应不包含 API key。模型项来自当前运行时设置和已注册 provider。

## 音色和试听片段

这一组端点都需要有效会话，未登录统一返回 `401`。`voice_key` 是目录返回的 `key`，放入路径时必须进行 URL 编码。

### `GET /api/voices`

- 认证：需要有效会话；未登录返回 `401`。
- 查询字段：可选的 `provider`、`model`、`gender`、`age`；`status` 为 `all`（默认）、`enabled` 或 `disabled`；`page` 默认 1；`page_size` 默认 50，并被限制到 1–200。
- `200` JSON：`voices`、`total`、`page`、`page_size` 和 `filters`。`filters` 含可用的 `providers`、`models`、`genders`、`ages` 数组。
- 每个 voice 含 `key`、`provider`、`model`、`voice_id`、`name`、`gender`、`age`（枚举数组）、`category`、`description`、`tags`、`clip_count`、`has_clips`、`enabled`。
- 相关错误：无效 `status` 为 `400`；不能解析为整数的分页参数由 FastAPI 返回 `422`。

### `PATCH /api/voices/{voice_key}`

- 认证：需要有效会话；未登录返回 `401`。
- JSON 请求：至少提供 `age` 或 `enabled`。`age` 是 `child`、`teen`、`young_adult`、`middle_aged`、`senior` 组成的字符串数组；`enabled` 是布尔值。两者可以同时提交。
- `200` JSON：更新后的完整 voice 对象，字段与列表项相同。
- 相关错误：voice 不存在为 `404`；请求体不是 JSON 对象、没有可修改字段、`enabled` 非布尔值或 `age` 非合法枚举数组为 `400`。

### `GET /api/voices/{voice_key}/clips`

- 认证：需要有效会话；未登录返回 `401`。
- 请求：无请求体。
- `200` JSON：`clips` 数组。每项含 `clip_id`、`project_id`、`story_title`、`character_name`、`text`、`created_at`、`duration_ms` 和 `audio_url_id`。
- 相关错误：voice 不存在为 `404`。

### `GET /api/voices/{voice_key}/clips/{clip_id}/audio`

- 认证：需要有效会话；未登录返回 `401`。
- 请求：无请求体。
- `200`：`audio/mpeg` 音频字节，不是 JSON。
- 相关错误：voice 不存在、片段不存在、音频文件缺失或不安全的 `clip_id` 都返回 `404`。

## 音色分析任务

以下 HTTP 路由当前没有 `require_login` 依赖：未登录请求会按正常业务逻辑处理，不会因为缺少会话而返回 401。部署到不可信网络前应在反向代理层限制访问。音色分析的 WebSocket 仍要求会话，见后文。

任务摘要（下文的 job snapshot）含 `job_id`、`status`、`phase`、`sample_limit`、`model_sample`、`model_summary`、`prompt_version`、`analysis_config_version`、`sampling_strategy`、`sample_seed`、`total`、`completed`、`failed`、`skipped`、`created_at` 和 `updated_at`。运行中还可能出现 `current`、`voice_completed`、`voice_failed`、`last_error`；任务失败时可能出现 `error_type` 和 `error_message`。

### `GET /api/voice-analysis/jobs`

- 认证：公开；未登录时按相同逻辑返回任务列表。
- 请求：无请求体。
- `200` JSON：`jobs` 数组，每项是 job snapshot，按 `created_at` 从新到旧排列。
- 相关错误：没有端点特有的业务错误。

### `POST /api/voice-analysis/jobs`

- 认证：公开；未登录时也会创建并启动任务。
- JSON 请求：所有字段均可选。`sample_limit` 默认 10，并限制到 1–20；`model_sample` 和 `model_summary` 默认 `gemini-3.5-flash-lite`；`prompt_version` 默认 `voice-analysis-v1`；`analysis_config_version` 默认 `v1`；`sampling_strategy` 默认 `random`；`sample_seed` 默认由服务生成。
- `200` JSON：新建任务的 job snapshot。任务会立即提交到后台执行。
- 相关错误：路由没有定义端点特有的 4xx schema；请求体必须是可解析的 JSON，字段值还必须能被任务管理器转换。
- 运行期失败：请求已被接受后发生的扫描或分析错误通过 snapshot 的 `status: "failed"`、`phase`、`error_type` 和 `error_message` 报告，而不是作为原请求的后续 HTTP 错误。

### `GET /api/voice-analysis/jobs/{job_id}`

- 认证：公开；未登录时行为相同。
- 请求：无请求体。
- `200` JSON：job snapshot，外加 `samples`、`voice_summaries` 和 `suggestions`。
- `samples` 每项包含 `sample_id`、故事/分句/角色字段、`audio_path`、音色字段、`catalog_snapshot`，已分析样本另含 `result`；`voice_summaries` 的分析内容由 analyzer 结果决定；`suggestions` 每项通常含 `suggestion_id`、`voice_key`、`status`、`text`、`category` 和 `source`。
- 相关错误：任务不存在为 `404`。

### `GET /api/voice-analysis/jobs/{job_id}/samples/{sample_id}/audio`

- 认证：公开；未登录时也可读取存在的样本音频。
- 请求：无请求体。
- `200`：`audio/mpeg` 样本字节，不是 JSON。
- 相关错误：任务、样本或样本音频文件不存在时分别返回 `404`。

### `POST /api/voice-analysis/jobs/{job_id}/cancel`

- 认证：公开；未登录时也可取消存在的任务。
- 请求：无请求体。
- `200` JSON：更新后的 job snapshot；当前实现把 `status` 和 `phase` 设为 `canceled`。
- 相关错误：任务不存在为 `404`。

### `POST /api/voice-analysis/jobs/{job_id}/resume`

- 认证：公开；未登录时也可重新提交存在的任务。
- 请求：无请求体。
- `200` JSON：当前 job snapshot，并把可继续的任务重新提交到后台。已经处于 `running` 或 `completed` 的任务不会重复启动。
- 相关错误：任务不存在为 `404`。

### `POST /api/voice-analysis/jobs/{job_id}/suggestions/{suggestion_id}/approve`

- 认证：公开；未登录时也可修改建议状态。
- 请求：无请求体。
- `200` JSON：更新后的 suggestion 对象，`status` 为 `approved`，并包含新的 `updated_at`；其余字段沿用建议记录。
- 相关错误：任务或建议不存在为 `404`。

### `POST /api/voice-analysis/jobs/{job_id}/suggestions/{suggestion_id}/reject`

- 认证：公开；未登录时也可修改建议状态。
- 请求：无请求体。
- `200` JSON：更新后的 suggestion 对象，`status` 为 `rejected`，并包含新的 `updated_at`；其余字段沿用建议记录。
- 相关错误：任务或建议不存在为 `404`。

## 主要故事入口

以下故事和 streaming-audio HTTP 端点需要有效会话；未登录返回 `401`。

- `GET /api/stories` → `{ "stories": [{ "id", "dir_name", "title", "state", "duration_ms", "created_at" }] }`。
- `GET /api/stories/{ref}` → 项目标题、主题、状态、角色摘要和 `lines`；无剧本返回 404。
- `GET /api/stories/{ref}/audio` → 返回已生成的 `mp3`、`wav`、`ogg` 或 `m4a`；没有完整音频返回 404。
- `GET /api/stories/{ref}/segments/{segment}` → 返回单句 MP3；`segment` 只允许字母、数字、下划线和连字符，可带 `.mp3`。
- `GET /api/streaming-jobs/{job_id}/audio` → `audio/mpeg` 流；任务不是 `native_mp3` 返回 409，缺少 ffmpeg 返回 503，响应带 `Cache-Control: no-store`。

## WebSocket `/ws`

连接必须携带有效 cookie 或 `?token=...`。无效 token 使用关闭码 1008，限流使用 1013。新任务连接后发送：

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

`topic`、`length`、`complexity`、`with_sound`、`llm_model`、`tts_model` 和 `audio_mode` 组成任务参数；`tts_providers` 也可作为 provider 名称数组发送。只有 `audio_mode: "native_mp3"` 会启用原生 MP3，其余值都按 `webaudio` 处理。连接期间客户端可发送 `{"type":"cancel"}`。

`/ws?job_id=<job-id>` 是服务端协议提供的手动重连能力：找到内存中的任务后会先重放快照，再继续发送队列事件；任务不存在使用关闭码 4404。当前放映室前端没有持久化 ready 事件里的任务 ID，也没有自动用该参数恢复连接，因此页面刷新不会自动重连原任务。

## WebSocket 事件字段

`/ws` 的文本帧是下列 JSON 事件；音频帧是 `ready.audio` 所描述的 PCM 二进制数据。

除重连时服务端直接补发的 `status` 快照事件外，`/ws` 的每个 JSON 事件都含有公共字段 `server_time`（ISO 8601 服务端时间戳）；`ready` 事件也明确返回该字段。重连快照中的 `status` 事件由路由直接构造，目前不含 `server_time`，因此客户端不应把它当作全量事件的统一字段。

| `type` | 其余字段（均含 `server_time`，重连快照 `status` 除外） |
| --- | --- |
| `ready` | `job_id`, `playback_mode`, `server_time`, `model_selection: {llm, audio}`, `audio: {encoding, sample_rate, channels}` |
| `status` | `phase`；可能含 `message`、`queue_position`，重连快照还含 `index`、`total` |
| `script_preview` | `title`, `opening`, `total`, `characters`, `lines`；line 含生成器已有的分句字段和计算出的 `speaker` |
| `characters_matched` | `characters`；每个角色含 `id`, `name`, `description`, `gender`, `age`, `voice`，其中 voice 可为 null，否则含 `provider`, `model`, `voice_id`, `name`, `gender`, `age`, `category`, `description` |
| `script_ready` | `title`, `total`, `characters`（同上），`lines`；每行含 `line_id`, `line_type`, `character_id`, `speaker`, `text` |
| `opening_text_delta` | `text` |
| `opening_audio_start` | 无 |
| `opening_audio_end` | `duration_ms` |
| `opening_audio_abort` | 无 |
| `start_notice` | `text` |
| `line_start` | `line_id`, `index`, `total`, `speaker`, `text`, `has_sound` |
| `line_text_delta` | `line_id`, `index`, `text` |
| `line_end` | `line_id`, `duration_ms` |
| `warning` | `message`，与某句相关时另含 `line_id` |
| `finalizing` | 无 |
| `complete` | `project_id`, `title`, `audio_url`, `script_url`, `duration_ms` |
| `error` | `message` |
| `canceled` | 无 |

## WebSocket `/ws/voice-analysis`

该 WebSocket 需要有效 cookie 或 `?token=...`，无效 token 使用关闭码 1008。连接后客户端发送 `{"type":"subscribe","job_ids":["analysis_..."]}`。服务端事件为：

- `ready`：`type` 和客户端提交的 `job_ids`；
- `progress`：`type`、`job_id`，以及对应 job snapshot 的全部字段。

只要订阅列表非空，服务端每秒发送存在任务的进度；所有找到的任务进入 `completed`、`failed` 或 `canceled` 后结束连接。当前音色分析详情页会在非终态断线后自动重新建立这一条 WebSocket；这与故事放映室的 `/ws?job_id=...` 恢复能力不同。

详细操作流程见 [Web 使用指南](../web.md)。设置请求字段和响应示例见 [Settings API](settings.md)。
