# Runtime Settings Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为单实例部署增加受保护的运行时配置后台，使管理员能够维护 Web、LLM、TTS 和音效配置，并让保存后的配置立即用于新任务。

**Architecture:** 增加一个独立的运行时配置服务，按“后台覆盖 > 环境变量 > 默认值”合并配置，并以原子 JSON 文件持久化后台覆盖项。应用启动时创建配置管理器；新任务创建时获取不可变配置快照，现有任务不受后续修改影响。FastAPI 提供认证后的配置 API，Vue 页面负责分组编辑、脱敏展示和连接测试。

**Tech Stack:** Python 3.11、FastAPI、现有 Config 配置系统、JSON 文件数据卷、Vue 3、TypeScript、Vitest、pytest、Docker Compose。

**Spec:** `docs/superpowers/specs/2026-09-14-runtime-settings-management-design.md`

## Global Constraints

- 配置优先级固定为：后台已保存配置 > 环境变量 > 程序默认值。
- API Key、Web Secret 和访问密码不得通过 GET 接口返回完整值，也不得写入日志。
- 配置覆盖文件保存于数据目录 `/data/config/settings.json`，并使用原子写入。
- 配置修改只影响新任务；已运行任务继续使用任务启动时的配置快照。
- 监听地址、容器端口和数据目录只读展示，不允许从后台修改。
- 不修改宿主机 `.env`，不把密钥写入 Docker 镜像或前端 localStorage。
- 每个任务完成一个独立交付后运行对应测试；所有任务完成后运行完整测试和前端构建。

## 文件结构

- Create: `src/storyteller/core/runtime_settings.py` — 后台覆盖的读写、合并、脱敏和配置快照。
- Modify: `src/storyteller/core/config.py` — 复用现有环境变量解析逻辑，并为运行时配置提供结构化 schema/序列化入口。
- Modify: `src/storyteller/web/app.py` — 创建并挂载运行时配置服务，注入路由和任务工厂。
- Create: `src/storyteller/web/routes_settings.py` — 配置读取、更新、重置、连接测试和历史接口。
- Modify: `src/storyteller/web/streaming.py`, `src/storyteller/web/jobs.py` — 在任务开始处绑定配置快照。
- Modify: `src/storyteller/web/routes_auth.py` 或现有认证依赖位置 — 复用统一登录认证保护配置 API。
- Create: `tests/unit/test_runtime_settings.py` — 配置优先级、原子写入、脱敏、损坏回退和快照测试。
- Create: `tests/unit/test_routes_settings.py` — 配置 API、认证、校验和连接测试接口测试。
- Create: `web/frontend/src/views/SettingsView.vue` — 配置后台页面。
- Modify: `web/frontend/src/api.ts`, `web/frontend/src/types.ts`, `web/frontend/src/router.ts`, `web/frontend/src/App.vue` — API 类型、路由和导航入口。
- Modify: `web/frontend/src/styles.css` — 配置页面布局、表单、脱敏字段和状态样式。
- Modify: `docker-compose.yml` — 使用 Docker Hub 镜像时保留 `.env` 注入和 `/data` 持久化。
- Modify: `.env.example`, `docs/deployment-docker.md` — 说明配置后台和首次部署流程。

### Task 1: 建立运行时配置模型与持久化服务

**Files:**
- Create: `src/storyteller/core/runtime_settings.py`
- Modify: `src/storyteller/core/config.py`
- Test: `tests/unit/test_runtime_settings.py`

**Interfaces:**
- `RuntimeSettingsStore(data_dir: str | Path, env_config: Config)`：管理后台覆盖文件。
- `RuntimeSettingsStore.snapshot() -> RuntimeSettingsSnapshot`：返回当前合并配置的不可变快照。
- `RuntimeSettingsStore.public_snapshot() -> dict`：返回脱敏后的分组配置和来源。
- `RuntimeSettingsStore.update(patch: dict) -> RuntimeSettingsSnapshot`：校验并原子保存部分更新。
- `RuntimeSettingsStore.reset(paths: list[str]) -> RuntimeSettingsSnapshot`：删除指定后台覆盖并重新合并。
- `RuntimeSettingsSnapshot.to_config() -> Config`：生成任务可使用的配置对象。

- [ ] **Step 1: 写配置优先级和脱敏行为的失败测试**

测试覆盖：后台值覆盖环境值；未覆盖字段继续使用环境值；没有环境值时使用默认值；敏感字段的 public snapshot 只返回 `configured` 和脱敏尾部；更新空值不会意外清空已有密钥，显式 reset 才会清空。

- [ ] **Step 2: 运行测试确认初始失败**

Run: `pytest tests/unit/test_runtime_settings.py -q`

Expected: FAIL，因为运行时配置模块尚未存在。

- [ ] **Step 3: 实现配置模型和原子持久化**

实现 JSON 覆盖文件格式，顶层按 `web`、`llm`、`tts`、`sound` 分组；只保存后台覆盖字段。写入时创建 `/data/config`，使用临时文件、`flush`、`fsync`、`os.replace`。文件不存在时返回空覆盖；JSON 损坏时保留环境配置并向上层返回明确的 `config_error` 状态。

- [ ] **Step 4: 运行单元测试确认通过**

Run: `pytest tests/unit/test_runtime_settings.py -q`

Expected: PASS，覆盖优先级、脱敏、重置、原子写入和损坏文件行为。

- [ ] **Step 5: 提交独立变更**

```bash
git add src/storyteller/core/runtime_settings.py src/storyteller/core/config.py tests/unit/test_runtime_settings.py
git commit -m "feat: add runtime settings store"
```

### Task 2: 接入应用生命周期和任务配置快照

**Files:**
- Modify: `src/storyteller/web/app.py`
- Modify: `src/storyteller/web/streaming.py`
- Modify: `src/storyteller/web/jobs.py`
- Test: `tests/unit/test_runtime_settings.py`, `tests/unit/test_web_jobs.py`（若现有文件不存在则创建）

**Interfaces:**
- `app.state.runtime_settings: RuntimeSettingsStore`
- `Job.config_snapshot: RuntimeSettingsSnapshot | None`
- `JobManager.submit(job, target, config_snapshot=None)`：提交时绑定快照。

- [ ] **Step 1: 写配置快照隔离测试**

创建任务 A，绑定旧快照；更新运行时配置；创建任务 B，绑定新快照；断言 A 的 provider/model/并发相关配置不变，B 使用新值。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/test_runtime_settings.py tests/unit/test_web_jobs.py -q`

Expected: 新增快照测试 FAIL。

- [ ] **Step 3: 接入应用状态和新任务快照**

应用创建时使用当前 `Config` 初始化 `RuntimeSettingsStore`。故事生成路由创建 Job 后立即调用 `snapshot()`，将快照放入 Job；streaming worker 和 pipeline 使用 Job 快照，不在执行中重新读取全局环境变量。保留现有 CLI 启动参数对 host/port 的覆盖行为。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/unit/test_runtime_settings.py tests/unit/test_web_jobs.py -q`

Expected: PASS，已有 JobManager 测试不回归。

- [ ] **Step 5: 提交独立变更**

```bash
git add src/storyteller/web/app.py src/storyteller/web/streaming.py src/storyteller/web/jobs.py tests/unit/test_runtime_settings.py tests/unit/test_web_jobs.py
git commit -m "feat: bind runtime config snapshots to jobs"
```

### Task 3: 实现配置 API 和 Provider 连接测试

**Files:**
- Create: `src/storyteller/web/routes_settings.py`
- Modify: `src/storyteller/web/app.py`
- Modify: `src/storyteller/web/routes_auth.py` 或现有认证依赖模块
- Create: `tests/unit/test_routes_settings.py`

**Interfaces:**
- `GET /api/settings`
- `PATCH /api/settings`
- `POST /api/settings/test/llm`
- `POST /api/settings/test/tts`
- `POST /api/settings/reset`
- `GET /api/settings/history`

- [ ] **Step 1: 写 API 失败测试**

测试未认证请求返回 `401/403`；GET 返回分组、来源和脱敏状态；PATCH 只更新允许字段；敏感值不出现在响应；reset 能回退到环境变量；连接测试超时或 Provider 错误返回安全的错误信息。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/test_routes_settings.py -q`

Expected: FAIL，因为路由尚未注册。

- [ ] **Step 3: 实现配置路由**

复用现有 Web 登录依赖。PATCH 使用白名单 schema，拒绝未知字段和错误类型；敏感字段使用明确的替换标记或 `clear_secrets` 操作；连接测试只使用请求中的临时配置，不写入持久化文件；限制测试请求超时并过滤供应商异常中的密钥片段。

- [ ] **Step 4: 注册路由并运行测试**

Run: `pytest tests/unit/test_routes_settings.py -q`

Expected: PASS，API 认证、脱敏、校验、回退和测试接口全部通过。

- [ ] **Step 5: 提交独立变更**

```bash
git add src/storyteller/web/routes_settings.py src/storyteller/web/app.py src/storyteller/web/routes_auth.py tests/unit/test_routes_settings.py
git commit -m "feat: add runtime settings api"
```

### Task 4: 实现配置后台页面

**Files:**
- Create: `web/frontend/src/views/SettingsView.vue`
- Modify: `web/frontend/src/api.ts`
- Modify: `web/frontend/src/types.ts`
- Modify: `web/frontend/src/router.ts`
- Modify: `web/frontend/src/App.vue`
- Modify: `web/frontend/src/styles.css`
- Test: `web/frontend/src/views/SettingsView.test.ts`

**Interfaces:**
- `getSettings(): Promise<SettingsResponse>`
- `patchSettings(patch: SettingsPatch): Promise<SettingsResponse>`
- `testSettings(kind, payload): Promise<ConnectionTestResult>`
- `resetSettings(paths): Promise<SettingsResponse>`

- [ ] **Step 1: 写前端交互失败测试**

覆盖：配置分组渲染；敏感字段显示脱敏占位符；保存调用 PATCH；测试连接显示成功/失败；重置需要确认；未保存离开页面显示提示；保存后展示“已对新任务生效”。

- [ ] **Step 2: 运行前端测试确认失败**

Run: `cd web/frontend && npm test -- --run src/views/SettingsView.test.ts`

Expected: FAIL，因为页面和 API 类型尚未实现。

- [ ] **Step 3: 实现 API 类型和 SettingsView**

页面分为 Web、LLM、TTS、音效四个可折叠区块。每个字段显示来源和配置状态；API Key 使用密码输入并保持空值不提交；Endpoint、模型、Provider 等普通字段可编辑；监听地址、端口、数据目录只读。保存按分组发送，测试连接使用当前表单值但不自动保存。

- [ ] **Step 4: 加入路由和导航入口**

增加 `/settings` 路由和后台导航入口，保持现有登录守卫和页面风格。

- [ ] **Step 5: 运行前端测试和构建**

Run: `cd web/frontend && npm test -- --run src/views/SettingsView.test.ts && npm run build`

Expected: PASS，构建生成新的静态资源。

- [ ] **Step 6: 提交独立变更**

```bash
git add web/frontend/src/views/SettingsView.vue web/frontend/src/views/SettingsView.test.ts web/frontend/src/api.ts web/frontend/src/types.ts web/frontend/src/router.ts web/frontend/src/App.vue web/frontend/src/styles.css
git commit -m "feat: add settings management page"
```

### Task 5: 完善 Docker 部署和文档

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `docs/deployment-docker.md`
- Test: `tests/integration/test_settings_persistence.py`（如现有 Docker 集成测试结构支持则加入；否则使用配置服务集成测试）

**Interfaces:**
- Docker Hub 镜像：`lizhe2004/audio-story-generator:latest`
- 配置覆盖持久化路径：`/data/config/settings.json`

- [ ] **Step 1: 写部署配置验证**

验证 Compose 使用 `.env`，容器环境中 `STORYTELLER_DATA_DIR=/data`，数据卷挂载到 `/data`；删除并重新创建容器后，后台配置文件仍存在。

- [ ] **Step 2: 更新 Compose 和环境变量示例**

将镜像配置切换为 Docker Hub 镜像模式，并在 `.env.example` 增加 Web 配置说明、配置后台优先级和敏感值注意事项。保留本地 `build` 方式的说明作为开发路径，而不是和发布 Compose 混用。

- [ ] **Step 3: 更新部署文档**

说明另一台电脑的最小部署流程：准备 Compose 文件、复制 `.env.example`、填写密钥、`docker compose pull`、`docker compose up -d`、访问 `/settings` 修改配置、查看日志和数据卷备份。

- [ ] **Step 4: 运行部署相关验证**

Run: `docker compose config`

Expected: Compose 配置解析成功，环境变量和卷映射正确；如果 Docker Hub 或 Docker daemon 不可用，至少完成静态配置校验并明确记录阻塞原因。

- [ ] **Step 5: 提交独立变更**

```bash
git add docker-compose.yml .env.example docs/deployment-docker.md
git commit -m "docs: document runtime settings deployment"
```

### Task 6: 全量验证与交付检查

**Files:**
- Modify: only files required by verification failures.
- Test: backend and frontend test suites.

- [ ] **Step 1: 运行后端全量测试**

Run: `pytest -q`

Expected: 全部通过。

- [ ] **Step 2: 运行前端全量测试和构建**

Run: `cd web/frontend && npm test -- --run && npm run build`

Expected: 全部通过，Vite 构建成功。

- [ ] **Step 3: 检查敏感信息和格式**

Run: `git diff --check && rg -n "API_KEY|WEB_SECRET|WEB_PASSWORDS" src/storyteller/web web/frontend/src --glob '*.py' --glob '*.ts' --glob '*.vue'`

Expected: 没有日志打印完整敏感值，前端没有硬编码密钥。

- [ ] **Step 4: 验证 Compose 配置**

Run: `docker compose config`

Expected: 配置成功解析，数据卷和环境变量路径正确。

- [ ] **Step 5: 汇总交付结果**

记录新增 API、配置文件路径、部署命令、测试结果和任何需要手工完成的 Docker Hub 登录/推送步骤。
