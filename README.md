# Storyteller

把一句话主题变成**带角色配音的音频故事**：LLM 写剧本 → 大模型为每个角色匹配音色 → TTS 逐句合成 → 拼接成一个 MP3。

- 多角色对话 + 旁白，剧本为结构化 JSON
- 大模型两阶段匹配音色：先判定角色性别/年龄，再在音色库里按音色描述精选
- 每句台词自动生成演法指令（情绪/语气），并引用上文保持情感连贯
- 可选音效与背景音乐：LLM 产出声音提示，seed-audio 生成并自动混音，结果进全局音效库缓存复用
- 火山引擎 LLM + 语音合成（seed-tts 2.0），同时支持任意 OpenAI 兼容服务
- 项目状态持久化，支持断点续作
- CLI 参数模式 + 交互式向导

## 安装

需要 Python ≥ 3.8，音频拼接依赖 [ffmpeg](https://ffmpeg.org/)（pydub 后端）。

```bash
pip install -e .[dev]
```

## 配置

密钥通过环境变量 / `.env` 管理。**`.env.example` 入库且只含占位符；真实 `.env` 已被 gitignore，禁止提交。**

```bash
cp .env.example .env
# 编辑 .env 填入凭据
```

需要配置两套互相独立的密钥：

| 变量 | 说明 |
|------|------|
| `STORYTELLER_LLM_VOLCENGINE_API_KEY` | 火山方舟（Ark）LLM Key |
| `STORYTELLER_LLM_VOLCENGINE_MODEL` | 默认 `deepseek-v4-flash-260425` |
| `STORYTELLER_LLM_VOLCENGINE_ENDPOINT` | `https://ark.cn-beijing.volces.com/api/v3` |
| `STORYTELLER_TTS_VOLCENGINE_API_KEY` | 语音合成 Key（**与 LLM Key 不同**） |
| `STORYTELLER_TTS_VOLCENGINE_RESOURCE_ID` | 默认 `seed-tts-2.0` |
| `STORYTELLER_TTS_VOLCENGINE_ENDPOINT` | v3 单向流式接口 `/api/v3/tts/unidirectional` |
| `STORYTELLER_DATA_DIR` | 生成物根目录，默认 `./.storyteller`（内含 `stories/`、`sounds/`） |
| `STORYTELLER_OUTPUT_DIR` / `STORYTELLER_PROJECT_DIR` | 分别覆盖故事产物/状态目录，默认都在 `<DATA_DIR>/stories` |
| `STORYTELLER_VOICE_MATCHER` | `llm`（默认，语义匹配）或 `rule`（仅关键字规则） |
| `STORYTELLER_SOUND_ENABLED` | `true/false`，是否生成音效/背景音乐（默认关） |
| `STORYTELLER_SOUND_DIR` | 全局共享音效库目录，默认 `<DATA_DIR>/sounds` |
| `STORYTELLER_SFX_VOLCENGINE_API_KEY` | 音效 Key（seed-audio），留空则复用 TTS Key |

## 使用

### 参数模式

```bash
# 最简：生成并输出到 .storyteller/stories/<project_id>/story.mp3
storyteller generate "一只小猫的冒险"

# 常用选项
storyteller generate "数字积木的故事" \
  --length short \          # short | medium | long
  --complexity simple \     # simple | medium | rich
  --output-format mp3 \     # mp3 | wav | ogg
  --voice-matcher llm \     # llm（默认）| rule
  --with-sfx                # 生成音效/背景音乐并自动混音（默认关闭）
```

只生成剧本、不合成音频（剧本会保存为 JSON）：

```bash
storyteller generate "月亮婆婆" --dry-run
# → .storyteller/stories/<project_id>/story.script.json
```

### 交互式向导

```bash
storyteller
```

按提示依次输入主题、长度、复杂度、输出格式。

### 其它命令

```bash
storyteller continue <project_id>   # 从断点继续
storyteller list-projects           # 列出所有项目及状态
storyteller list-voices             # 列出可用音色
```

通用选项：`--data-dir`（生成物根目录，默认 `./.storyteller`）、`--progress quiet|simple|detailed`、`--strict-mode`、`--log-level`。

> 生成过程是网络密集型：剧本 + 音色分类/精选各有一次 LLM 调用，随后逐句 TTS。一个短篇通常需要几十秒到几分钟，期间无逐字输出属正常现象，可用 `--progress simple` 查看进度。

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
        "voice_type": "child", "age": "child", "name": "亮嗓萌仔"
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

默认 `llm` 模式分两步，把「关键词硬猜」降级为兜底：

1. **角色分类（LLM 调用一）**：根据角色名 + 描述判定性别（male/female）与年龄段（child/teen/young_adult/middle_aged/senior）。旁白角色按 id/名称确定性识别。
2. **音色精选（LLM 调用二）**：按分类结果把内置音色库过滤成候选池，再让模型结合每个音色的名称、分类、描述挑选最贴切的一个（例如「慈祥老婆婆」会选中老年温和女声，而不是年轻御姐音）。

任一步调用失败或返回非法结果，对应角色自动回退到关键字规则匹配，不影响出音频。可用 `--voice-matcher rule` 或 `STORYTELLER_VOICE_MATCHER=rule` 完全走规则（不产生额外 LLM 调用）。

内置火山音色库约 249 个（仅 seed-tts-2.0，含中英文混读音色），由 `scripts/build_voice_catalog.py` 从 `data/` 下的官方清单整理生成，打包在 `src/storyteller/providers/volcengine/voices.json`。

## 演法指令与上文引用

每句对话，LLM 会生成一条不超过 20 字的自然语言 `direction`（如「又急又委屈，带着哭腔」），合成时通过火山 TTS 的 `additions.context_texts` 传递：

- 以 `#` 开头的演法指令：控制情绪/语气，**不会被朗读**；
- 不带 `#` 的引用上文（最近一句旁白/对话）：不合成，仅让模型承接场景情绪。

## 音效与背景音乐

`--with-sfx`（或 `STORYTELLER_SOUND_ENABLED=true`）开启后：

1. 写剧本的 LLM 会额外产出**可选**的声音提示——顶层一条贯穿全剧的 `background_music`，以及个别台词行的 `sound_effects`（`effect` 短促音效 / `ambient` 持续环境声）。提示遵循「宁缺毋滥、只描述声音本身、不含任何人声台词」。
2. 每条提示交给火山 **seed-audio**（非流式 `POST /api/v3/tts/create`）生成音频。
3. 用 pydub 把背景音乐循环、归一化到统一衬底响度（约 −27 dBFS，首尾淡入淡出）铺在人声下，音效按所在行的时间点叠加（近静音的失败素材会被跳过），写回最终 MP3。

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

LLM 与 TTS 都可通过环境变量追加任意 OpenAI 兼容 provider。TTS 示例：

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

## 许可证

MIT
