# 配置参考

本文记录 Storyteller 当前实现读取的配置。代码、测试和 Web 运行时行为是准确信息来源；厂商参数和账号开通条件请参阅 [`docs/reference/tts/`](reference/tts/) 及 Provider 文档。

## 配置来源和优先级

CLI 进程配置和 Web runtime settings 是两条配置路径，不能混为一个全局优先级链。

### CLI 进程配置

每次 CLI 命令启动时，`Config.from_env()` 按以下顺序读取，后者覆盖前者：

1. 内置默认值（`Config.DEFAULTS`）。
2. 当前工作目录向上查找的 `.env`，以及进程环境变量。显式传给 `Config.from_env(env_file)` 的文件优先用于加载；环境变量仍可覆盖文件中的同名值。
3. 当前 CLI 命令的选项，例如 `--data-dir`、`--progress` 或 `--sound-provider`。这些选项只影响本次命令；它们不会写入 `.env` 或 Web 设置文件。

CLI 不读取 Web 的 `<data_dir>/config/settings.json`，所以 Web 管理员保存的 runtime override 不会改变 CLI 命令。反过来，CLI 选项也不会改变 Web 进程的 runtime settings。

### Web runtime settings

Web 启动时先用同样的内置默认值、`.env` 和进程环境创建基础 `Config`，再由 `RuntimeSettingsStore` 读取 `<data_dir>/config/settings.json` 并为 Web 应用创建快照。Web API 保存的覆盖项只对 Web 后续读取和新任务快照生效；空的敏感字段不会清除已有值。

Web 设置路由当前支持 `web`（不含 `host`、`port`）、`llm`、`tts` 和 `sound` 中声明的字段，以及 provider 配置字段。调度器设置不在 Web settings API 的可编辑字段中；`web.host`/`web.port` 也不是可通过该 API 修改的字段，必须在进程启动前通过环境变量或 `storyteller web --host/--port` 配置。

LLM 和音效使用 `STORYTELLER_<GROUP>_PROVIDER` 选择默认 provider；没有选择器时，唯一自动发现的 provider 才会成为默认值。TTS 使用 `STORYTELLER_TTS_PROVIDERS` 作为可用名单；留空时才自动发现配置过的内置 provider。一个 provider 被配置，不等于它一定在 TTS 可用名单中。

## `.env` 示例

复制仓库根目录的 [`.env.example`](../.env.example) 为 `.env`，再替换占位符。最小的本地 CLI 配置示例：

```dotenv
STORYTELLER_DATA_DIR=./.storyteller
STORYTELLER_LLM_PROVIDER=volcengine
STORYTELLER_LLM_VOLCENGINE_API_KEY=replace-me
STORYTELLER_LLM_VOLCENGINE_MODEL=deepseek-v4-flash-260425
STORYTELLER_TTS_PROVIDERS=volcengine
STORYTELLER_TTS_VOLCENGINE_API_KEY=replace-me
STORYTELLER_TTS_VOLCENGINE_RESOURCE_ID=seed-tts-2.0
```

不要提交真实密钥。provider 配置变量遵循 `STORYTELLER_LLM_<NAME>_<KEY>`、`STORYTELLER_TTS_<NAME>_<KEY>` 或 `STORYTELLER_SOUND_<NAME>_<KEY>` 形式；支持的通用 key 包括 `TYPE`、`API_KEY`、`MODEL`、`BASE_URL`、`ENDPOINT`、`RESOURCE_ID`、`MODELS` 和 `WORKSPACE_ID`。`ENDPOINT` 对当前火山引擎和阿里云适配器不会被读取。

## LLM

| 环境变量 | 默认值 | 作用 |
| --- | --- | --- |
| `STORYTELLER_LLM_PROVIDER` | 唯一自动发现的 provider，否则无 | 选择本次配置的默认 LLM provider |
| `STORYTELLER_LLM_<NAME>_API_KEY` | 无 | provider 凭据；敏感；需要重新创建 CLI/Web 配置或重启进程才能让环境值进入新快照 |
| `STORYTELLER_LLM_<NAME>_MODEL` | provider 自己的默认值 | 模型名；可由 Web runtime settings 覆盖 |
| `STORYTELLER_LLM_<NAME>_TYPE` / `BASE_URL` / `ENDPOINT` | 无 | provider 类型或 OpenAI-compatible 连接参数（按 provider 实现决定） |

只发现到一个配置过的 LLM 时可以省略 `STORYTELLER_LLM_PROVIDER`；发现多个时必须显式选择，否则不会隐式选第一个。`model` 是厂商模型标识，不能当作 TTS 的 voice id 或 resource id。

## TTS

| 环境变量 | 默认值 | 作用 |
| --- | --- | --- |
| `STORYTELLER_TTS_PROVIDERS` | 自动发现 | 逗号分隔的配置 allowlist；未列入的 provider 不会注册为本次配置的一部分 |
| `STORYTELLER_TTS_<NAME>_API_KEY` | 无 | provider 凭据；敏感 |
| `STORYTELLER_TTS_<NAME>_MODEL` | provider 默认 | 模型标识 |
| `STORYTELLER_TTS_<NAME>_RESOURCE_ID` | provider 默认 | 厂商资源/服务标识，不是项目内部的 `voice_id` |
| `STORYTELLER_TTS_<NAME>_WORKSPACE_ID` | 无 | 需要业务空间的 provider 的空间标识 |
| `STORYTELLER_TTS_<NAME>_MODELS` | catalog 中全部模型 | 逗号分隔的模型白名单；当前主要用于阿里云 |

OpenAI-compatible TTS 通过成组变量声明：`STORYTELLER_TTS_OPENAI_COMPATIBLE_<SLOT>_NAME`、`..._API_KEY`、`..._BASE_URL`、`..._MODEL`。如果设置了非空的 `STORYTELLER_TTS_PROVIDERS`，该 provider 的名称也必须在名单中。CLI 的 `--tts-providers` 只能在已经注册/配置的 provider 中进一步限制本次生成或查询；它不能添加 provider，也不能扩大 `STORYTELLER_TTS_PROVIDERS` 的 allowlist。

项目语义如下：

- `provider` 是适配器注册名，例如 `aliyun`、`volcengine`。
- `model` 是 provider 使用的模型名。
- `voice_id` 是具体说话人音色的 catalog 标识，传给生成管线；`list-voices` 可以查看。
- `resource_id` 是厂商服务/资源入口，通常用于选择 TTS 产品版本，不代表某个音色。

音色匹配、音色 catalog 和厂商字段的详细差异不在此重复；参阅后续的 voice/provider 文档。

## 音效

| 环境变量 | 默认值 | 作用 |
| --- | --- | --- |
| `STORYTELLER_SOUND_ENABLED` | `false` | 是否在生成时加入音效/BGM；接受 `1`、`true`、`yes`、`on` |
| `STORYTELLER_SOUND_PROVIDER` | 唯一自动发现的 provider，否则无 | 默认音效 provider；`--sound-provider` 可覆盖本次运行 |
| `STORYTELLER_SOUND_DIR` | `<data_dir>/sounds` | 全局音效库目录 |
| `STORYTELLER_SOUND_<NAME>_API_KEY` | 无 | 独立的音效 provider 凭据；通常不复用 TTS key |
| `STORYTELLER_SOUND_<NAME>_MODEL` | provider 默认 | 音效模型，例如 `seed-audio-1.0` |

`generate --with-sfx` 只对当前生成开启音效；`make-sound` 会查找或生成全局音效库记录。多个已发现音效 provider 时必须使用环境选择器或 `--sound-provider`。

## Web

| 环境变量 | 默认值 | 敏感/运行时修改 | 说明 |
| --- | --- | --- | --- |
| `STORYTELLER_WEB_HOST` | `127.0.0.1` | 否/否 | Web 监听地址；`storyteller web --host` 可覆盖 |
| `STORYTELLER_WEB_PORT` | `8000` | 否/否 | Web 端口；`storyteller web --port` 可覆盖 |
| `STORYTELLER_WEB_PASSWORDS` | 空列表 | 是/是 | 逗号分隔的登录密码 |
| `STORYTELLER_WEB_SECRET` | 空 | 是/是 | Cookie 签名密钥 |
| `STORYTELLER_WEB_TOKEN_TTL_DAYS` | `30` | 否/是 | 登录 token 有效天数 |
| `STORYTELLER_WEB_CONCURRENCY` | `2` | 否/是 | Web 生成并发度 |
| `STORYTELLER_WEB_RATE_LIMIT_PER_MIN` | `10` | 否/是 | 速率限制 |
| `STORYTELLER_TTS_HOST_VOICE` | 自动选择旁白 | 否/是 | 实时 Web 主持人音色，格式 `provider:voice_id` |

Web runtime settings 的覆盖值保存在 `settings.json`，并在创建新任务时形成配置快照；已经运行的任务不会被中途改写。`--host`/`--port` 是启动进程参数，不会写入 runtime settings。

## 安全

API key、密码列表、Web secret 和 access password 都属于敏感值。示例只使用 `replace-me` 等占位符；日志、截图、提交和问题报告中不要暴露真实值。Web settings 的公开快照会将单值显示为 `********` 加最后最多四个字符，密码列表只显示是否配置和数量。

## 目录与缓存

默认 `STORYTELLER_DATA_DIR=./.storyteller`，相对当前启动目录解析。未显式配置时：

```text
<data_dir>/
├── stories/       项目目录、状态、剧本、分段音频和 story.<format>
├── sounds/        跨项目复用的音效库
├── config/        Web runtime settings.json 及历史记录
├── logs/          运行日志
├── web_cache/     Web 流式相关缓存
└── voice-analysis/音色分析任务数据（启用相关功能时）
```

`STORYTELLER_OUTPUT_DIR` 和 `STORYTELLER_PROJECT_DIR` 可以分别覆盖默认的 `stories/` 路径；`STORYTELLER_SOUND_DIR` 可以覆盖音效目录。CLI `--data-dir` 会重新解析未显式覆盖的目录，`--sound-dir` 只覆盖本次音效操作。

## 调度器

以下设置只影响 Web 实时 TTS，不改变同步 CLI 的整行 TTS 行为：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `STORYTELLER_TTS_SCHEDULER_MAX_CONCURRENT_SESSIONS` | `1` | 默认并发会话数 |
| `STORYTELLER_TTS_SCHEDULER_MAX_TEXT_CHUNKS_PER_SECOND` | 不限速 | 每秒文本块数；空、`0` 或负数表示不限速 |
| `STORYTELLER_TTS_SCHEDULER_QUEUE_SIZE` | `16` | 等待队列大小 |
| `STORYTELLER_TTS_SCHEDULER_QUEUE_TIMEOUT_SECONDS` | 不超时 | 排队超时；空或 `0` 表示一直排队 |
| `STORYTELLER_TTS_SCHEDULER_LIMITS_<PROVIDER>_<FIELD>` | 使用默认值 | 对 provider 覆盖并发、限速、队列大小或超时；provider 名可含下划线 |

模型级别的设置也存在于内部 config 结构（`tts.scheduler.limits.<provider>.<model>`）。当前环境变量只提供上述默认及 provider 级别入口；Web settings API 不提供 scheduler 字段的更新或 reset 路由，因此调度器配置需要在启动 Web 进程前通过环境变量设置。

## 运行时设置

Web 管理员设置被校验为 JSON 对象，只允许 `web`、`llm`、`tts`、`sound` 四个顶层组。每次 update 原子写入 `<data_dir>/config/settings.json`；写入失败会保留旧文件和旧快照。`reset` 只接受路由允许的 dotted path：`web` 的直接字段（不含 `host`、`port`）、`llm`/`tts`/`sound` 的直接字段，或 provider 配置中的已知字段，例如 `llm.provider_config.my-llm.api_key`。`web.port` 和 scheduler 路径不能通过该 API reset。

如果 settings 文件损坏，应用会回退到环境配置并在公开快照的 `config_error` 中报告错误；修复或移走损坏文件后重启 Web。运行时配置的公开值包含 `sources`，可区分 `default`、`environment` 和 `admin`。

## 配置生效时机

- `.env` 和进程环境：每个 CLI 命令启动时读取；Web 进程在启动时读取一次，已启动的 Web 进程不会自动重读环境。
- CLI 选项：仅当前 CLI 命令，优先于同名环境配置；不会读取或写入 Web runtime settings。
- Web runtime settings：保存后用于后续读取和新任务快照；端口、host、依赖安装等进程级设置需要重启，且不能通过 `settings.json` 代替 `storyteller web --host/--port`。
- Provider SDK、模型、resource id 或 API key 的更换：建议重启 Web，确保注册表和任务使用新配置。

## 敏感信息处理

设置密码时优先使用环境变量或 Web 首次设置流程；`settings.json` 需要限制文件权限并纳入备份保护。不要把 `settings.json`、`.env`、日志或音频元数据中的凭据上传到 issue。需要诊断时只提供 provider 名、模型名、配置来源和脱敏后的末四位。

## 配置故障排查

1. 先运行 `storyteller list-voices --format json` 检查 TTS provider 是否被发现；没有 provider 时检查 key 名拼写、`STORYTELLER_TTS_PROVIDERS` allowlist 和当前工作目录的 `.env`。若使用 `--tts-providers`，只能填写已注册的 provider 名称。
2. LLM 配置了多个 provider 却没有默认值时，设置 `STORYTELLER_LLM_PROVIDER` 或使用 `generate --default-llm-provider`。
3. 音效报 `No sound provider configured` 或多个 provider 冲突时，设置 `STORYTELLER_SOUND_PROVIDER` 或传 `--sound-provider`，并确认音效 key 独立配置。
4. 目录不符合预期时打印或检查 `STORYTELLER_DATA_DIR`、`STORYTELLER_PROJECT_DIR`、`STORYTELLER_OUTPUT_DIR` 和 `STORYTELLER_SOUND_DIR`；相对路径以启动命令的当前目录为基准。
5. Web 设置没有覆盖环境值时检查 `settings.json` 所在的 data root、顶层组名和 `config_error`；敏感字段的空字符串不会删除已有 admin 值，使用支持的 reset 路径。CLI 不读取这个文件。
6. 实时 Web TTS 排队或降级时检查 scheduler 的队列、并发和超时配置；这些设置只影响 Web 流式路径，不是 CLI 生成失败的首要原因。
