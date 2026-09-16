# Storyteller

把一句话主题变成**带角色配音的音频故事**：LLM 写剧本 → 大模型为每个角色匹配音色 → TTS 逐句合成 → 拼接成一个 MP3。

- 多角色对话 + 旁白，剧本为结构化 JSON
- 大模型两阶段匹配音色：先判定角色性别/年龄，再在音色库里按音色描述精选
- 每句台词自动生成演法指令（情绪/语气），并引用上文保持情感连贯
- 可选音效与背景音乐：LLM 产出声音提示，seed-audio 生成并自动混音，结果进全局音效库缓存复用
- 火山引擎 LLM + 语音合成（seed-tts 2.0），可选接入阿里云百炼 TTS（Qwen-Audio-TTS），同时支持任意 OpenAI 兼容服务
- 项目状态持久化，支持断点续作
- CLI 参数模式 + 交互式向导

## 安装

需要 Python ≥ 3.8，音频拼接依赖 [ffmpeg](https://ffmpeg.org/)（pydub 后端）。

```bash
pip install -e ".[dev]"
```

如果使用 Web 界面，额外安装 Web 依赖：

```bash
pip install -e ".[web,dev]"
```

也可以使用 Docker Compose 部署，详见 [Docker 部署文档](docs/deployment-docker.md)。

## 配置

密钥通过环境变量 / `.env` 管理。**`.env.example` 入库且只含占位符；真实 `.env` 已被 gitignore，禁止提交。**

```bash
cp .env.example .env
# 编辑 .env 填入凭据
```

CLI 最少需要配置 LLM 和 TTS 两套互相独立的密钥；使用 Web、阿里云 TTS 或音效功能时，还需要对应的额外配置：

| 变量 | 说明 |
|------|------|
| `STORYTELLER_LLM_VOLCENGINE_API_KEY` | 火山方舟（Ark）LLM Key |
| `STORYTELLER_LLM_VOLCENGINE_MODEL` | 默认 `deepseek-v4-flash-260425` |
| `STORYTELLER_LLM_PROVIDERS` | LLM provider 启用名单与顺序；未设置时按已配置 provider 自动发现 |
| `STORYTELLER_TTS_VOLCENGINE_API_KEY` | 语音合成 Key（**与 LLM Key 不同**） |
| `STORYTELLER_TTS_VOLCENGINE_RESOURCE_ID` | 默认 `seed-tts-2.0` |
| `STORYTELLER_TTS_PROVIDERS` | TTS 可用 provider 列表；设置后仅列表内可用，未设置时自动发现已配置 provider |
| `STORYTELLER_TTS_ALIYUN_API_KEY` | 可选第二 TTS：阿里云百炼（DASHSCOPE）Key；provider 名为 `aliyun` 时自动选择阿里云实现 |
| `STORYTELLER_TTS_ALIYUN_MODELS` | 可选的阿里云模型白名单，逗号分隔 |
| `STORYTELLER_TTS_ALIYUN_WORKSPACE_ID` | 业务空间 ID；自动派生 HTTP 专属域名和 Web 实时 WebSocket 地址 |
| `STORYTELLER_DATA_DIR` | 生成物根目录，默认 `./.storyteller`（内含 `stories/`、`sounds/`） |
| `STORYTELLER_OUTPUT_DIR` / `STORYTELLER_PROJECT_DIR` | 分别覆盖故事产物/状态目录，默认都在 `<DATA_DIR>/stories` |
| `STORYTELLER_VOICE_MATCHER` | `llm`（默认，语义匹配）或 `rule`（仅关键字规则） |
| `STORYTELLER_WEB_PASSWORDS` / `STORYTELLER_WEB_SECRET` | Web 登录密码（逗号分隔）/ Cookie 签名密钥；启动 Web 必填密码 |
| `STORYTELLER_WEB_HOST` / `STORYTELLER_WEB_PORT` | Web 监听地址/端口，默认 `127.0.0.1` / `8000` |
| `STORYTELLER_SOUND_ENABLED` | `true/false`，是否生成音效/背景音乐（默认关） |
| `STORYTELLER_SOUND_DIR` | 全局共享音效库目录，默认 `<DATA_DIR>/sounds` |
| `STORYTELLER_SOUND_VOLCENGINE_API_KEY` | 音效 Key（seed-audio），独立配置、不复用 TTS Key；启用音效必填 |
| `STORYTELLER_SOUND_VOLCENGINE_MODEL` | 音效模型，默认 `seed-audio-1.0` |
| `STORYTELLER_SOUND_PROVIDERS` | 可选的音效 provider 启用名单；配了 key 即可被 `--sound-provider` 选用 |
| `STORYTELLER_TTS_SCHEDULER_*` | Web 实时 TTS 的并发、限速、队列和超时参数，详见[实时 TTS 与调度器](#实时-tts-与调度器) |
| `STORYTELLER_TTS_HOST_VOICE` | Web 实时播放使用的主持人音色，格式为 `provider:voice_id`；未设置时自动选择 |

> `STORYTELLER_TTS_PROVIDERS` 是 TTS 的允许列表：设置后，未列出的 provider 即使配置了 key 也不会注册；未设置时才自动发现。LLM 与音效 provider 仍是“配了参数即可自动发现”的模式。

## 使用

### 交互式向导（默认入口）

不带子命令直接运行 `storyteller`，会进入交互式向导，依次提示输入**主题、长度、复杂度、输出格式**（直接回车用默认值）：

```bash
storyteller
```

### 参数模式

```bash
# 最简：生成并输出到 .storyteller/stories/<project_id>/story.mp3
storyteller generate "一只小猫的冒险"

# 常用选项
storyteller generate "数字积木的故事" \
  --length medium \
  --complexity rich \
  --output-format mp3 \
  --voice-matcher llm \
  --with-sfx
```

只生成剧本、不合成音频（剧本会保存为 JSON）：

```bash
storyteller generate "月亮婆婆" --dry-run
# → .storyteller/stories/<project_id>/story.script.json
```

> 生成过程是网络密集型：剧本生成、音色精选和逐句 TTS 都可能产生网络等待。一个短篇通常需要几十秒到几分钟，可用 `--progress simple` 查看进度；详细耗时会记录到 `.storyteller/logs/storyteller.log`。

### 命令参考

#### `storyteller generate <topic>` — 生成音频故事

| 参数 | 含义 | 是否必填 | 默认值 | 可选值 |
|------|------|:---:|--------|--------|
| `topic` | 故事主题（一句话描述） | ✅ 必填 | — | 任意文本 |
| `--length`, `-l` | 故事篇幅，决定台词行数多少 | 否 | `medium` | `short` / `medium` / `long` |
| `--complexity`, `-c` | 剧本复杂度（角色数量、情节层次） | 否 | `simple` | `simple` / `medium` / `rich` |
| `--output-format`, `-f` | 最终音频格式 | 否 | `mp3` | `mp3` / `wav` / `ogg` |
| `--tts-providers` | 参与合成的 TTS provider，逗号分隔 | 否 | 环境变量 `STORYTELLER_TTS_PROVIDERS` | 如 `volcengine,my-tts` |
| `--voice-ids` | 限制使用的音色 ID，逗号分隔 | 否 | 全部可用音色 | 任意音色 ID |
| `--default-llm-provider` | 覆盖默认 LLM provider | 否 | 环境变量配置 | provider 名 |
| `--voice-matcher` | 音色匹配方式 | 否 | `llm` | `llm`（大模型语义匹配） / `rule`（关键字规则） |
| `--with-sfx` | 生成音效/背景音乐并自动混音（seed-audio，结果进全局音效库缓存） | 否 | 关 | 标志（开关） |
| `--sound-provider` | 本次使用的音效 provider（需配合 `--with-sfx`） | 否 | 环境默认 | provider 名，如 `volcengine` |
| `--sound-dir` | 音效库目录 | 否 | `<data-dir>/sounds` | 任意目录 |
| `--dry-run` | 只生成剧本、不合成音频 | 否 | 关 | 标志（开关） |
| `--data-dir` | 生成物根目录 | 否 | `./.storyteller` | 任意目录 |
| `--log-level` | 日志级别 | 否 | `info` | `debug` / `info` / `warn` / `error` |
| `--progress` | 进度显示级别 | 否 | `simple` | `quiet` / `simple` / `detailed` |
| `--strict-mode` | 严格模式：任一步出错立即停止 | 否 | 关 | 标志（开关） |

说明：`--dry-run` 只写剧本、不生成音频，与合成类参数无关；`--tts-providers`、`--voice-ids`、`--with-sfx` 等也适用于 `continue`（见下）。

#### `--progress` 进度显示级别

`generate` 支持 `--progress` 控制终端输出详细程度，可选三档（默认 `simple`）：

| 值 | 含义 | 适用场景 |
|------|------|------|
| `quiet` | 不输出任何过程信息，只在结束时打印最终输出路径 | 脚本化 / 无人值守，只关心产物 |
| `simple` | 每个大步骤一行：剧本生成、音色配置、逐句合成进度（`1/20` … `20/20`）、拼接、最终路径 | 默认，日常使用 |
| `detailed` | 在 `simple` 基础上，额外打印每句的**行号 `[角色]` 台词片段**，以及每条音效/背景音乐的**生成或缓存命中详情** | 排查某句配音或某个音效问题时 |

`simple` 的典型输出：

```text
Script generated: 逃离地球：深空巨兽
Voices configured
Generating audio 1/20
Generating audio 2/20
...
Generating audio 20/20
Concatenating audio...
Done! Output: .storyteller/stories/proj_259076a9b8e1/story.mp3
```

`detailed` 会在此之上增加逐句与逐音效明细（示例）：

```text
Script generated: 逃离地球：深空巨兽
Voices configured
Generating audio 1/20
  line 1 [旁白]: 公元 2177 年，地球已经……
  line 2 [李教授]: 数据不会说谎，我们……
Generating audio 2/20
  line 3 [旁白]: 舱门缓缓开启……
...
Concatenating audio...
  sound 警报声 -> snd_ab12cd34ef56.mp3 (3.2s)
  sound 引擎轰鸣 -> snd_12ab34cd56ef.mp3 (2.8s, cached)
Done! Output: .storyteller/stories/proj_259076a9b8e1/story.mp3
```

说明：`detailed` 里 `cached, skipped` 表示该句台词已在本地缓存（断点续作）、不再调用 TTS；音效一行的 `, cached` 表示该音效命中全局音效库、未重复调用 seed-audio。

#### 日志与耗时排查

每次 CLI 或 Web 任务都会把诊断日志写入：

```text
.storyteller/logs/storyteller.log
```

日志采用传统文本格式，关键字段使用 `key=value`，例如：

```text
2026-09-14 23:49:31,123 INFO storyteller.core.voice_matcher event=llm_request_completed job_id=job_xxx project_id=proj_xxx phase=voices duration_ms=19042 candidate_count=28 character_count=5
```

排查音色阶段时，可搜索同一个任务的 `job_id`，重点查看：

```text
voice_matching_started
llm_request_started
llm_request_completed
project_saved
script_export_completed
script_ready_sent
```

#### `storyteller continue <project_id>` — 从断点继续

沿用项目已保存的 length/complexity 与已合成的分段音频，跳过已完成步骤。可选参数（含义与 `generate` 相同）：`--output-format/-f`、`--tts-providers`、`--voice-ids`、`--default-llm-provider`、`--voice-matcher`、`--with-sfx`、`--sound-provider`、`--sound-dir`、`--data-dir`、`--strict-mode`。

#### `storyteller list-projects` — 列出所有项目

| 参数 | 含义 | 默认值 |
|------|------|--------|
| `--data-dir` | 生成物根目录 | `./.storyteller` |

输出 `项目ID [状态] 主题`。

#### `storyteller list-voices` — 列出可用音色

| 参数 | 含义 | 默认值 | 可选值 |
|------|------|--------|--------|
| `--tts-providers` | 限定查询的 provider，逗号分隔 | 全部已配置 provider | provider 名 |
| `--format` | 输出格式 | `table` | `table` / `json` |

按 provider 分组，先显示 provider 名称、说明与音色数，再用表格列出每个音色的**名称、音色 ID、性别、年龄段、场景**；有描述的音色，描述紧跟在该音色所在行的下一行（名称列留白、后四列合并展示，过长自动折行）。

```text
【火山引擎】  seed-tts 2.0 语音合成（火山方舟）（249 个音色）
+----------------+--------------------------------------------+------+--------+----------+
| 名称           | 音色ID                                     | 性别 | 年龄段 | 场景     |
+----------------+--------------------------------------------+------+--------+----------+
| 少儿故事       | zh_female_shaoergushi_...                  | 女   | 青年   | 有声阅读 |
|                | 语调活泼、声线亲切，适配儿童故事的治愈女声                            |
| ...            | ...                                        | ...  | ...    | ...      |
+----------------+--------------------------------------------+------+--------+----------+
```

`--format json` 输出数组，每条含 `provider/voice_id/name/gender/age/category/description/language`，便于脚本处理。性别只有 `male`/`female`（OpenAI 兼容的中性音色为 `null`）；年龄段为 `child/teen/young_adult/middle_aged/senior`。

#### `storyteller make-sound "<prompt>"` — 生成/复用一个音效

| 参数 | 含义 | 是否必填 | 默认值 | 可选值 |
|------|------|:---:|--------|--------|
| `prompt` | 声音描述（写清发声体+动作+质感+节奏） | ✅ 必填 | — | 任意文本 |
| `--name` | 音效名称 | 否 | 提示词前 12 字 | 任意文本 |
| `--kind` | 类型 | 否 | `sfx` | `sfx`（短促音效） / `ambient`（环境声） / `music`（音乐） |
| `--description` | 描述（便于检索复用） | 否 | 空 | 任意文本 |
| `--tags` | 逗号分隔的标签 | 否 | 空 | 如 `天气,夜晚` |
| `--format` | 输出格式 | 否 | `mp3` | `mp3` / `wav` |
| `--sound-dir` | 音效库目录 | 否 | `<data-dir>/sounds` | 任意目录 |
| `--sound-provider` | 使用的音效 provider | 否 | 首个已配置 provider | provider 名 |

相同 `prompt` 命中缓存时打印 `Cache hit (no API call)`，不产生网络调用。

#### `storyteller list-sounds [query]` — 列出/检索音效库

| 参数 | 含义 | 默认值 | 可选值 |
|------|------|--------|--------|
| `query`（位置参数） | 关键字过滤（匹配名称/描述/标签） | 无 | 任意文本 |
| `--kind` | 只列出指定类型 | 全部 | `sfx` / `ambient` / `music` |
| `--sound-dir` | 音效库目录 | `<data-dir>/sounds` | 任意目录 |

### 通用说明

- 带 `--data-dir` / `--sound-dir` 的选项也可用环境变量 `STORYTELLER_DATA_DIR` / `STORYTELLER_SOUND_DIR` 指定，优先级：命令行 > 环境变量 > 默认值（完整环境变量表见上文[配置](#配置)）。
- `generate` 与 `continue` 共用：`--tts-providers`、`--voice-ids`、`--default-llm-provider`、`--voice-matcher`、`--with-sfx`、`--sound-provider`、`--sound-dir`、`--data-dir`、`--strict-mode`、`--output-format`。
- `--length` / `--complexity` 原样传给 LLM 作为"故事长度 / 剧本复杂度"约束，最终台词行数由模型决定。

## 产物

所有生成物默认收在单一数据根 `.storyteller/` 下。每个故事独占一个文件夹：

```
.storyteller/
├── stories/
│   └── <project_id>/
│       ├── project.json          # 项目状态（断点续作用）
│       ├── story.mp3             # 拼接混音后的最终音频
│       ├── story.script.json     # 完整剧本（含角色、台词、演法指令、匹配到的音色）
│       └── audio/                # 逐句合成的分段音频（用于断点续作）
│           ├── 1.mp3 …
└── sounds/                       # 全局共享音效库（跨项目复用）
    ├── index.json
    └── snd_*.mp3
```

可用 `--data-dir` 或 `STORYTELLER_DATA_DIR` 更换根目录；也可用 `STORYTELLER_OUTPUT_DIR` / `STORYTELLER_PROJECT_DIR` / `STORYTELLER_SOUND_DIR` 分别覆盖。

剧本 JSON 片段示例：

```json
{
  "title": "数字积木的搭塔比赛",
  "characters": [
    {
      "id": "one", "name": "数字1",
      "description": "6岁男孩性格，有点急躁但热心",
      "voice_config": {
        "provider": "volcengine",
        "voice_id": "zh_male_liangsangmengzai_uranus_bigtts",
        "gender": "male", "age": "child", "name": "亮嗓萌仔"
      }
    }
  ],
  "lines": [
    {"line_id": "1", "line_type": "narration", "text": "……"},
    {"line_id": "2", "line_type": "dialogue", "character_id": "one",
     "text": "我这么矮，搭不高呀。",
     "metadata": {"direction": "低头叹气，声音闷闷的"}}
  ]
}
```

## 音色匹配

音色只用两个正交维度描述：**性别**（male/female，中性音色为 null）与**年龄段**（child/teen/young_adult/middle_aged/senior），另有来自官方分类的**场景**标签（有声阅读、通用场景、角色扮演等）。系统不再给音色贴「旁白/角色」的固定类型——儿童音色、温暖年轻女声同样可以念旁白。

默认 `llm` 模式分两步：

1. **角色分类（LLM 调用一）**：根据角色名 + 描述判定性别与年龄段。旁白角色按 id/名称确定性识别（旁白/narrator/说书/叙述），不参与分类。
2. **音色精选（LLM 调用二）**：把全部候选音色（有声阅读类排在最前）连同性别/年龄/场景/描述交给模型挑选。对话角色严格遵守性别、年龄与气质贴合；旁白角色无性别限制，优先有声阅读类，也可按故事气质选儿童或温暖音色。

任一步失败或返回非法结果，对应角色回退到确定性规则匹配：对话角色在同性别音色池里按年龄距离挑选（同性别池为空时退到中性音色），有声阅读类作为对话的最后备选；旁白角色在全库中优先有声阅读类。可用 `--voice-matcher rule` 或 `STORYTELLER_VOICE_MATCHER=rule` 完全走规则（不产生额外 LLM 调用）。

内置火山音色库约 249 个（仅 seed-tts-2.0，含中英文混读音色），由 `scripts/build_voice_catalog.py` 从 `data/` 下的官方清单整理生成，打包在 `src/storyteller/providers/volcengine/voices.json`。启用阿里云 provider 后另有 1,189 个中文 Qwen-Audio-TTS 系统音色（含多个年龄段和 3.0 flash/plus 模型），打包在 `src/storyteller/providers/aliyun/voices.json`，每个音色记录其专属模型（plus/flash 音色不可混用）。原始清单位于项目根目录的两个 `qwen-audio-3.0-tts-*.md` 文件，目录可用 `scripts/build_aliyun_voice_catalog.py` 重新生成。

## 演法指令与上文引用

每句对话，LLM 会生成一条不超过 20 字的自然语言 `direction`（如「又急又委屈，带着哭腔」），合成时通过火山 TTS 的 `additions.context_texts` 传递：

- 以 `#` 开头的演法指令：控制情绪/语气，**不会被朗读**；
- 不带 `#` 的引用上文（最近一句旁白/对话）：不合成，仅让模型承接场景情绪。

阿里云 provider 只有单个 `instruction` 参数：演法指令会拼接进 `instruction`，引用上文被丢弃（该接口无对应机制）。

## 接入阿里云百炼 TTS

除火山外可启用阿里云 Qwen-Audio-TTS（非实时 SpeechSynthesizer 接口，北京地域）。在 `.env` 中：

```bash
# 配置 API_KEY 后，将 aliyun 加进 TTS 可用列表：
STORYTELLER_TTS_PROVIDERS=volcengine,aliyun
STORYTELLER_TTS_ALIYUN_API_KEY=your_dashscope_key
# Web 实时播放需要配置 Qwen-Audio-TTS/CosyVoice 的业务空间 ID；HTTP/WebSocket 地址由程序自动拼接：
# STORYTELLER_TTS_ALIYUN_WORKSPACE_ID=your_workspace_id
```

非流式接口先返回 24 小时有效的音频 URL，程序会立即下载落盘。当前实现只接受内置音色目录中的阿里云音色，并从音色记录中使用对应模型；未知音色会直接报错。当前实现使用 HTTP API；官方 HTTP SDK 与原始 HTTP API 参考分别见 [`qwen-audio-tts-http-python-sdk.md`](docs/reference/tts/qwen-audio-tts-http-python-sdk.md) 和 [`qwen-audio-tts-http-api.md`](docs/reference/tts/qwen-audio-tts-http-api.md)，SDK 是否切换作为后续决策。多 provider 时逐句按音色归属的 provider 路由，音色匹配在 `STORYTELLER_TTS_PROVIDERS` 列出的音色库中统一进行；想完全用阿里云，设 `STORYTELLER_TTS_PROVIDERS=aliyun`，或单次使用 `--tts-providers aliyun`。

## 音效与背景音乐

`--with-sfx`（或 `STORYTELLER_SOUND_ENABLED=true`）开启后：

> 音效是与 LLM/TTS 同构的独立 provider 分组：用 `STORYTELLER_SOUND_VOLCENGINE_API_KEY` 配置独立 Key（**不复用、不回退 TTS Key**），可用 `--sound-provider NAME`（generate/continue/make-sound）显式选择；未指定时使用首个已配置 provider。旧变量 `STORYTELLER_SFX_VOLCENGINE_*` 已移除。

> 生成的每条音效（含未通过响度闸门、被跳过混音的废片）都会以 cue 的中文名保存在项目目录 `stories/<项目>/sounds/` 下，永不自动删除，方便事后收听排查；通过闸门的素材另存一份到全局音效库（`snd_<id>.mp3`，供跨项目缓存复用）。`make-sound` 的新素材先暂存于 `sounds/raw/`，合格入库后清理，不合格则保留并以非零退出码报告路径。

1. 写剧本的 LLM 会额外产出**可选**的声音提示——顶层一条贯穿全剧的 `background_music`，以及个别台词行的 `sound_effects`（`effect` 短促音效 / `ambient` 持续环境声）。提示遵循「宁缺毋滥、只描述声音本身、不含任何人声台词」，并要写清发声体+动作+声音质感与节奏（例如肚子叫要写「人肚子饿时咕咕叫、低沉冒泡、两三声」，而不是含糊的「咕噜水声」）。每个短促 `effect` 还要给一个本行里**逐字出现**的 `anchor` 短语，标明声音在这句台词里发生的位置。
2. 每条提示交给火山 **seed-audio**（非流式 `POST /api/v3/tts/create`）生成音频。
3. 用 pydub 混音：
   - **行内定时**：短促音效按 `anchor` 在台词中的字数位置（结合该行实际音频时长自校准）放到对应时刻，而不是堆在行首；持续环境声从行首铺底。
   - **不越行**：每条声音在所属台词行末尾硬切并短淡出，不会延续到下一行。
   - **响度平衡**：音效按类型归一化（短音效约 −14 dBFS 压过人声、环境声约 −27 dBFS 垫底），同一行多个音效叠完后整体封顶（含音效 ≤−16、纯环境 ≤−22 dBFS），避免多音效堆叠盖过旁白。
   - 背景音乐循环、归一化到约 −27 dBFS 衬底，近静音的失败素材直接跳过。

### 全局音效库与缓存（省钱）

所有项目共用一个音效目录（默认 `.storyteller/sounds/`），每条声音以「模型 + 归一化提示词 + 格式」的哈希为指纹登记在 `sounds/index.json`：

```json
{
  "id": "snd_ab12…", "name": "雨声", "kind": "ambient",
  "description": "窗外舒缓的下雨声", "tags": ["天气"],
  "prompt": "舒缓的下雨声，无人声", "fingerprint": "…",
  "path": "snd_ab12….mp3", "duration": 6.2, "model": "seed-audio-1.0"
}
```

**相同提示词只生成一次**：再次请求直接命中本地文件、不产生 API 调用。name/description/tags 等字段也为将来「让大模型从库里检索可复用音效」预留。

seed-audio 偶尔会返回近静音的失败素材：这类结果（≤ −55 dBFS 或无法解码）会被**直接丢弃、不写入缓存**，同一提示词下次仍会重新生成，不会永久命中一段废音频。

手动生成 / 检索音效：

```bash
# 生成（已存在相同提示词则命中缓存，不调用接口）
storyteller make-sound "舒缓的下雨声，室内听感，无人声" \
  --name 雨声 --kind ambient --description "窗外雨声" --tags 天气,夜晚

# 列出 / 按关键字或类型检索
storyteller list-sounds
storyteller list-sounds 雨 --kind ambient
```

该功能默认关闭，不带 `--with-sfx` 时流程与产物和之前完全一致。

## 接入其它 OpenAI 兼容服务

LLM 与 TTS 都可通过环境变量追加任意 OpenAI 兼容 provider。下面分别给出 LLM 和 TTS 示例：

LLM 示例：

```bash
export STORYTELLER_LLM_PROVIDERS=volcengine,my_llm
export STORYTELLER_LLM_MY_LLM_TYPE=openai_compatible
export STORYTELLER_LLM_MY_LLM_API_KEY=your-key
export STORYTELLER_LLM_MY_LLM_BASE_URL=https://example.com/v1
export STORYTELLER_LLM_MY_LLM_MODEL=chat-model
# 多个 LLM 时可在命令行用 --default-llm-provider my_llm 选择本次任务
```

TTS 示例：

```bash
export STORYTELLER_TTS_PROVIDERS=volcengine,my-tts
export STORYTELLER_TTS_OPENAI_COMPATIBLE_MY_TTS_NAME=my-tts
export STORYTELLER_TTS_OPENAI_COMPATIBLE_MY_TTS_API_KEY=your-key
export STORYTELLER_TTS_OPENAI_COMPATIBLE_MY_TTS_BASE_URL=https://example.com/v1
export STORYTELLER_TTS_OPENAI_COMPATIBLE_MY_TTS_MODEL=tts-model
```

## 项目状态

项目元数据保存在 `.storyteller/stories/<project_id>/project.json`，状态机：

`topic_collected → script_generated → voice_configured → generating_audio → audio_generated → completed`

任一步中断后，用 `storyteller continue <project_id>` 跳过已完成的步骤继续；已合成的分段音频会被复用。

## 架构

```
src/storyteller/
├── core/
│   ├── pipeline.py         # 流程编排：剧本→配音→合成→拼接
│   ├── story_generator.py  # LLM 剧本生成与解析（含旁白角色兜底注入）
│   ├── voice_matcher.py    # 两阶段 LLM 音色匹配 + 规则回退
│   ├── sound_library.py    # 全局音效库：指纹缓存、检索复用
│   ├── sfx.py              # 音效 provider 抽象（text→sound）
│   ├── audio.py            # 音频拼接 + BGM 衬底/音效叠加（pydub）
│   ├── project.py          # 项目状态与 JSON 序列化
│   ├── config.py           # .env / 环境变量配置
│   └── models.py           # Script / Character / ScriptLine / VoiceConfig
├── providers/
│   ├── volcengine/         # 火山 LLM + v3 seed-tts 流式 TTS + voices.json
│   ├── aliyun/             # 阿里云百炼 Qwen-Audio-TTS + voices.json
│   ├── openai_compatible/  # 任意 OpenAI 兼容服务
│   ├── mock/               # 测试用桩实现
│   └── registry.py         # provider 注册与音色聚合
└── cli/                    # 参数式命令 + 交互式向导
```

## 开发

```bash
pytest                      # 全量测试
pytest tests/unit/test_voice_matcher.py
pytest --cov=storyteller    # 覆盖率
```

## Web 界面（后端）

```bash
pip install -e ".[web,dev]"
cp .env.example .env
storyteller web --host 0.0.0.0 --port 8000
```

配置 `STORYTELLER_WEB_PASSWORDS` 后即可登录。WebSocket `/ws` 使用 cookie
或 token 鉴权，音频线缆标准为 PCM s16le / mono / 24kHz。前端工程见
`web/frontend`，构建产物由 FastAPI 托管。

### 实时 TTS 与调度器

Web 播放时，开场旁白（opening）、固定开播提示（start notice）和正文每一句都走
双向**实时 TTS**：开场会在剧本还没写完时抢先合成、边写边播；正文在音色确定后才
提交文本。某 provider 不支持实时、实时会话失败或入队超时，会自动**降级为整行
HTTP TTS**，不影响出片；CLI 完全不经过这条链路。

- 火山实时语音使用内置的 `websocket-client`，无需额外安装。
- 阿里云**实时**流式 TTS 需要 DashScope SDK（HTTP 非实时 TTS 不需要）：

  ```bash
  pip install -e ".[web,aliyun,dev]"
  ```

  未安装 `dashscope` 时阿里云在 Web 端自动走整行 HTTP TTS。

调度器按 `(provider, model)` 维度维护独立 FIFO 队列、并发槽位、文本限速与背压，
可用下列环境变量调参（均可选，括号内为默认值）：

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `STORYTELLER_TTS_SCHEDULER_MAX_CONCURRENT_SESSIONS` | `1` | 每个 (provider, model) 同时进行的实时会话数 |
| `STORYTELLER_TTS_SCHEDULER_MAX_TEXT_CHUNKS_PER_SECOND` | 空（不限速） | 每会话每秒提交的文本块上限，`0`/留空表示不限 |
| `STORYTELLER_TTS_SCHEDULER_QUEUE_SIZE` | `16` | 排队文本块缓冲深度，满了对上游施加背压 |
| `STORYTELLER_TTS_SCHEDULER_QUEUE_TIMEOUT_SECONDS` | 空（不限时） | 槽位/文本缓冲最长等待；留空或 `0` 表示一直排队 |
| `STORYTELLER_TTS_SCHEDULER_LIMITS_<PROVIDER>_<字段>` | — | 只覆盖某个 provider（名小写，可含下划线），字段同上 |

例：给阿里云更大并发与更深队列——

```bash
STORYTELLER_TTS_SCHEDULER_LIMITS_ALIYUN_MAX_CONCURRENT_SESSIONS=2 \
STORYTELLER_TTS_SCHEDULER_LIMITS_ALIYUN_QUEUE_SIZE=8 \
storyteller web
```

## 许可证

MIT
