# 项目文档体系改造设计

## 状态

提案，等待确认后实施。

## 背景

当前项目的 README 已经包含安装、配置、CLI、音色匹配、实时 TTS、Provider 和架构等大量内容；`docs/reference/tts/` 主要保存阿里云、火山引擎的原始参考资料；`docs/superpowers/` 保存历史设计和实施记录。随着 Web 音色管理、音色启用状态、运行时配置、多 Provider/多模型、流式 TTS 和 Docker 部署能力不断增加，正式使用文档已经落后于代码，并且用户难以区分：

- 项目如何使用；
- 本项目如何抽象和调用各家 Provider；
- 当前代码实际支持哪些配置和 API；
- 原始厂商文档中的能力是否已经被项目实现。

本次改造采用方案 B：README 保持入口和快速开始，详细内容拆成按主题维护的文档。

## 目标

1. 新用户能够从 README 在几分钟内完成安装、配置并生成第一个故事。
2. 使用者能够查到当前代码实际支持的配置、CLI、Web 功能和音色管理流程。
3. 开发者能够理解故事生成、角色/音色匹配、TTS 调度、Provider 适配和数据持久化之间的边界。
4. 运维者能够查到日志位置、常见故障、Docker 部署、数据目录和备份方式。
5. 阿里云、火山引擎等厂商原始资料与项目适配说明分开维护，避免把厂商概念误认为项目内部概念。
6. 后续新增 Provider、模型、配置或 Web 功能时，有明确的文档更新位置。

## 非目标

- 本阶段不重写厂商原始参考资料，不把 `docs/reference/tts/` 改造成项目 API 文档。
- 本阶段不引入 MkDocs、Docusaurus 等文档站点生成系统。
- 本阶段不从代码自动生成全部文档；API 自动化校验作为后续增强项。
- 本阶段不删除 `docs/superpowers/` 中的历史 spec/plan，它们保留为开发过程记录。

## 信息架构

```text
README.md                         项目简介、快速开始、文档入口

docs/
  index.md                        文档导航和阅读路径
  getting-started.md              安装、首次配置、第一次生成
  configuration.md                配置来源、优先级、完整配置项
  cli.md                          CLI 命令和参数
  web.md                          Web 登录、故事生成和页面功能
  architecture.md                 核心模块和数据流
  story-generation.md             剧本生成、项目状态和断点续作
  voice-matching.md               角色信息、候选池、匹配和回退策略
  voice-management.md             音色目录、试听、筛选、年龄编辑、启用状态
  streaming-tts.md                流式台词生成、direction 和上下文处理
  sound-effects.md                音效生成、缓存和混音
  providers/
    overview.md                   Provider/模型/音色的项目抽象
    aliyun-tts.md                 阿里云项目适配和限制
    volcengine-tts.md             火山引擎项目适配和限制
    llm.md                        LLM Provider 与模型配置
  api/
    overview.md                   API 约定和认证
    settings.md                   配置相关 API
    voices.md                     音色管理 API
    websocket.md                  流式 WebSocket 协议
  deployment/
    docker.md                     Docker 和多平台镜像
    production.md                 生产部署建议
  operations/
    logging.md                    日志字段、位置和检索方式
    troubleshooting.md            常见故障排查
    data-and-backup.md            数据目录、缓存和备份
  development.md                  本地开发、测试和前端构建
  release.md                      版本、镜像和发布流程
```

## 各文档的内容边界

### README.md

只保留项目定位、核心能力摘要、最短安装/配置/生成示例、Docker 快速入口、支持能力概览和详细文档链接。现有 README 中较长的 CLI 参数表、完整环境变量表、Provider 细节、实时 TTS 说明和架构说明迁移到对应主题文档。

### configuration.md

必须说明：

- 环境变量、`.env`、CLI 参数、Web 运行时设置的来源和优先级；
- LLM、TTS、音效的 Provider 与模型配置方式；
- TTS 多 Provider、多模型、多音色的关系；
- 阿里云模型配置、火山引擎 resource id 的项目语义；
- Web 密码、secret、数据目录、并发/限速/超时配置；
- 配置变更何时生效，哪些任务会读取已保存设置，哪些需要重启。

所有配置项以当前代码为准，示例不得包含真实密钥。

### voice-matching.md

必须说明：

- 剧本生成的角色性别、年龄和音色偏好如何进入后续匹配；
- 年龄数组、相邻年龄覆盖、旁白的特殊处理；
- 候选池的性别、年龄、分类/偏好、禁用状态筛选策略；
- LLM 匹配与 rule 匹配的区别、硬约束和回退策略；
- Provider、模型不会被写死为匹配规则，新增 Provider/模型只需提供标准音色元数据；
- LLM 输出非法、重复或越界时如何处理；
- 候选池、完整提示词、模型结果和最终分配日志如何关联。

### voice-management.md

必须说明音色管理页面的真实能力：

- 音色列表及 provider、模型、性别、年龄、分类、标签、描述筛选；
- 启用/禁用状态筛选和状态修改；
- 年龄数组编辑；
- 音色详情和试听片段来源；
- 试听片段不存在、生成失败或多个模型使用相同音色标识时的展示方式；
- 修改属于本地覆盖数据，如何持久化、备份和恢复。

### providers/ 目录

项目适配文档与 `docs/reference/tts/` 原始资料分开。每个 Provider 文档应说明：

- 项目中的 provider 名、模型名、voice_id/resource id 映射；
- 鉴权和 endpoint 配置；
- 普通 HTTP、流式 HTTP、WebSocket 的调用路径；
- `direction`、`instruction`、`context_texts` 等概念在项目中的统一表示和 Provider-specific 转换；
- 不支持或行为不同的能力；
- 常见错误及对应的原始厂商文档链接。

### operations/ 目录

必须覆盖：

- CLI/Web 日志文件位置和 Docker 日志查看方式；
- `job_id`、`project_id`、`session_id` 等关联字段；
- 角色候选池、完整匹配提示词、LLM 匹配结果、底层 TTS session 参数的日志事件；
- 鉴权、模型、resource id、WebSocket、音频缓存和 ffmpeg 常见问题；
- `.storyteller` 数据目录中项目状态、音频片段、音色覆盖和音效缓存的用途与备份策略。

## README 与主题文档的维护关系

- README 是入口，不重复维护完整细节。
- 主题文档是用户操作和当前实现的正式说明。
- `docs/reference/tts/` 是厂商原始资料，引用时注明“厂商能力”或“项目已实现能力”。
- `docs/superpowers/specs/` 和 `docs/superpowers/plans/` 是历史设计/实施记录，不作为当前行为的唯一依据。
- 代码、测试和运行时行为是事实来源；文档描述应以它们为准。

## 文档更新规则

以下改动必须在同一提交中更新对应文档：

- 新增/删除/改名配置项；
- 新增 Provider、模型、音色字段或匹配规则；
- 修改 CLI、Web 页面、API 或 WebSocket 协议；
- 修改数据目录、日志字段、缓存或恢复行为；
- 修改 Docker 构建、发布或运行方式。

每份主题文档应尽量包含“适用范围、最小示例、配置/输入、输出/结果、故障排查、相关代码入口”这几个部分。涉及 API 的文档要给出请求方法、路径、参数、响应示例和错误行为。

## 实施顺序

### 第一批：用户最常查且当前差距最大

1. `docs/index.md`
2. `docs/getting-started.md`
3. `docs/configuration.md`
4. `docs/web.md`
5. `docs/voice-matching.md`
6. `docs/voice-management.md`

### 第二批：开发和故障排查

1. `docs/architecture.md`
2. `docs/streaming-tts.md`
3. `docs/providers/overview.md`
4. `docs/providers/aliyun-tts.md`
5. `docs/providers/volcengine-tts.md`
6. `docs/api/voices.md`
7. `docs/operations/logging.md`

### 第三批：交付和长期维护

1. `docs/cli.md`
2. `docs/story-generation.md`
3. `docs/sound-effects.md`
4. `docs/api/` 其余文档
5. `docs/deployment/`、`docs/operations/troubleshooting.md`
6. `docs/development.md`、`docs/release.md`

## 验收标准

- README 能够在不阅读长篇细节的情况下完成首次运行，并链接到所有主题文档。
- 文档中列出的环境变量、CLI 参数、API 路径和页面能力都能在当前代码中找到对应实现或测试。
- 用户可以仅通过文档回答：如何配置多个 TTS provider/模型、如何禁用音色、如何修改年龄、如何查看试听片段、如何定位一次音色匹配和一次 TTS 请求。
- Provider 文档明确区分项目统一抽象与阿里云/火山引擎的厂商差异。
- Docker、日志、数据目录和备份文档能够覆盖本地与部署场景。
- 后续功能提交有明确的文档更新位置，不再把所有内容堆回 README。

## 待确认事项

本 spec 只确定文档结构和内容边界，不决定是否引入文档站点生成器，也不要求一次性完成所有文档。确认后按三批次逐步编写，并在每批次完成时用代码、测试和实际命令核对文档中的事实。
