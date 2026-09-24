# Documentation Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将项目文档从“README 集中维护 + 厂商原始资料分散”改造成 README 入口、主题文档和 Provider 适配文档分层维护的体系，并让第一批文档准确覆盖当前代码行为。

**Architecture:** README 只保留项目定位、最短上手路径和文档索引；`docs/` 按用户使用、核心流程、Provider、API、运维和发布拆分。文档编写以当前源码、测试和现有厂商参考资料为事实来源，先完成高频用户路径，再补充开发和运维细节。历史设计文档保留，不与当前行为文档混用。

**Tech Stack:** Markdown、Python 3.8+、FastAPI/Starlette Web API、现有 pytest 测试、Docker/Compose 文档。

**Spec:** `docs/superpowers/specs/2026-09-24-documentation-overhaul-design.md`

## Global Constraints

- README 是入口，不重复维护主题文档中的完整细节。
- 代码、测试和运行时行为是事实来源；文档描述必须以当前实现为准。
- `docs/reference/tts/` 保留为厂商原始资料，必须明确区分厂商能力和项目已实现能力。
- `docs/superpowers/specs/` 与 `docs/superpowers/plans/` 是历史设计/实施记录，不作为当前行为的唯一依据。
- 示例不得包含真实 API key、密码、Cookie secret 或其他凭据。
- 新增/删除配置项、Provider/模型、CLI/Web/API/WebSocket、数据目录、日志字段或 Docker 流程时，必须同步更新对应主题文档。
- 不引入 MkDocs、Docusaurus 或新的文档构建依赖。

## Review Focus

- 文档列出的配置项与实际环境变量、运行时设置和默认值不一致；由 Task 2 的配置交叉核对清单覆盖。
- 音色匹配描述遗漏角色性别/年龄、年龄数组、禁用音色或旁白规则；由 Task 4 的候选池示例和源码核对覆盖。
- Provider 文档把阿里云模型名、火山引擎 resource id 和项目内部模型/音色字段混为一谈；由 Task 6 的映射表和差异表覆盖。
- Web/API 文档声称存在前端功能，但路由、响应字段或持久化方式已经改变；由 Task 3 和 Task 4 的 API/页面核对覆盖。
- 日志、Docker 或数据恢复步骤在本地可用但在容器或另一台机器上不可用；由 Task 8 的运行命令和故障场景核对覆盖。

---

### Task 1: 建立文档入口和 README 边界

**Files:**
- Create: `docs/index.md`
- Create: `docs/getting-started.md`
- Modify: `README.md`
- Reference: `pyproject.toml`, `src/storyteller/cli/main.py`, `docs/deployment-docker.md`

**Interfaces:**
- Consumes: 当前 README 的安装、最短 CLI 示例、Docker 部署入口和项目名称。
- Produces: 文档导航、首次运行指南，以及指向后续主题文档的稳定链接。

- [ ] **Step 1: 从当前 README 和 CLI 实现整理首次运行事实**

  核对 Python 版本、安装 extras、最小环境变量、`.env.example`、`storyteller generate`、`--dry-run`、输出目录和 Docker 入口。使用：

  ```bash
  rg -n "python_requires|optional-dependencies|STORYTELLER_|generate|dry-run|Docker" pyproject.toml README.md .env.example docs/deployment-docker.md src/storyteller/cli/main.py
  ```

- [ ] **Step 2: 编写 `docs/getting-started.md`**

  包含本地安装、最小配置、第一次生成、只生成剧本、Web 启动、产物位置和凭据安全说明；所有命令必须来自当前脚本或 README 可验证示例。

- [ ] **Step 3: 编写 `docs/index.md`**

  按“第一次使用、日常使用、理解内部机制、部署与排障、开发贡献”提供阅读路径，并链接当前存在的 `docs/deployment-docker.md` 与 `docs/reference/tts/`。

- [ ] **Step 4: 收缩 README 并保留入口链接**

  README 保留项目简介、核心能力、最短安装/生成示例、Docker 快速入口、支持 Provider 概览、文档索引和开发测试入口；暂不删除无法在第一批文档中准确迁移的段落，迁移时逐段核对。

- [ ] **Step 5: 校验 Markdown 链接和命令引用**

  ```bash
  git diff --check
  rg -n "\]\([^)]*\)" README.md docs/index.md docs/getting-started.md
  .venv/bin/python -m pytest tests/e2e/test_cli.py tests/e2e/test_pipeline.py -q
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add README.md docs/index.md docs/getting-started.md
  git commit -m "docs: add documentation entry points"
  ```

### Task 2: 编写配置和 CLI 参考文档

**Files:**
- Create: `docs/configuration.md`
- Create: `docs/cli.md`
- Modify: `docs/index.md`
- Reference: `src/storyteller/core/config.py`, `src/storyteller/core/runtime_settings.py`, `src/storyteller/cli/main.py`, `src/storyteller/cli/interactive.py`, `.env.example`, `tests/unit/test_config.py`, `tests/unit/test_runtime_settings.py`

**Interfaces:**
- Consumes: Task 1 的文档导航和首次运行术语。
- Produces: 配置来源/优先级说明、完整 CLI 命令参考和参数行为说明。

- [ ] **Step 1: 建立配置交叉核对表**

  对照 `Config`、runtime settings schema、CLI parser 和 `.env.example`，逐项记录变量名、默认值、是否敏感、是否可运行时修改、是否需要重启；特别覆盖 LLM、TTS 多 provider/模型、音效、Web、数据目录、TTS scheduler 和主持人音色。

- [ ] **Step 2: 编写 `docs/configuration.md`**

  章节固定为：配置来源和优先级、`.env` 示例、LLM、TTS、音效、Web、安全、目录与缓存、调度器、运行时设置、配置生效时机、敏感信息处理、配置故障排查。解释 provider、model、voice_id、resource id 的项目语义，但不替代 Provider 文档。

- [ ] **Step 3: 从 argparse 和交互式入口编写 `docs/cli.md`**

  覆盖 `generate`、`continue`、`list-projects`、`list-voices`、`make-sound`、`list-sounds` 以及交互式向导；每个参数给出默认值、可选值、与环境变量的关系和一个可运行示例。

- [ ] **Step 4: 运行配置和 CLI 回归测试**

  ```bash
  .venv/bin/python -m pytest tests/unit/test_config.py tests/unit/test_runtime_settings.py tests/e2e/test_cli.py -q
  rg -n "STORYTELLER_[A-Z0-9_]+|--[a-z0-9-]+" docs/configuration.md docs/cli.md
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add docs/configuration.md docs/cli.md docs/index.md
  git commit -m "docs: document configuration and cli"
  ```

### Task 3: 编写 Web 使用和 API 入口文档

**Files:**
- Create: `docs/web.md`
- Create: `docs/api/overview.md`
- Create: `docs/api/settings.md`
- Modify: `docs/index.md`
- Reference: `src/storyteller/web/app.py`, `src/storyteller/web/routes_auth.py`, `src/storyteller/web/routes_options.py`, `src/storyteller/web/routes_settings.py`, `src/storyteller/web/routes_stories.py`, `web/frontend/` or bundled static assets, `tests/web/test_web_api.py`, `tests/unit/test_routes_settings.py`

**Interfaces:**
- Consumes: Task 1 的首次运行路径和 Task 2 的配置命名。
- Produces: 用户可执行的 Web 操作指南，以及设置/认证/故事相关 API 的当前行为说明。

- [ ] **Step 1: 从路由注册和响应模型生成 API 清单**

  使用 `src/storyteller/web/app.py` 和 `src/storyteller/web/routes_*.py` 记录认证、options、settings、stories、voices、voice clips、WebSocket 的路径、方法、认证要求、请求字段、响应字段和错误状态；不凭 README 推测不存在的接口。

- [ ] **Step 2: 编写 `docs/web.md`**

  覆盖登录/首次设置、故事生成、LLM/TTS 模型持久化、角色卡片、音色信息浮层、试听片段、音色管理、启用/禁用、年龄编辑、状态筛选、进度和失败恢复。说明前端持久化与后端运行时设置的边界。

- [ ] **Step 3: 编写 API 总览和 settings API 文档**

  `docs/api/overview.md` 说明认证、错误格式、路径分组和本地访问；`docs/api/settings.md` 给出当前 settings/options/history/reset/provider-test 相关请求和响应示例，敏感字段使用掩码或占位符。

- [ ] **Step 4: 用 Web 测试核对文档示例**

  ```bash
  .venv/bin/python -m pytest tests/web/test_web_api.py tests/unit/test_routes_settings.py tests/unit/test_web_config.py -q
  rg -n "@app\.|@router\.|Route\(" src/storyteller/web
  git diff --check
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add docs/web.md docs/api/overview.md docs/api/settings.md docs/index.md
  git commit -m "docs: document web usage and settings api"
  ```

### Task 4: 编写角色音色匹配和音色管理文档

**Files:**
- Create: `docs/voice-matching.md`
- Create: `docs/voice-management.md`
- Create: `docs/api/voices.md`
- Modify: `docs/index.md`
- Reference: `src/storyteller/core/voice_matcher.py`, `src/storyteller/core/voice_overrides.py`, `src/storyteller/providers/registry.py`, `src/storyteller/web/voice_catalog.py`, `src/storyteller/web/routes_voices.py`, `src/storyteller/web/routes_options.py`, `tests/unit/test_voice_matcher.py`, `tests/unit/test_voice_overrides.py`, `tests/unit/test_voice_catalog.py`, `tests/web/test_voice_management_api.py`

**Interfaces:**
- Consumes: Task 2 的配置术语和 Task 3 的 Web/API 结构。
- Produces: 当前候选池和音色管理行为的正式说明，以及完整 voices API 参考。

- [ ] **Step 1: 画出当前匹配数据流**

  按代码记录角色输入、性别/年龄硬约束、年龄数组、旁白规则、偏好/分类排序、禁用音色过滤、候选池采样、LLM 提示词、结果校验、重复分配和 fallback；注明每一步的函数或类入口。

- [ ] **Step 2: 编写 `docs/voice-matching.md`**

  给出一个包含 narrator、儿童角色和中年角色的候选池示例，解释为什么角色年龄和性别必须来自剧本，为什么 provider/model 不应成为匹配逻辑的硬编码条件，以及候选池/提示词/模型结果日志如何串联。

- [ ] **Step 3: 编写 `docs/voice-management.md`**

  说明 provider、模型、性别、年龄、分类、标签、描述和启用状态筛选；年龄数组编辑；试听片段来源；音色禁用对匹配/列表的影响；本地 override 文件的持久化、备份和恢复。

- [ ] **Step 4: 编写 `docs/api/voices.md`**

  记录音色列表、status 筛选、年龄/启用状态 PATCH、试听片段列表和音频下载/播放接口；为每个接口提供请求、响应、错误和鉴权示例。

- [ ] **Step 5: 运行音色相关测试并核对字段**

  ```bash
  .venv/bin/python -m pytest tests/unit/test_voice_matcher.py tests/unit/test_voice_overrides.py tests/unit/test_voice_catalog.py tests/web/test_voice_management_api.py -q
  rg -n "enabled|age|category|description|clip|voice_id|model" src/storyteller/web src/storyteller/core/voice_matcher.py
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add docs/voice-matching.md docs/voice-management.md docs/api/voices.md docs/index.md
  git commit -m "docs: document voice matching and management"
  ```

### Task 5: 编写架构、故事生成、流式 TTS 和音效文档

**Files:**
- Create: `docs/architecture.md`
- Create: `docs/story-generation.md`
- Create: `docs/streaming-tts.md`
- Create: `docs/sound-effects.md`
- Create: `docs/api/websocket.md`
- Modify: `docs/index.md`
- Reference: `src/storyteller/core/pipeline.py`, `src/storyteller/core/story_generator.py`, `src/storyteller/core/project.py`, `src/storyteller/core/streaming_tts.py`, `src/storyteller/web/streaming.py`, `src/storyteller/web/tts_scheduler.py`, `src/storyteller/web/routes_ws.py`, `src/storyteller/core/sfx.py`, `src/storyteller/core/sound_library.py`, `tests/unit/test_story_generator.py`, `tests/unit/test_streaming_contract.py`, `tests/unit/test_tts_scheduler.py`, `tests/unit/test_sound_library.py`, `tests/web/test_websocket.py`

**Interfaces:**
- Consumes: Task 2 的配置命名、Task 4 的角色/音色术语。
- Produces: 从主题到音频产物的数据流、断点续作、实时 TTS、direction/context 和音效缓存的开发者说明。

- [ ] **Step 1: 根据模块和测试整理端到端数据流**

  明确剧本 JSON、角色 voice_config、台词 line、音频片段、项目状态、最终拼接音频、音效库之间的输入输出关系，并标出同步 CLI 与 Web 流式路径的分叉。

- [ ] **Step 2: 编写 `docs/architecture.md` 和 `docs/story-generation.md`**

  前者说明模块边界、Provider registry、项目持久化和依赖关系；后者说明剧本生成、角色匹配、TTS、混音、缓存、断点续作和失败恢复。

- [ ] **Step 3: 编写 `docs/streaming-tts.md` 和 `docs/api/websocket.md`**

  说明 line 的 `direction` 先于 `text` 的生成约定、缺少 direction 时的默认处理、`instruction/context_texts` 到各 Provider 的转换、WebSocket 生命周期、队列/并发/限速/背压/超时和事件格式。

- [ ] **Step 4: 编写 `docs/sound-effects.md`**

  说明声音提示、seed-audio provider、全局缓存 key、混音、项目产物和 `list-sounds`/`make-sound` 的使用方式。

- [ ] **Step 5: 运行核心流测试**

  ```bash
  .venv/bin/python -m pytest tests/unit/test_story_generator.py tests/unit/test_streaming_contract.py tests/unit/test_tts_scheduler.py tests/unit/test_sound_library.py tests/web/test_websocket.py -q
  git diff --check
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add docs/architecture.md docs/story-generation.md docs/streaming-tts.md docs/sound-effects.md docs/api/websocket.md docs/index.md
  git commit -m "docs: explain generation and streaming architecture"
  ```

### Task 6: 编写 Provider 适配文档

**Files:**
- Create: `docs/providers/overview.md`
- Create: `docs/providers/aliyun-tts.md`
- Create: `docs/providers/volcengine-tts.md`
- Create: `docs/providers/llm.md`
- Modify: `docs/index.md`
- Reference: `src/storyteller/providers/base.py`, `src/storyteller/providers/registry.py`, `src/storyteller/providers/aliyun/tts.py`, `src/storyteller/providers/volcengine/tts.py`, `src/storyteller/providers/volcengine/llm.py`, `src/storyteller/providers/openai_compatible/`, `docs/reference/tts/`

**Interfaces:**
- Consumes: Task 2 的 provider/model 配置、Task 4 的音色字段、Task 5 的流式 TTS 术语。
- Produces: 项目统一 Provider 抽象、阿里云/火山引擎适配差异、LLM 接入说明。

- [ ] **Step 1: 建立 Provider/模型/音色映射表**

  从 registry、Provider 实现和 voices JSON 记录 provider、模型、voice_id、resource id、endpoint、同步/流式能力；明确哪些字段是项目内部统一字段，哪些是厂商 API 字段。

- [ ] **Step 2: 编写 `docs/providers/overview.md`**

  解释新增 Provider 需要实现的接口、注册方式、能力边界、音色元数据和配置发现规则；明确匹配逻辑不应依赖特定 provider 或模型名称。

- [ ] **Step 3: 编写阿里云和火山引擎文档**

  阿里云文档覆盖模型白名单、workspace、HTTP/WebSocket 地址、instruction/context 的项目映射和 Qwen/CosyVoice 差异；火山文档覆盖 model/resource id、WebSocket 会话参数、direction/context 的映射、同步/流式接口和常见错误。每个厂商差异都链接到对应 `docs/reference/tts/` 原始资料。

- [ ] **Step 4: 编写 `docs/providers/llm.md`**

  覆盖 LLM provider 选择、模型配置、OpenAI-compatible 约定、角色匹配提示词和响应校验；不重复 voice-matching 的候选池规则。

- [ ] **Step 5: 用 provider 测试和静态字段核对文档**

  ```bash
  .venv/bin/python -m pytest tests/unit/test_provider_abstractions.py tests/unit/test_registry.py tests/unit/test_aliyun_tts.py tests/unit/test_streaming_contract.py -q
  rg -n "resource_id|voice_id|instruction|context_texts|direction|workspace" src/storyteller/providers docs/reference/tts
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add docs/providers docs/index.md
  git commit -m "docs: document provider integrations"
  ```

### Task 7: 编写日志、排障、数据、部署和开发发布文档

**Files:**
- Create: `docs/operations/logging.md`
- Create: `docs/operations/troubleshooting.md`
- Create: `docs/operations/data-and-backup.md`
- Create: `docs/deployment/docker.md`
- Create: `docs/deployment/production.md`
- Create: `docs/development.md`
- Create: `docs/release.md`
- Modify: `docs/deployment-docker.md`, `docs/index.md`
- Reference: `src/storyteller/core/observability.py`, `src/storyteller/web/`, `scripts/build_and_push_docker.sh`, `Dockerfile`, `docker-compose.yml`, `.github/`, `tests/unit/test_logging.py`, `tests/unit/test_observability.py`

**Interfaces:**
- Consumes: 前六个任务定义的术语、路径、API、Provider 和数据流。
- Produces: 可执行的本地/容器运维手册、开发贡献说明和发布流程。

- [ ] **Step 1: 核对日志事件和日志文件路径**

  从 observability、CLI/Web 启动方式和测试记录 `job_id`、`project_id`、`session_id`、候选池、完整 prompt、LLM 结果、底层 TTS session 参数以及异常日志的真实字段和位置。

- [ ] **Step 2: 编写三份 operations 文档**

  `logging.md` 给出检索示例；`troubleshooting.md` 按认证、模型/resource id、音色过滤、WebSocket、音频/ffmpeg、Docker 启动失败分类；`data-and-backup.md` 说明项目状态、片段、音色 override、音效缓存和恢复边界。

- [ ] **Step 3: 整理 Docker 文档**

  `docs/deployment/docker.md` 说明多架构构建/推送脚本、平台参数、运行时卷挂载和配置注入；将 `docs/deployment-docker.md` 改成兼容入口或迁移说明，避免两个文档出现冲突的命令。

- [ ] **Step 4: 编写生产、开发和发布文档**

  生产文档覆盖反向代理、密码/secret、持久化和资源限制；开发文档覆盖 Python/前端依赖、测试、静态资源构建；发布文档覆盖版本提交、GitHub push、Docker Hub 镜像标签和发布前验证。

- [ ] **Step 5: 运行验证命令**

  ```bash
  .venv/bin/python -m pytest tests/unit/test_logging.py tests/unit/test_observability.py -q
  git diff --check
  test -x scripts/build_and_push_docker.sh
  rg -n "storyteller\.log|job_id|project_id|session_id|docker buildx|docker push" docs/operations docs/deployment docs/development.md docs/release.md
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add docs/operations docs/deployment docs/development.md docs/release.md docs/deployment-docker.md docs/index.md
  git commit -m "docs: add operations deployment and release guides"
  ```

### Task 8: 全量事实核对和文档收口

**Files:**
- Modify: `README.md`, `docs/index.md`, all newly created topic documents as needed
- Test/validation: all `tests/`, Markdown links and referenced commands

**Interfaces:**
- Consumes: Tasks 1–7 的所有主题文档。
- Produces: 与当前代码一致、链接完整、可交接维护的文档集合。

- [ ] **Step 1: 检查 README 是否仍重复维护细节**

  对照 `docs/index.md`，把已迁移完成的长章节改为摘要和链接；保留最短可运行示例、项目定位和关键警告。

- [ ] **Step 2: 检查配置、API、字段和路径一致性**

  用以下命令找出文档中的配置和 API 词条，逐项回到代码确认：

  ```bash
  rg -n "STORYTELLER_|/api/|WebSocket|voice_id|resource_id|model|enabled|age|direction|context_texts" README.md docs
  rg -n "@app\.|@router\.|Route\(" src/storyteller/web
  ```

- [ ] **Step 3: 检查链接、代码块和敏感信息**

  ```bash
  git diff --check
  rg -n "sk-|api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9]" README.md docs .env.example || true
  ```

  对相对链接逐个确认目标存在；代码块中的命令不得依赖未说明的当前目录、环境变量或服务状态。

- [ ] **Step 4: 运行完整测试集和前端构建**

  ```bash
  .venv/bin/python -m pytest -q
  cd web/frontend && npm test -- --run && npm run build
  ```

- [ ] **Step 5: 进行最终 review**

  按 spec 的目标、非目标、验收标准逐项记录结果；发现文档与代码冲突时以代码/测试为准修正文档，并在提交说明中列出无法自动验证的厂商行为。

- [ ] **Step 6: Commit**

  ```bash
  git add README.md docs
  git commit -m "docs: align documentation with current implementation"
  ```
