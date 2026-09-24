# 首次使用指南

本指南覆盖从源码安装到第一次生成音频故事的最短路径。项目的事实配置名和默认值以当前源码与 `.env.example` 为准。

## 前置条件

- Python 3.8 或更高版本
- [ffmpeg](https://ffmpeg.org/)，用于 `pydub` 的音频拼接
- 可用的 LLM API Key 和 TTS API Key；两者是独立配置

## 本地安装

在项目根目录执行：

```bash
pip install -e .
```

如果要启动 Web 界面，安装 Web 依赖：

```bash
pip install -e ".[web]"
```

复制配置模板：

```bash
cp .env.example .env
```

编辑 `.env`，至少填写当前使用的 LLM 和 TTS provider 的 API Key。默认模板使用火山引擎：

```env
STORYTELLER_LLM_PROVIDER=volcengine
STORYTELLER_LLM_VOLCENGINE_API_KEY=your_api_key_here
STORYTELLER_TTS_PROVIDERS=volcengine
STORYTELLER_TTS_VOLCENGINE_API_KEY=your_api_key_here
STORYTELLER_TTS_VOLCENGINE_RESOURCE_ID=seed-tts-2.0
```

LLM Key 与 TTS Key 不要混用。阿里云 TTS、音效和其他 provider 需要额外配置，见 `.env.example` 与后续 Provider 文档。

## 第一次生成

使用 `generate` 加上一句话主题：

```bash
storyteller generate "一只小猫的冒险"
```

常用选项可以组合使用：

```bash
storyteller generate "数字积木的故事" \
  --length medium \
  --complexity rich \
  --output-format mp3 \
  --voice-matcher llm \
  --with-sfx
```

生成过程会依次请求剧本、音色和 TTS 服务；短篇通常需要几十秒到几分钟。需要更详细的终端进度时，可加 `--progress simple` 或 `--progress detailed`。

## 只生成剧本

使用 `--dry-run` 跳过音频合成，只生成并保存剧本 JSON：

```bash
storyteller generate "月亮婆婆" --dry-run
```

该模式仍需要 LLM 配置，但不会生成最终音频。

## 启动 Web

安装 `.[web]` 后执行：

```bash
storyteller web --host 0.0.0.0 --port 8000
```

本地访问 <http://localhost:8000>。如果没有设置 `STORYTELLER_WEB_PASSWORDS`，首次启动会在日志中输出一次性初始化码，用它设置至少 8 位的 Web 密码。Web 相关的实时 TTS 需要额外能力时，再按 `.env.example` 配置对应 provider。

## 产物位置

默认数据根目录是 `./.storyteller`。每个项目保存在 `stories/<project_id>/` 下，常见文件包括：

```text
.storyteller/
├── stories/<project_id>/
│   ├── project.json
│   ├── story.script.json
│   ├── story.mp3
│   ├── audio/<line_id>.mp3 # 逐句音频，用于断点续作
│   └── sounds/             # 本项目音效（启用音效时）
├── sounds/                 # 跨项目复用的音效库
└── logs/storyteller.log
```

可用 `--data-dir` 或 `STORYTELLER_DATA_DIR` 更换数据根目录；`STORYTELLER_OUTPUT_DIR` 和 `STORYTELLER_PROJECT_DIR` 可以分别覆盖故事输出与项目状态目录。

中断后可使用已保存的项目 ID 继续：

```bash
storyteller continue <project_id>
```

## 凭据安全

- `.env.example` 只放占位符；真实 `.env` 不要提交到版本库。
- 不要把 API Key、Web 密码、初始化码或 Cookie 签名密钥写入文档、日志截图或提交记录。
- Docker 部署时通过 Compose 运行时注入 `.env`，不要把凭据复制进镜像；数据备份和密码初始化见 [Docker 部署文档](deployment-docker.md)。
