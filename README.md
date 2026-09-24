# Storyteller

把一句话主题变成带角色配音的音频故事：LLM 写结构化剧本，系统匹配音色，TTS 逐句合成并拼接为音频。项目支持多角色对话、旁白、演法指令、可选音效/背景音乐、断点续作，以及 CLI 和 Web 使用方式。

## 核心能力

- LLM 剧本生成与角色音色匹配
- 火山引擎 LLM/TTS，及可选的阿里云百炼 TTS
- 任意 OpenAI 兼容服务的接入能力
- 项目状态、逐句音频和最终音频持久化
- 可选 seed-audio 音效与背景音乐，并跨项目缓存
- CLI 参数模式、交互式向导和 Web 界面

## 最短上手

需要 Python 3.8+ 和 [ffmpeg](https://ffmpeg.org/)。安装 CLI：

```bash
pip install -e .
cp .env.example .env
```

在 `.env` 中填写独立的 LLM 与 TTS API Key 后生成故事：

```bash
storyteller generate "一只小猫的冒险"
```

完整的本地安装、配置、首次生成、Web 启动和产物说明见[首次使用指南](docs/getting-started.md)。

## Docker 快速入口

```bash
cp .env.example .env
# 编辑 .env，填写凭据
docker compose pull
docker compose up -d
```

然后打开 <http://localhost:8000>。Docker 的数据卷、密码初始化、升级和备份说明见 [Docker 部署文档](docs/deployment-docker.md)。

## 支持的 Provider

- LLM：火山引擎，以及可配置的 OpenAI 兼容服务
- TTS：火山引擎、阿里云百炼，以及可配置的 OpenAI 兼容服务
- 音效：火山引擎 seed-audio

Provider 的凭据、模型、音色和能力差异应以对应主题文档及 `docs/reference/tts/` 原始资料为准；厂商资料不等同于项目已经实现的能力。

## 文档索引

- [文档首页](docs/index.md)：按使用路径查找文档
- [首次使用指南](docs/getting-started.md)：本地安装、配置、生成和 Web
- [Docker 部署](docs/deployment-docker.md)：Compose、数据持久化和容器运行
- [TTS 厂商参考资料](docs/reference/tts/)：阿里云、火山引擎和 Qwen 原始资料

配置、CLI、Web/API、架构、Provider 和运维主题会在后续主题文档中分别维护；入口链接集中在[文档首页](docs/index.md)。

## 开发与测试

```bash
pip install -e ".[dev]"
pytest
```

开发约定和各主题的实现边界见 [文档首页](docs/index.md)。

## 许可证

MIT
