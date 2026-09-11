# 原始音效保留与项目内聚设计

日期：2026-09-12
状态：已与用户确认

## 背景

当前 `SoundLibrary.get_or_create` 直接把 provider 生成的音频写入全局音效库 `sounds/snd_<随机id>.mp3`，随即做响度闸门检测；不合格（≤ -55 dBFS 或不可解码）就**删除文件**、不写 index、抛 `SoundGenerationError`（pipeline 宽松模式记 warning 跳过）。由此带来三个问题：

1. 废片被物理删除，无法事后人工收听、判断是提示词问题还是模型问题；
2. 生成素材只存在于全局库，项目目录里没有本次故事用到的音效文件，项目不自包含；
3. 文件名是 `snd_9ae1dd6733cb` 这类无语义随机串，人无法识别。

## 目标

- 每次音效生成都先把**原始音频**写到项目目录，用 cue 的中文名命名，**无论质量好坏永不删除**；
- 全局音效库仍只收录通过响度闸门的素材（跨项目缓存语义不变）；
- 命中全局缓存时也复制一份中文名文件到项目，保证项目自包含；
- `make-sound` 的废片同样保留（暂存目录），并以非零退出码报告闸门失败。

非目标：不改响度闸门阈值与判定逻辑；不改混音逻辑；不改缓存指纹算法；不做素材回放/管理 UI。

## 设计

### 目录语义

| 位置 | 内容 | 命名 | 生命周期 |
|------|------|------|----------|
| `.storyteller/stories/<proj>/sounds/` | 本次故事每个 cue 的音频（合格与废片都在） | cue 中文名，重名加序号 | 随项目，永不自动删除 |
| `.storyteller/sounds/` | 全局精选库（通过闸门） | `snd_<id>.<ext>` + index.json | 不变 |
| `.storyteller/sounds/raw/` | make-sound 生成暂存 | 中文名，重名加序号 | 合格入库后删除；废片保留 |

文件名安全处理：以 cue 名（缺省回退 prompt 前 12 字）做跨平台清洗——去除 `/\:*?"<>|` 及控制字符、折叠空白、去除首尾点号空格；为空时回退 `sfx_<effect_id 短码>`。目标路径已存在时追加 `-2`、`-3`…（同时检查磁盘已有文件，兼容 resume）。扩展名按实际输出格式（pipeline 固定 mp3；make-sound 随 `--format`）。

### SoundLibrary 接口重构

把 `get_or_create` 拆成三个职责：

- `find(provider, prompt, audio_format) -> record|None`：按指纹 `sha256(model|归一化prompt|format)` 查 index，且库文件实际存在才返回（文件被外部删除视同未命中）。
- `path_for(record) -> Path`：已有辅助方法，返回库内文件路径。
- `admit(source_path, provider, *, prompt, name, kind, description, tags, audio_format) -> record`：
  1. 对 `source_path` 做响度闸门（不可解码或 ≤ `MIN_SOUND_DBFS` → 抛 `SoundGenerationError`，**不删除 source_path**）；
  2. 生成 `snd_<id>`，把 source_path **复制**进库目录；
  3. 写 index 记录（字段同现状），返回 record。

`get_or_create` 删除（两个调用方都重写；其测试改写为新接口测试）。

### pipeline `_apply_soundtrack` 改造

对每个待生成 cue（有 prompt 且无 source_path）：

1. 计算项目内目标路径 `<project_dir>/sounds/<安全名>.mp3`（目录按需创建，序号去重）；
2. `library.find(...)` 命中 → 把库文件 `shutil.copy2` 到目标路径，`created=False`；
3. 未命中 → `provider.generate(prompt, 目标路径, audio_format="mp3")`，随后 `library.admit(目标路径, ...)`；
   - `admit` 抛 `SoundGenerationError`（废片）或 generate 抛任何异常：记 warning，**文件保留**，`cue.source_path` 保持为空 → 该 cue 不参与混音（与现状一致），continue；
   - 成功 → `created=True`；
4. 成功的 cue：`source_path` 指向**项目内文件**、`source_type="local"`、回填 duration，日志与现状一致（命中标 cached）。

后续混音阶段零改动（它只认 `cue.source_path`）。废片文件物理存在但不被引用，因此不会被混入。

### make-sound 改造

1. `library.find(...)` 命中且文件存在 → `Cache hit (no API call): <库路径>`，退出 0（行为不变，不产生 raw 文件）；
2. 未命中 → 生成到 `sounds/raw/<安全名>.<ext>`；
3. `library.admit(raw, ...)`：成功 → 删除 raw、打印 `Generated: <库路径>`；失败（SoundGenerationError）→ **保留 raw**，打印警告与 raw 完整路径，以 ClickException（退出码 1）结束。

### 文档与记忆

- README「音效与背景音乐」段补充：项目目录 `sounds/` 保留全部原始素材（含未通过闸门的废片）及其用途；全局库只收录合格素材；make-sound 废片在 `sounds/raw/`。
- 完成后更新记忆 storyteller-project.md 的音效段（目录语义与新接口）。

## 测试（全部本地，无真实 API）

- SoundLibrary 单测：`find` 指纹命中/文件丢失视同未命中；`admit` 合格素材复制入库+写 index+返回 record；`admit` 近静音/假字节抛错且**源文件保留**、index 不增长；`get_or_create` 已移除。
- 文件名工具单测：非法字符清洗、空名回退、序号去重。
- pipeline e2e（mock provider）：缓存未命中 → 项目 `sounds/` 有中文名文件、全局库有 snd_ 副本、cue.source_path 指向项目文件；缓存命中（预置库记录）→ 项目目录得到中文名副本且不调 provider；废片（静音 stub provider）→ 项目里保留文件、warning、不混音、库中无记录。
- CLI make-sound e2e：成功路径 raw 暂存被清理；废片路径 raw 文件保留、退出码非 0 且输出含 raw 路径。

## 风险与取舍

- 项目目录体积增大：每个 cue 多一份原始音频（废片也占空间）；这是用户明确要的可追溯性，文件在项目内，用户可自行清理。
- resume 时失败 cue 会重试并生成 `-2` 文件（旧废片保留），符合"永不删除"语义。
- 全局库仍只增精选，跨项目缓存与指纹省钱逻辑完全不变。
