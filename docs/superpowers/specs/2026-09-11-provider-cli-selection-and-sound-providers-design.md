# Provider 命令行选用与音效 Provider 独立化 设计文档

日期：2026-09-11
状态：待评审

## 背景与动机

一次「完全用阿里云 TTS + 音效」的真实运行暴露了三个摩擦点：

1. `--tts-providers aliyun` 只在已注册集合里过滤；provider 必须先写进
   `STORYTELLER_TTS_PROVIDERS` 名单才会注册，命令行无法选用「已配 key 但未列名单」
   的 provider，每次切换都要改 `.env`。
2. `continue` 子命令缺少 `--default-tts-provider`（generate 有），只能靠环境变量
   覆盖默认 provider。
3. 音效只有火山一家实现，且 `VolcengineSoundProvider` 在 pipeline 和
   `make-sound` 里都是硬编码；音效 key 缺省时回退复用 TTS key。当 TTS 只用阿里云、
   火山 TTS provider 未注册时，这个回退找不到 key，音效阶段必然失败。

## 目标

1. **配置即注册 + CLI 选用**：`.env` 中为某 provider 配了参数（API_KEY/TYPE 等），
   它就自动注册、可被命令行选用，不必修改 `*_PROVIDERS` 名单。LLM、TTS、音效三类
   provider 行为一致。
2. **音效成为独立 provider 分组**：与 llm/tts 同构的
   `STORYTELLER_SOUND_*` 配置、注册表与命令行选择参数；音效 key 独立，**不回退**
   到 TTS key。
3. 命令行可以为 `generate` / `continue` / `make-sound` 指定音效 provider。
4. 交互式向导可以开关音效并选择音效 provider。

## 非目标（明确不做）

- 不实现阿里云或其他第二家音效 provider（只预留类型分发位置）。
- 不做旧环境变量 `STORYTELLER_SFX_VOLCENGINE_*` 的向后兼容；用户一次性改 `.env`。
- 不提供「配了 key 但对匹配器隐藏」的开关；配置即视为有意使用。
- 不改音效生成、混音、缓存（SoundLibrary）的任何既有行为。
- 不改 OpenAI 兼容 provider 现有的 `STORYTELLER_TTS_OPENAI_COMPATIBLE_*` 声明方式。

## 已确认的设计决策

| # | 决策 |
|---|------|
| 1 | 音效采用 `STORYTELLER_SOUND_*` 分组命名，旧 `STORYTELLER_SFX_VOLCENGINE_*` 不再读取，不做兼容 |
| 2 | 「配置即注册 + CLI 选用」：按环境变量存在自动发现注册；`*_PROVIDERS` 变为可选的默认启用/排序列表；LLM 同步改造 |
| 3 | 音效 key 只从 `STORYTELLER_SOUND_<NAME>_API_KEY` 读取，缺失即报错，不回退 TTS key |
| 4 | 范围包含：LLM 自动注册对齐、`make-sound --sound-provider`、向导音效提问 |

## 配置模型（Config）

### 环境变量约定（三类 provider 统一）

| 变量 | 作用 |
|------|------|
| `STORYTELLER_<KIND>_PROVIDERS` | **可选**。逗号分隔的默认启用名单，同时决定排序；未列出的 provider 仍会被自动发现注册 |
| `STORYTELLER_<KIND>_DEFAULT_PROVIDER` | 默认 provider 名 |
| `STORYTELLER_<KIND>_<NAME>_TYPE` | 实现类型：`volcengine`（缺省）/ `aliyun`（仅 TTS）/ `openai_compatible`（llm、tts）/ `mock` |
| `STORYTELLER_<KIND>_<NAME>_API_KEY` | 该 provider 独立 key |
| `STORYTELLER_<KIND>_<NAME>_MODEL` / `_ENDPOINT` / `_BASE_URL` / `_RESOURCE_ID` | 同现状 |

`<KIND>` ∈ `LLM` / `TTS` / `SOUND`。

音效分组新增变量：

```bash
STORYTELLER_SOUND_PROVIDERS=volcengine        # 可选
STORYTELLER_SOUND_DEFAULT_PROVIDER=volcengine # 可选
STORYTELLER_SOUND_VOLCENGINE_API_KEY=...      # 独立音效 key，不再回退 TTS key
STORYTELLER_SOUND_VOLCENGINE_MODEL=seed-audio-1.0
# STORYTELLER_SOUND_VOLCENGINE_ENDPOINT=https://openspeech.bytedance.com/api/v3/tts/create
```

`STORYTELLER_SOUND_ENABLED` 与 `STORYTELLER_SOUND_DIR` 语义不变。

### `config.py` 改动

1. `DEFAULTS.sound` 增加 `"providers": []` 与 `"default_provider": None`。
2. `from_env` 中：`_load_provider_group(config, "llm")`、
   `_load_provider_group(config, "tts")` 之外增加
   `_load_provider_group(config, "sound")`；`_load_sound` 只保留
   `SOUND_ENABLED` / `SOUND_DIR` 两项读取，删除 `STORYTELLER_SFX_VOLCENGINE_*`
   读取逻辑。
3. `_load_provider_group` 改为两阶段：
   - 先读 `*_PROVIDERS` 名单（显式名单，按其顺序）；
   - 再扫描 `os.environ` 中所有形如
     `STORYTELLER_<KIND>_<NAME>_<TYPE|API_KEY|MODEL|ENDPOINT|BASE_URL|RESOURCE_ID>`
     的变量，把发现的 `<NAME>` 并入名单。
   - 保留名跳过：`<NAME>` 为 `PROVIDERS`、`DEFAULT_PROVIDER` 时永不视为 provider；
     sound 分组另外跳过 `ENABLED`、`DIR`；TTS 分组跳过 `OPENAI_COMPATIBLE` 前缀
     （那条路径仍由 `_load_openai_compatible_tts` 处理，它照旧把名字 append 进
     `tts.providers`，去重）。
   - 最终顺序：显式名单在前（去重），自动发现的名字按字母序追加（保证跨平台确定性）。
   - 每个名字的 per-provider 配置读取与现状相同（六个字段，存在即写入；
     至少一个变量存在才写 `provider_config`）。
4. 判定「已配置」的标准与现状一致：至少存在一个该 provider 的变量即注册；
   缺 key 等问题在实例化/调用时由 provider 构造函数报错（延迟实例化，注册本身不触网、
   不构造）。

## Registry 改动

`ProviderRegistry` 增加与 TTS 同构的音效段：

- `register_sound(name, factory)`
- `get_sound(name)`：未知名抛 `ProviderError("Unknown sound provider: <name>")`，
  懒加载并缓存实例
- `set_default_sound(name)` / `get_default_sound()`
- `list_sound_names()`

LLM/TTS 既有接口不变。

## Bootstrap 改动

- `register_providers_from_config` 增加 `_register_sounds(config, registry)` 与
  `_set_defaults` 中的 sound 分支（默认名未注册时同样吞掉 `ProviderError`）。
- 类型分发：
  - `type == "mock"` → `MockSoundProvider`
  - `type == "volcengine"` 或未指定 type → `VolcengineSoundProvider`
  - 其他类型（含 `aliyun`、`openai_compatible`）→ 安静跳过（暂无音效实现，
    与 LLM 段「无匹配实现则跳过」一致）。
- 顶部新增 `VolcengineSoundProvider` / `MockSoundProvider` 的 ImportError 防护导入。

## Provider 改动：VolcengineSoundProvider

`src/storyteller/providers/volcengine/sfx.py`：

- 构造函数只读取 `sound.provider_config.<注册名>`。该 provider 目前以注册名
  `volcengine` 使用，故读取 `sound.provider_config.volcengine`（与 TTS provider
  读 `tts.provider_config.volcengine` 的既有模式一致）。
- **删除** `tts.provider_config.volcengine` 的 key 回退（第 29、31 行）。
- 缺 key 的错误改为：

  > `Volcengine sound api_key is missing: set STORYTELLER_SOUND_VOLCENGINE_API_KEY`

- endpoint/model 缺省值不变。类 docstring 同步更新。

## Pipeline 改动

`_get_sound_provider` 选择优先级：

1. 构造时注入的 `sound_provider`（测试用，最高优先，现状不变）；
2. `self.registry.get_sound(name)`，`name` 取
   `config.get("sound.default_provider")`；
3. 默认名为空时取 `registry.list_sound_names()[0]`；
4. 一个音效 provider 都没注册 → 抛 `TTSError`：

   > `No sound provider configured: set STORYTELLER_SOUND_<NAME>_API_KEY
   > (use --sound-provider to choose one)`

删除方法内对 `VolcengineSoundProvider` 的硬编码 import 与直接实例化。

音色匹配前增加 CLI 选用校验（第 2 步开头）：`kwargs["tts_providers"]` 中若有名字
不在 `registry.list_tts_names()`，立即抛 `TTSError`：

> `Unknown TTS provider(s): aliyun. Configured: volcengine. Configure it with
> STORYTELLER_TTS_ALIYUN_API_KEY (and STORYTELLER_TTS_ALIYUN_TYPE for non-Volcengine
> implementations), or pick from the configured list.`

`voice_matcher.py:206` 原有的 "No TTS voices available for providers: ..."
保留为候选池为空时的第二层错误。

## CLI 改动（`cli/main.py`）

### generate / continue 对齐

- `generate`、`continue` 均新增：
  - `--sound-provider NAME`：覆盖本次运行的音效 provider（写入
    `sound.default_provider`，与 `--default-tts-provider` 写 config 的方式相同）。
- `continue` 补齐已有选项的参数对等：`--default-llm-provider`、
  `--default-tts-provider`（其余如 `--length`/`--progress` 等不在本次范围）。
- `_build_pipeline` 在 bootstrap 注册之后做一次音效选用校验：CLI 显式传了
  `--sound-provider` 且名字不在 `registry.list_sound_names()` 时，以 `ClickException`
  提前失败并列出已注册音效 provider 名（错误在任何 LLM/TTS 花费前发生）。
- `--with-sfx` 仍是音效开关，语义不变（单向开启；默认关）。

### make-sound

- 新增 `--sound-provider NAME`（可选）。
- 改为：`Config.from_env()` → 应用 `--sound-dir` → 直接构造
  `ProviderRegistry(config)` 并 `register_providers_from_config(config, registry)`
  （不经过 Pipeline，避免无关的 ProjectManager 初始化）→ 按
  `CLI 参数 > sound.default_provider > 首个已注册音效 provider` 解析并
  `registry.get_sound(name)`；未配置任何音效 provider 时报清晰错误。
- 删除对 `VolcengineSoundProvider` 的硬编码 import/实例化。

## 交互式向导改动（`cli/interactive.py`）

在格式选择之后、确认配置附近新增两个提问（pipeline 已构建、registry 可用之后）：

1. 「是否启用音效与背景音乐？」是/否，默认否（回车=否；`STORYTELLER_SOUND_ENABLED`
   为 true 时默认是）。
2. 仅当选「是」**且** `registry.list_sound_names()` 多于一个时，列出编号让用户选
   音效 provider；0 或 1 个时不提问（0 个的情况下交由后续运行时报配置错误，
   向导里不提前失败）。

`run_wizard` 返回值扩展，携带 `with_sfx: bool` 与 `sound_provider: str|None`；
`cli/main.py` 的 `wizard` 命令把它们写进 config 后再 `pipeline.run(...)`。
向导的 TTS provider 选择仍维持现状（`_prompt_voice_mode` 占位），本次不动。

## 错误处理汇总

| 场景 | 行为 |
|------|------|
| `--tts-providers aliyun` 但完全未配置 | pipeline 提前抛 TTSError，列出已配置名与所需环境变量 |
| `--sound-provider foo` 未注册 | CLI 在任何生成前 ClickException，列出已注册音效名 |
| `--with-sfx` 但无音效 provider/key | 音效阶段 TTSError，提示 `STORYTELLER_SOUND_<NAME>_API_KEY`（不再提示可复用 TTS key） |
| `SOUND_DEFAULT_PROVIDER` 指向未注册名 | bootstrap 安静忽略；落到首个已注册音效 provider，与 llm/tts 默认行为一致 |

## 测试策略（TDD，全部为本地测试，不触真实 API）

沿用 FakeSession/FakeResponse 与 mock provider 既有风格：

1. **config 单测**
   - 仅有 `STORYTELLER_TTS_ALIYUN_API_KEY`（无 `TTS_PROVIDERS`）→ aliyun 被发现注册；
   - 名单与发现并存时：名单在前、发现项按字母序追加、去重；
   - 保留名不被误判为 provider（`SOUND_ENABLED`/`SOUND_DIR`/`*_PROVIDERS`/
     `DEFAULT_PROVIDER`）；
   - sound 分组加载 `API_KEY/MODEL/ENDPOINT` 与 default；
   - 设置旧 `STORYTELLER_SFX_VOLCENGINE_API_KEY` 后 `sound.provider_config` 为空
     （锁定不兼容决策）；
   - LLM 自动发现与 TTS 行为一致；
   - OpenAI 兼容声明路径仍生效且不重复注册。
2. **registry 单测**：sound 的 register/get（含懒加载、未知名 ProviderError）/
   default/list。
3. **bootstrap 单测**：按 `sound.providers` 注册 mock 与 volcengine；
   `type=aliyun` 等未支持类型安静跳过；sound default 设置。
4. **VolcengineSoundProvider 单测/集成测试**：删除
   `test_reuses_tts_key_when_sound_key_absent`，替换为「只有 TTS key 没有
   SOUND key 时构造失败、错误信息指向 `STORYTELLER_SOUND_VOLCENGINE_API_KEY`」。
5. **pipeline 测试**：
   - 注入 provider 仍为最高优先（现有 e2e 测试不改）；
   - 未注入时从 registry 按 default/首个解析音效 provider；
   - 无任何音效 provider 且 with-sfx 时抛新 TTSError；
   - `tts_providers` 含未知名时在匹配前报错并带配置提示。
6. **CLI e2e（CliRunner + mock env）**：
   - mock env 增补 `STORYTELLER_SOUND_PROVIDERS=mock`、
     `STORYTELLER_SOUND_MOCK_TYPE=mock`（追加到 `_MOCK_ENV`，对现有测试无害）；
   - `generate --with-sfx --sound-provider mock` 跑通并调用 MockSoundProvider；
   - `--sound-provider nope` 退出码非 0、输出已注册名；
   - `continue --default-tts-provider mock --default-llm-provider mock
     --sound-provider mock` 参数被接受（help/调用层面覆盖）；
   - `make-sound --sound-provider mock` 走 registry 生成；未配置音效 provider 时
     报错友好；
   - 向导：更新现有向导测试的输入序列，覆盖「启用音效 + 多 provider 选择」与
     「默认不启用」两条输入路径。
7. 全量 `.venv/bin/python -m pytest -q` 绿；测试数量随新增用例增长，不允许减少断言。

## 文档与迁移

`.env.example`：

- LLM/TTS 段注释更新：`*_PROVIDERS` 标注为可选（默认启用/排序），配了 key 即可被
  CLI 选用；
- 删除整个 `STORYTELLER_SFX_VOLCENGINE_*` 块，替换为
  `STORYTELLER_SOUND_PROVIDERS/DEFAULT_PROVIDER/SOUND_VOLCENGINE_{API_KEY,MODEL,ENDPOINT}`
  块，注释写明音效 key 独立、必填才能用音效。

`README.md`：

- 配置表：删 SFX 行，加 SOUND 分组三行；`*_PROVIDERS` 语义改为可选；
- generate/continue/make-sound 三个参数表加 `--sound-provider`，
  continue 加 `--default-llm-provider/--default-tts-provider`；
- 「音效与背景音乐」段：环境变量改名、独立 key、provider 选择方式；
- 「接入阿里云」段：把「把 aliyun 加入 PROVIDERS」改为「配置即可被
  `--tts-providers aliyun` 选用，`PROVIDERS` 仅控制默认启用与排序」；
- 明确标注这是破坏性变更（旧 SFX 变量不再生效）。

用户本机 `.env` 需手工迁移一次：

```bash
# 旧
STORYTELLER_SFX_VOLCENGINE_API_KEY=<key>
# 新
STORYTELLER_SOUND_VOLCENGINE_API_KEY=<key>
```

## 涉及文件一览

| 文件 | 改动 |
|------|------|
| `src/storyteller/core/config.py` | DEFAULTS、group loader 自动发现、`_load_sound` 精简 |
| `src/storyteller/providers/registry.py` | sound 注册段 |
| `src/storyteller/providers/bootstrap.py` | `_register_sounds`、默认值、导入 |
| `src/storyteller/providers/volcengine/sfx.py` | 删 TTS key 回退、错误文案 |
| `src/storyteller/core/pipeline.py` | `_get_sound_provider` 走 registry；tts 选用校验 |
| `src/storyteller/cli/main.py` | 三个子命令新参数、make-sound 走 registry、向导接线 |
| `src/storyteller/cli/interactive.py` | 音效开关/provider 提问、返回值扩展 |
| `tests/unit/`、`tests/e2e/`、`tests/integration/` | 上述测试策略各条 |
| `.env.example`、`README.md` | 迁移与文档 |
