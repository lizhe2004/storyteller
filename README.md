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

## 命令参考

`storyteller generate <topic>` 支持 `--length short|medium|long`、
`--complexity simple|medium|rich`、`--output-format mp3|wav|ogg`、
`--tts-providers`、`--voice-ids`、`--voice-matcher llm|rule`、
`--dry-run`、`--data-dir`、`--progress quiet|simple|detailed` 和
`--strict-mode`。`--with-sfx` 仅适用于已配置音效 provider 的运行；完整的
首次运行配置见[首次使用指南](docs/getting-started.md)。

其他常用命令：

- `storyteller continue <project_id>`：复用已保存的状态和分段音频继续运行。
- `storyteller list-projects`：列出项目及状态。
- `storyteller list-voices`：列出已配置 provider 的音色，可用 `--format json`。
- `storyteller make-sound "<prompt>"` 与 `storyteller list-sounds [query]`：管理全局音效库。

`--dry-run` 只生成剧本 JSON，不合成音频。生成是网络密集型操作，短篇通常需要几十秒到几分钟；`--progress detailed` 可查看逐句和音效进度。

## 产物与项目状态

默认数据根目录是 `./.storyteller`。项目完成剧本生成后，目录会被重命名为
`.storyteller/stories/<YYYY-MM-DD>-<story-title>[-2]/`，其中包含
`project.json`、`story.script.json`、最终的 `story.mp3`（或所选格式）、
`audio/<line_id>.<format>` 分段音频，以及启用音效时的项目级 `sounds/`。全局
`make-sound` 音效库位于 `.storyteller/sounds/`；`project_id` 保存在
`project.json` 中且不会因目录重命名改变。项目状态按
`topic_collected → script_generated → voice_configured → generating_audio → audio_generated → completed` 推进，中断后可用 `continue` 续作。

## 音色匹配与演法指令

默认 `llm` 模式先判断角色性别/年龄段，再从已配置音色中精选；失败时回退到确定性规则，可用 `--voice-matcher rule` 或
`STORYTELLER_VOICE_MATCHER=rule` 强制规则匹配。每句对话可带演法指令，火山 TTS 通过 `additions.context_texts` 传递；阿里云 provider 将演法指令并入 `instruction`，不支持对应的上文引用机制。

## Provider 与音效

LLM 支持火山引擎和 OpenAI 兼容服务；TTS 支持火山引擎、阿里云百炼和 OpenAI 兼容服务；音效支持火山引擎 seed-audio。阿里云 HTTP TTS 需要单独的 API Key，Web 实时 TTS 还需要按 `.env.example` 配置业务空间和相应依赖。音效默认关闭，启用时必须配置独立的 `STORYTELLER_SOUND_<NAME>_API_KEY`，不能复用 TTS Key。

## 架构与开发

核心流程由 `core/pipeline.py` 编排剧本、音色、TTS、音频拼接和可选混音；`core/project.py` 负责项目状态和目录；`providers/` 提供 LLM、TTS、音效实现；`web/` 提供 Web 后端和实时 TTS。开发测试入口如下：

```bash
pip install -e ".[dev]"
pytest
pytest tests/unit/test_voice_matcher.py
```

Web 后端的登录、实时 TTS 和调度器细节目前保留在本 README；本地启动默认绑定 `127.0.0.1`，Docker 运行方式见 [Docker 部署文档](docs/deployment-docker.md)。

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
