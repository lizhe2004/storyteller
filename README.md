# Storyteller

音频故事生成工具 —— 把故事主题变成带角色声音的音频故事。

支持从简单的故事主题生成完整的音频故事，包含：
- 多角色对话和旁白
- 自动匹配角色声音
- 支持多个 TTS 提供商
- 断点续传

## 安装

```bash
pip install -e .[dev]
```

## 配置

复制 `.env.example` 到 `.env` 并填入你的 API Key。

```bash
cp .env.example .env
```

## 使用

### 参数模式

```bash
# 最简用法
storyteller generate "一只小猫的冒险"

# 带各种参数
storyteller generate "太空探险" \
  --length medium \
  --complexity simple \
  --output-format mp3 \
  --tts-providers volcengine,aliyun \
  --voice-ids volcengine:narrator_01,volcengine:male_01
```

### 交互式向导

```bash
storyteller
# 按提示一步步输入主题、长度、复杂度等
```

### 从断点继续

```bash
storyteller continue <project_id>
```

### 列出项目

```bash
storyteller list-projects
```

### 列出可用声音

```bash
storyteller list-voices
```

## 支持的 AI 提供商

### LLM（大语言模型）
- 火山引擎（Volcengine）- 默认
- OpenAI 兼容格式（通过配置添加）

### TTS（语音合成）
- 火山引擎（Volcengine）- 默认
- OpenAI 兼容格式（通过配置添加）

### 添加自定义 OpenAI 兼容 TTS Provider

```bash
export STORYTELLER_TTS_PROVIDERS=volcengine,my-custom-tts
export STORYTELLER_TTS_OPENAI_COMPATIBLE_MY_CUSTOM_TTS_NAME=my-custom-tts
export STORYTELLER_TTS_OPENAI_COMPATIBLE_MY_CUSTOM_TTS_TYPE=openai_compatible
export STORYTELLER_TTS_OPENAI_COMPATIBLE_MY_CUSTOM_TTS_API_KEY=your-key
export STORYTELLER_TTS_OPENAI_COMPATIBLE_MY_CUSTOM_TTS_BASE_URL=https://custom.example.com/v1
export STORYTELLER_TTS_OPENAI_COMPATIBLE_MY_CUSTOM_TTS_MODEL=tts-model
```

## 项目状态（断点续传）

每个项目保存状态到 `projects/` 目录，支持从断点继续：

| 状态 | 说明 |
|------|------|
| `initialized` | 项目已创建 |
| `topic_collected` | 已收集主题 |
| `script_generating` | 正在生成剧本 |
| `script_generated` | 剧本已生成 |
| `voice_configuring` | 正在配置声音 |
| `voice_configured` | 声音已配置 |
| `generating_audio` | 正在生成音频 |
| `audio_generated` | 音频已生成 |
| `post_processing` | 正在后处理 |
| `completed` | 全部完成 |
| `failed` | 失败 |

## 开发

```bash
# 运行测试
pytest

# 覆盖率报告
pytest --cov=storyteller

# 只运行特定测试
pytest tests/unit/test_pipeline.py
pytest tests/e2e/test_cli.py
```

## 架构

```
src/storyteller/
├── core/                 # 核心抽象和业务逻辑
│   ├── models.py         # 数据模型（Script, Character, VoiceConfig 等）
│   ├── llm.py           # LLM 抽象接口
│   ├── tts.py           # TTS 抽象接口
│   ├── audio.py         # 音频处理（pydub）
│   ├── story_generator.py # 剧本生成
│   ├── voice_matcher.py  # 声音匹配
│   ├── pipeline.py       # 流程编排
│   └── project.py        # 项目状态保存/加载
├── providers/            # Provider 实现
│   ├── volcengine/       # 火山引擎
│   ├── openai_compatible/ # OpenAI 兼容
│   └── mock/             # 测试用 mock
└── cli/                  # 命令行界面
    ├── main.py           # CLI 入口
    └── interactive.py    # 交互式向导
```

## 许可证

MIT
