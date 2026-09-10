# Storyteller 音频故事生成器 - 设计文档

**状态：** 设计完成（待审核）
**日期：** 2026-09-10

---

## 1. 项目概述

Storyteller 是一个音频故事生成工具，输入故事主题，输出带角色声音的音频故事/广播剧。

### 1.1 目标
- 从简单的故事主题生成完整的音频故事
- 支持多角色、多声音
- 可配置故事长度、复杂度
- 支持多种AI服务提供商
- 支持断点续传

### 1.2 MVP 范围

**包含：**
- CLI命令行工具（交互式 + 参数模式）
- 火山引擎LLM + TTS
- 角色声音自动匹配 + 手动选择
- 多TTS Provider支持（每个角色可用不同Provider）
- OpenAI兼容Provider（配置式添加）
- 输出多格式音频 + 剧本文本
- 项目保存/加载（断点续传）
- Claude Code技能集成

**暂不包含（后续版本）：**
- Web界面
- 背景音乐和音效（数据模型预留）
- 更多内置Provider（先专注火山引擎）

---

## 2. 架构设计

### 2.1 架构风格
经典分层架构，关注点分离。业务逻辑与Provider调用解耦。

### 2.2 组件职责

| 组件 | 职责 | 知道什么 | 不知道什么 |
|------|------|----------|------------|
| **Pipeline** | 协调整个故事生成流程 | 完整的流程步骤、项目状态 | 具体怎么调用API |
| **Story Generator** | 把主题变成剧本 | 故事结构、prompt怎么写 | 用什么LLM |
| **LLM Provider** | 跟大模型对话 | 输入文本、输出文本 | 什么是剧本 |
| **Voice Matcher** | 给角色分配合适的声音 | 角色描述、声音列表 | 具体怎么合成语音 |
| **TTS Provider** | 把文本变成音频文件 | 文本、声音配置 | 什么是角色 |
| **Audio Processor** | 音频拼接、格式转换 | 音频文件 | 什么是故事 |
| **Config** | 管理所有配置 | 环境变量、配置文件 | 业务逻辑 |
| **Project** | 保存/加载项目状态 | 项目文件格式 | 其他组件 |

### 2.3 数据流

```
用户主题 + 配置
     ↓
[Pipeline] 协调流程
     ↓
[Story Generator] 生成剧本
     ↑↓
[LLM Provider] 文本生成
     ↓
[Voice Matcher] 匹配声音
     ↑↓
[TTS Provider] 声音列表
     ↓
[TTS Provider] 生成音频片段
     ↓
[Audio Processor] 拼接+转换
     ↓
输出文件
```

### 2.4 目录结构

```
audio-story-generator/
├── storyteller/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py           # 数据模型
│   │   ├── llm.py              # LLM抽象接口
│   │   ├── tts.py              # TTS抽象接口
│   │   ├── audio_generator.py  # 音频生成抽象（预留）
│   │   ├── audio.py            # 音频处理抽象
│   │   ├── story_generator.py  # 剧本生成业务逻辑
│   │   ├── voice_matcher.py    # 声音匹配逻辑
│   │   ├── pipeline.py         # 流程编排
│   │   ├── config.py           # 配置管理
│   │   ├── exceptions.py       # 自定义异常
│   │   ├── project.py          # 项目状态保存/加载
│   │   ├── cache.py            # API缓存管理（预留）
│   │   ├── hooks.py            # 工作流钩子（预留）
│   │   └── utils.py            # 工具函数
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py             # Provider基类
│   │   ├── registry.py         # Provider注册中心
│   │   ├── volcengine/         # 火山引擎实现
│   │   │   ├── __init__.py
│   │   │   ├── llm.py
│   │   │   └── tts.py
│   │   └── openai_compatible/  # OpenAI兼容Provider
│   │       ├── __init__.py
│   │       ├── llm.py
│   │       └── tts.py
│   ├── templates/              # 内置故事模板
│   │   ├── __init__.py
│   │   └── default.py
│   ├── presets/                # 内置预设
│   │   ├── __init__.py
│   │   ├── characters.py
│   │   └── sounds.py
│   ├── exporters/              # 导出器（预留）
│   │   ├── __init__.py
│   │   └── base.py
│   └── cli/                    # 命令行界面
│       ├── __init__.py
│       ├── main.py             # CLI入口
│       └── interactive.py      # 交互式向导
├── skills/                     # Claude Code技能
│   └── storyteller/
│       └── skill.yaml
├── templates/                  # 用户自定义模板
├── presets/                    # 用户自定义预设
├── projects/                   # 项目保存目录
├── outputs/                    # 输出目录
├── examples/                   # 示例
├── tests/                      # 测试
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── .env.example
├── requirements.txt
└── README.md
```

---

## 3. 数据模型设计

### 3.1 核心概念

| 概念 | 说明 |
|------|------|
| **SoundEffect** | 音效/背景音乐 |
| **VoiceConfig** | TTS声音配置（含provider信息） |
| **CharacterPreset** | 角色预设 |
| **Character** | 故事中的角色 |
| **ScriptLine** | 剧本段落（对话或旁白） |
| **Script** | 完整剧本 |
| **StoryTemplate** | 可复用的故事模板 |
| **ScriptVersion** | 剧本版本（版本管理） |
| **ProjectState** | 项目当前状态 |

### 3.2 VoiceConfig 设计原则
- 包含 `provider` 字段，指定使用哪个TTS Provider
- 每个角色可以有不同的provider
- 支持跨provider的声音匹配

### 3.3 设计原则
- 预留音效和背景音乐字段（MVP不实现生成逻辑）
- 预留版本管理字段
- 支持序列化/反序列化（JSON/YAML）
- 所有数据模型可独立测试

---

## 4. Pipeline 流程设计

### 4.1 整体流程

```
1. 初始化阶段
   - 加载配置
   - 初始化Provider注册中心
   - 创建项目目录

2. 剧本生成阶段
   - 构建故事prompt
   - 调用LLM生成剧本
   - 解析为结构化Script对象
   - 保存剧本

3. 声音配置阶段
   - 获取所有已启用Provider的声音列表
   - 根据限制过滤可用声音
   - 自动匹配角色声音
   - （可选）用户手动调整
   - 保存声音配置

4. 音频生成阶段
   - 逐段调用对应Provider的TTS
   - （预留）生成音效/背景音乐
   - 显示实时进度

5. 后处理阶段
   - 拼接所有音频片段
   - 格式转换
   - 音量平衡
   - （预留）混音处理

6. 输出阶段
   - 保存最终音频文件
   - 保存剧本文本
   - 保存项目状态
   - 显示结果摘要
```

### 4.2 状态机

| 状态 | 说明 | 可转移到 |
|------|------|----------|
| `initialized` | 项目已创建 | `topic_collected` |
| `topic_collected` | 已收集主题和配置 | `script_generating` |
| `script_generating` | 正在生成剧本 | `script_generated` / `failed` |
| `script_generated` | 剧本已生成 | `voice_configuring` |
| `voice_configuring` | 正在配置声音 | `voice_configured` / `failed` |
| `voice_configured` | 声音已配置 | `generating_audio` |
| `generating_audio` | 正在生成音频 | `audio_generated` / `failed` |
| `audio_generated` | 音频片段已生成 | `post_processing` |
| `post_processing` | 正在后处理 | `completed` / `failed` |
| `completed` | 全部完成 | - |
| `failed` | 失败 | 可重试 |

### 4.3 设计原则
- **可中断**：每个阶段结束都保存状态，随时可以暂停
- **可重试**：失败的阶段可以重试，不用从头开始
- **可跳过**：已完成的阶段可以跳过
- **可观察**：每个步骤有清晰的进度反馈

---

## 5. 配置设计

### 5.1 配置层级

优先级从高到低：
```
命令行参数 > 环境变量 > 配置文件 > 默认值
```

### 5.2 配置分类

| 类别 | 说明 | 来源 |
|------|------|------|
| **全局配置** | 日志级别、输出目录、项目目录 | 环境变量 + 配置文件 |
| **Provider配置** | API Key、Endpoint、模型选择 | 环境变量（为主） |
| **故事配置** | 长度、复杂度、模板 | CLI参数 + 交互式 |
| **音频配置** | 格式、质量、音量 | CLI参数 + 配置文件 |
| **行为配置** | 严格/宽松模式、进度显示级别 | CLI参数 + 配置文件 |

### 5.3 多Provider支持

- 可以同时启用多个 LLM/TTS Provider
- 每个 Provider 有独立的配置
- Provider 可以单独启用/禁用
- 支持 OpenAI 兼容 Provider（通过配置添加，无需写代码）

### 5.4 环境变量示例

```bash
# ===== 全局配置 =====
STORYTELLER_OUTPUT_DIR=./outputs
STORYTELLER_PROJECT_DIR=./projects
STORYTELLER_LOG_LEVEL=info

# ===== LLM Provider =====
STORYTELLER_LLM_PROVIDERS=volcengine
STORYTELLER_LLM_DEFAULT_PROVIDER=volcengine

# 火山引擎 LLM
STORYTELLER_LLM_VOLCENGINE_API_KEY=xxx
STORYTELLER_LLM_VOLCENGINE_MODEL=xxx
STORYTELLER_LLM_VOLCENGINE_ENDPOINT=xxx

# ===== TTS Provider =====
STORYTELLER_TTS_PROVIDERS=volcengine,openai-compatible-1
STORYTELLER_TTS_DEFAULT_PROVIDER=volcengine

# 火山引擎 TTS
STORYTELLER_TTS_VOLCENGINE_API_KEY=xxx
STORYTELLER_TTS_VOLCENGINE_ENDPOINT=xxx

# OpenAI兼容 TTS（自定义）
STORYTELLER_TTS_OPENAI_COMPATIBLE_1_NAME=my-custom-tts
STORYTELLER_TTS_OPENAI_COMPATIBLE_1_API_KEY=xxx
STORYTELLER_TTS_OPENAI_COMPATIBLE_1_BASE_URL=https://my-custom-tts.com/v1
STORYTELLER_TTS_OPENAI_COMPATIBLE_1_MODEL=my-model
```

### 5.5 设计原则
- **环境变量优先**：敏感信息只通过环境变量
- **分层加载**：默认值 → 配置文件 → 环境变量 → CLI参数
- **可验证**：启动时验证配置完整性
- **可序列化**：配置可以保存到项目中，方便复现

---

## 6. CLI 交互设计

### 6.1 两种模式

**参数模式（一条命令搞定）：**
```bash
storyteller "一只小猫的冒险" --length medium --complexity simple
```

**交互式向导：**
```bash
storyteller
# 一步步引导用户配置
```

### 6.2 子命令

| 命令 | 说明 |
|------|------|
| `storyteller generate <topic>` | 生成新故事 |
| `storyteller continue <project>` | 继续之前的项目 |
| `storyteller list-projects` | 列出所有项目 |
| `storyteller list-voices` | 列出可用声音 |
| `storyteller config` | 查看/修改配置 |

### 6.3 参数列表

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--topic, -t` | 故事主题 | （交互式时问） |
| `--length, -l` | 故事长度 short/medium/long | `medium` |
| `--complexity, -c` | 剧本复杂度 simple/medium/rich | `simple` |
| `--output-format, -f` | 输出音频格式 mp3/wav/ogg | `mp3` |
| `--output-dir, -o` | 输出目录 | `./outputs` |
| `--project-dir` | 项目保存目录 | `./projects` |
| `--template` | 使用的故事模板 | `default` |
| `--default-llm-provider` | 默认LLM provider | 配置中的默认 |
| `--default-tts-provider` | 默认TTS provider | 配置中的默认 |
| `--tts-providers` | 本次可用的TTS provider列表（逗号分隔） | 所有已配置的 |
| `--voice-ids` | 限制使用的音色ID列表（逗号分隔） | 不限制 |
| `--strict-mode` | 严格模式（出错就停） | false |
| `--lenient-mode` | 宽松模式（出错尽量继续） | false |
| `--progress` | 进度显示级别 quiet/simple/detailed | `simple` |
| `--log-level` | 日志级别 debug/info/warn/error | `info` |
| `--resume` | 从断点继续 | false |
| `--force` | 覆盖已存在的项目 | false |
| `--dry-run` | 只生成剧本，不生成音频 | false |
| `--voice-mode` | 声音配置方式 auto/manual | `auto` |
| `--narrator-voice` | 指定旁白声音 | （自动匹配） |
| `--config` | 指定配置文件路径 | 默认路径 |

### 6.4 交互式向导步骤

```
1. 输入故事主题
2. 选择故事长度
3. 选择剧本复杂度
4. 选择输出格式
5. 确认配置 → 开始生成
   ↓
6. （剧本生成后）显示角色列表
7. 问：自动匹配声音吗？[Y/n]
8. （如选手动）逐个让用户选角色声音
   ↓
9. 开始生成音频，显示进度
10. 完成，显示结果
```

---

## 7. 错误处理设计

### 7.1 错误模式

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| **严格模式** (strict) | 任何错误立即停止，给出清晰错误信息 | 调试、对质量要求高 |
| **宽松模式** (lenient) | 非关键错误尽量继续，用备选方案 | 批量生成、不想被打断 |

### 7.2 错误分类和处理策略

| 错误类型 | 严格模式 | 宽松模式 |
|----------|----------|----------|
| **配置错误** | 立即停止 | 立即停止（必须） |
| **LLM调用失败** | 立即停止 | 重试3次，失败则停止 |
| **TTS某段失败** | 立即停止 | 跳过该段/用其他声音重试/用旁白代替 |
| **音频处理失败** | 立即停止 | 跳过该处理步骤 |
| **网络超时** | 重试3次，失败则停止 | 重试5次，失败则停止 |

### 7.3 错误信息设计

每个错误都包含：
- 错误类型和代码
- 人类可读的描述
- 发生在哪个阶段/步骤
- 建议的解决方法
- （可选）原始错误详情

### 7.4 重试机制
- 网络请求自动重试（指数退避）
- 可配置最大重试次数
- 每次重试都有日志记录

### 7.5 异常类层次
```
StorytellerError (基础)
├── ConfigError
├── ProviderError
│   ├── LLMError
│   └── TTSError
├── AudioProcessingError
└── ProjectError
```

---

## 8. 测试策略

### 8.1 测试分层

| 层级 | 测试内容 | 用什么 |
|------|----------|--------|
| **单元测试** | 单个组件的逻辑（数据模型、配置、工具函数等） | pytest |
| **集成测试** | 组件之间的协作（Pipeline、Provider集成等） | pytest + mock |
| **端到端测试** | 完整流程（用mock provider） | pytest |

### 8.2 关键测试点

**核心逻辑：**
- 剧本解析（LLM返回 → Script对象）
- 声音匹配逻辑
- 项目保存/加载
- 配置加载和优先级
- 错误处理和重试
- Provider注册和发现

**Provider：**
- 每个 Provider 的接口调用逻辑
- 错误处理和异常转换
- Mock 实现（用于测试）

**CLI：**
- 参数解析
- 交互式流程
- 进度显示

### 8.3 Mock Provider

提供 Mock LLM Provider 和 Mock TTS Provider：
- 不调用真实API
- 返回固定的测试数据
- 可以模拟各种错误场景
- 用于单元测试和集成测试

---

## 9. Provider 设计

### 9.1 Provider 注册中心
- 统一管理所有已启用的 Provider
- 支持动态注册和发现
- 按类型（LLM/TTS/AudioGenerator）分类

### 9.2 Provider 类型
- **内置 Provider**：火山引擎等，代码内置
- **OpenAI兼容 Provider**：通过配置添加，无需写代码
- （预留）**插件 Provider**：代码扩展

### 9.3 接口设计原则
- LLM Provider 只负责纯文本生成（chat/complete）
- TTS Provider 只负责文本转语音
- 业务逻辑在 core 层，不在 Provider 层

---

## 10. 待确认事项

- [ ] 火山引擎LLM具体API信息（端点、模型名）
- [ ] 火山引擎TTS具体API信息（端点、音色列表）
- [ ] Claude Code技能的具体交互方式

---

**设计完成时间：** 2026-09-10
