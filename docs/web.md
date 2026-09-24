# Web 使用指南

Web 服务由 `storyteller web` 启动，默认监听 `127.0.0.1:8000`。打开 `http://127.0.0.1:8000/` 后，前端通过同源 HTTP API 和 `/ws` WebSocket 工作；服务也会把前端静态资源和 Vue history 路由一起提供。

## 登录和首次设置

首次启动且没有 `web.passwords` 时，服务端日志会打印一次性初始化码。登录页会显示“首次使用”表单：粘贴该码，设置并确认至少 8 个字符的访问密码，然后提交。初始化码只能使用一次；成功后服务会把密码以 PBKDF2 哈希写入运行时设置，并立即建立会话。

已有密码时直接输入访问密码。登录成功后会收到 HttpOnly、`SameSite=Lax` 的 `storyteller_session` cookie；HTTPS 请求会设置 `Secure`。会话有效期由 `web.token_ttl_days` 决定。退出会删除 cookie。请求被判定为未登录时，前端会清除登录状态并回到登录流程。

登录页使用以下接口：`GET /api/auth/status`、`POST /api/auth/setup`、`POST /api/auth`、`GET /api/me` 和 `POST /api/auth/logout`。初始化码错误返回 401，密码短于 8 个字符返回 422，首次设置已完成返回 409；登录密码错误返回 401，登录限流返回 429。

## 放映室：生成和播放故事

1. 在“放映室”输入主题，选择长度（`short`、`medium`、`long`）和复杂度（`simple`、`medium`、`rich`）。如果 options 返回了模型，选择故事模型；音频模型可以多选，所选模型会转换为对应的 TTS provider 池。
2. 可选择“加一点环境声音”，以及 `Web Audio` 或“原生 audio（MP3 实验）”播放方式。
3. 点击“开始放映”。浏览器连接 `/ws` 并发送 `type: start` 消息；服务端返回 `ready` 后，随后发送状态、剧本预览、角色/音色匹配、逐句文本和音频事件。二进制消息是 PCM 音频数据。
4. 播放器显示开场文字/声音、主持人提示、当前句、角色卡片和进度。角色卡片可查看角色描述、性别、年龄，以及匹配音色的 provider、模型、音色 ID、性别、年龄、分类和描述。
5. `Web Audio` 播放使用浏览器 AudioWorklet；原生 MP3 播放使用 `/api/streaming-jobs/{job_id}/audio`，可能被浏览器自动播放策略拦截，此时点击“开始原生播放”即可继续。

故事生成不是普通的 `POST /api/stories` 请求，而是 WebSocket 会话。页面关闭或连接中断不会把已保存故事从项目目录删除；再次打开故事书架可查看已完成项目。生成过程中点击“停止生成”会发送 `type: cancel`，服务端会发出取消事件。错误会显示在播放器中；限流错误会被前端转换为更明确的稍后重试提示。

### 模型选择的持久化边界

放映室只把最近的选择保存到当前浏览器的 `localStorage`：

- `storyteller.home.llm-model`：一个 `provider::model` 字符串；
- `storyteller.home.audio-models`：`provider::model` 字符串数组。

这些值只是 UI 默认选择，不会修改服务端配置，也不会替代任务启动消息中的显式选择。服务端 options 列表和可用 provider 来自当前运行时配置；保存或修改“系统配置”才会写入后端运行时设置。

## 故事书架和失败恢复

“故事书架”调用 `GET /api/stories`，按创建时间倒序列出项目标题、日期和状态。打开项目会调用 `GET /api/stories/{ref}`；当前 StoryView 只渲染标题、主题、完整故事音频控件，以及每行的说话人和文本。接口响应虽然还提供 `state`、`characters` 和每行可能存在的 `duration_ms`，当前详情页并不显示这些字段；`GET /api/stories/{ref}/segments/{segment}` 也可按 API 单独获取分句音频，但当前详情页不会请求或播放它。完整音频控件使用 `GET /api/stories/{ref}/audio`。

如果服务仍在内存中保留生成任务，协议客户端可以手动连接 `/ws?job_id=...`：服务端会重放 `ready`、当前状态、已有剧本预览、角色匹配和剧本就绪事件，然后继续发送队列事件。这是 WebSocket 协议能力，不是当前放映室已经实现的自动恢复流程；HomeView/player 不持久化任务 ID，页面刷新会初始化新的播放器，也不会自动带 `job_id` 重连。普通用户刷新后应从故事书架检查已经落盘的结果；不存在完整音频时详情页音频控件会请求失败，前端不会改用分句音频拼接。

## 系统配置

“系统配置”分为 Web、LLM、TTS 和音效四组。页面先读取 `GET /api/settings`，草稿只在浏览器内编辑；离开有未保存修改的页面会要求确认。

- Web：修改密码、签名 secret、token TTL、并发数、每分钟限流数和主持人音色。监听地址、端口、数据目录是只读展示，需通过环境变量、Docker 或部署配置修改。
- LLM：配置一个 provider、默认 provider、模型和候选模型；表单支持火山引擎方舟、OpenAI 兼容服务和 mock。
- TTS：维护参与音色匹配的 provider 池，没有可配置的 TTS default provider；阿里云、火山引擎、OpenAI 兼容服务和 mock 的字段由后端返回的 provider schema 决定。
- 音效：启用/禁用音效、配置目录和至多一个 provider。启用音效但没有 provider 会被拒绝。

保存后设置写入数据目录下的 `config/settings.json`，返回的 `effective_for` 是 `new_jobs`：新任务使用新快照，运行中的任务不受影响。刷新运行时配置会更新认证、限流和任务并发对象；正在使用旧 secret 的会话会失效。API key、密码和 secret 只返回 `configured`、数量及尾部掩码，前端不会回填原值；要更换密钥需输入新值。

“恢复环境变量”会先确认，再调用 reset API 删除该组允许的后台覆盖；之后回到环境变量或程序默认值。`GET /api/settings/history` 可按最新在前读取最多 100 条设置历史；当前设置页没有调用或展示这份历史，因此它是 API-only 能力。

## 音色管理和试听

“音色管理”页面从 `/api/voices` 读取音色列表，支持 provider、模型、性别、年龄和状态（全部、已启用、已禁用）筛选及分页。每行展示 voice ID、分类、标签、描述和适用年龄。保存年龄会提交年龄枚举数组：`child`、`teen`、`young_adult`、`middle_aged`、`senior`。启用/禁用是独立操作；禁用音色不会出现在启用后的匹配池中，但配置卡仍可保留。

展开“试听片段”会读取 `/api/voices/{voice_key}/clips`，播放地址是对应的 `/audio` 接口。片段是故事生成时保存的音频，包含故事、角色、台词和创建时间；没有片段时页面显示空状态。

## 访问故障排查

- 登录页显示无法初始化：检查服务日志，确认运行时配置可读且首次设置仍有初始化码。
- 401：会话 cookie 缺失、过期，或 WebSocket 的 `token`/cookie 无效；重新登录。
- 生成时连接中断：检查服务端日志和 provider 配置，刷新后从故事书架确认是否已经落盘；原生 MP3 失败时切回 Web Audio。
- 设置保存成功但当前播放未变化：这是预期行为，设置只对新任务生效。
- 音色筛选为空：确认 provider/model/年龄/启用状态筛选，并检查音色是否被禁用。

API 的完整入口和请求字段见 [API 总览](api/overview.md)；设置 API 的示例见 [Settings API](api/settings.md)。
