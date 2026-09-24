# CLI 参考

入口命令是 `storyteller`；在源码工作区也可使用 `python -m storyteller.cli.main`。不带子命令时进入交互式向导。CLI 每次启动都从当前目录的 `.env` 和 `STORYTELLER_*` 变量创建进程配置；命令行选项只覆盖本次运行。CLI 不读取 Web 的 `settings.json`。完整配置语义见 [`configuration.md`](configuration.md)。

## `generate`

```text
storyteller generate TOPIC [OPTIONS]
```

根据主题生成剧本、角色音频和最终故事。`TOPIC` 必填。

| 参数 | 默认值/可选值 | 环境变量关系 |
| --- | --- | --- |
| `--length, -l` | `medium`; `short`、`medium`、`long` | 无对应环境变量 |
| `--complexity, -c` | `simple`; `simple`、`medium`、`rich` | 无 |
| `--output-format, -f` | 配置值，未配置为 `mp3` | 无专用环境变量；CLI 选项仅覆盖本次命令 |
| `--tts-providers` | 未指定时使用配置/注册表中的 provider；逗号分隔 | 只在已注册/配置的 provider 中限制本次生成；不添加或扩大 `STORYTELLER_TTS_PROVIDERS` allowlist |
| `--voice-ids` | 未限制 | 无；逗号分隔的项目 voice id 集合 |
| `--default-llm-provider` | 配置默认值 | 覆盖 `STORYTELLER_LLM_PROVIDER` |
| `--dry-run` | 关闭 | 无；只生成并保存剧本，不生成音频 |
| `--data-dir` | `./.storyteller` | 覆盖 `STORYTELLER_DATA_DIR`，并重新派生未显式覆盖的目录 |
| `--log-level` | `info` | 覆盖 `STORYTELLER_LOG_LEVEL` |
| `--progress` | `simple`; `quiet`、`simple`、`detailed` | 无专用环境变量 |
| `--strict-mode` | 关闭 | 无；出错立即停止 |
| `--voice-matcher` | `llm`; `llm`、`rule` | 覆盖 `STORYTELLER_VOICE_MATCHER` |
| `--with-sfx` | 关闭 | 覆盖 `STORYTELLER_SOUND_ENABLED` 为开启 |
| `--sound-dir` | `<data-dir>/sounds` | 覆盖 `STORYTELLER_SOUND_DIR` |
| `--sound-provider` | 配置默认值/唯一 provider | 覆盖 `STORYTELLER_SOUND_PROVIDER` |

示例：

```bash
storyteller generate "月球上的小猫" --length short --output-format mp3
storyteller generate "森林里的雨夜" --dry-run --voice-matcher rule
storyteller generate "海边探险" --tts-providers aliyun,volcengine --with-sfx --sound-provider volcengine
```

成功时打印 `Done! Output: ...`；`--dry-run` 打印剧本保存路径。最终文件位于项目目录下的 `story.<format>`。

## `continue`

```text
storyteller continue PROJECT_ID [OPTIONS]
```

从项目断点继续生成。`PROJECT_ID` 可以是稳定项目 id 或项目目录名。`--output-format`（默认配置值/`mp3`）、`--tts-providers`、`--voice-ids`、`--data-dir`、`--strict-mode`、`--voice-matcher`、`--with-sfx`、`--sound-dir`、`--default-llm-provider` 和 `--sound-provider` 的取值与 `generate` 相同；它们都只影响本次续作。`--tts-providers` 只能从已注册/配置的 provider 中进一步限制本次续作，不能扩展配置 allowlist。示例：

```bash
storyteller continue 2026-09-24-小猫的冒险 --output-format wav --sound-provider mock
```

## `list-projects`

```text
storyteller list-projects [--data-dir PATH]
```

列出 data root 下的项目目录、状态和标题。`--data-dir` 默认来自 `STORYTELLER_DATA_DIR` 或 `./.storyteller`；没有独立的项目列表环境变量。示例：

```bash
storyteller list-projects --data-dir ./demo-data
```

## `list-voices`

```text
storyteller list-voices [--tts-providers NAMES] [--format table|json]
```

列出已注册 TTS provider 的音色。`--tts-providers` 默认使用配置的全部 provider，值为逗号分隔名称，只能缩小本次查询范围；它不能添加未注册 provider，也不能扩大 `STORYTELLER_TTS_PROVIDERS` 的 allowlist。`--format` 默认 `table`，可选 `json`。JSON 行包含 `provider`、`voice_id`、`name`、`gender`、`age`、`category`、`description` 和 `language`。

```bash
storyteller list-voices --tts-providers mock --format json
```

没有可用音色时命令返回成功并提示检查配置；provider 请求失败时返回错误。

## `make-sound`

```text
storyteller make-sound PROMPT [OPTIONS]
```

用文字提示生成或复用一条全局音效库记录。`PROMPT` 必填。

| 参数 | 默认值/可选值 | 环境变量关系 |
| --- | --- | --- |
| `--name` | 提示词前 12 个字符 | 无 |
| `--kind` | `sfx`; `sfx`、`ambient`、`music` | 无 |
| `--description` | 空字符串 | 无 |
| `--tags` | 空字符串；逗号分隔 | 无 |
| `--format` | `mp3`；实现支持 `mp3`、`wav` | 无 |
| `--sound-dir` | `STORYTELLER_SOUND_DIR` 或 `<data-dir>/sounds` | 覆盖目录 |
| `--sound-provider` | `STORYTELLER_SOUND_PROVIDER`，唯一 provider 时自动选择 | 覆盖环境选择 |

```bash
storyteller make-sound "轻柔的雨声" --kind ambient --name rain --tags rain,night --sound-provider volcengine
```

同一提示词、格式和 provider 命中缓存时不会再次调用 API；新记录写入音效库，成功后删除 raw staging 文件。未配置 provider、或配置多个却未选择时命令返回错误。

## `list-sounds`

```text
storyteller list-sounds [QUERY] [--kind sfx|ambient|music] [--sound-dir PATH]
```

列出或检索全局音效库。`QUERY` 默认无（列出全部）；`--kind` 默认无，可限制类型；`--sound-dir` 默认 `STORYTELLER_SOUND_DIR` 或 `<data-dir>/sounds`。示例：

```bash
storyteller list-sounds rain --kind ambient
storyteller list-sounds --sound-dir ./demo-data/sounds
```

## `web`

```text
storyteller web [--host HOST] [--port PORT]
```

启动 Web 服务。`--host` 默认 `STORYTELLER_WEB_HOST`/`127.0.0.1`，`--port` 默认 `STORYTELLER_WEB_PORT`/`8000`；两个选项只覆盖本次进程，不写入 runtime settings。需要 Web 依赖时先安装 `pip install -e ".[web]"`。

```bash
storyteller web --host 127.0.0.1 --port 8000
```

## 交互式向导

运行 `storyteller` 或 `storyteller wizard` 会询问：

1. 故事主题：空值会拒绝并重新询问，无默认主题。
2. 故事长度：`1` 短篇、`2` 中篇（默认）、`3` 长篇；也接受选项字符串。
3. 剧本复杂度：`1` 简单（默认）、`2` 中等、`3` 丰富。
4. 输出格式：`1` `mp3`（默认）、`2` `wav`。
5. 角色声音：`1` 自动匹配（默认）；`2` 暂未接入手动选择，当前仍按自动流程执行。
6. 音效与背景音乐：默认跟随 `STORYTELLER_SOUND_ENABLED`；输入 `y/yes` 开启，`n/no` 关闭。启用且存在多个 provider 时继续选择 provider；只有一个时自动选择。

直接回车使用默认值；数字越界、未知字符串和无效 yes/no 输入也回退到该问题的默认值。向导读取 `.env`/环境配置，但没有独立的向导环境变量。示例：

```bash
STORYTELLER_TTS_PROVIDERS=mock STORYTELLER_TTS_MOCK_TYPE=mock storyteller
```

向导完成后与 `generate` 相同，成功打印输出路径。
