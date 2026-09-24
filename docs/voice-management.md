# Web 音色管理

音色管理页位于 `/voices`，需要先登录 Web。它读取所有已注册 TTS provider 的 catalog，并把 provider 原始元数据与本地 override、故事生成片段合并。接口细节见 [Voices API](api/voices.md)。

## 列表、展示和筛选

页面每页固定请求 50 条，并显示总数。当前可组合的服务端筛选是：

| 页面字段 | API 参数 | 行为 |
| --- | --- | --- |
| Provider | `provider` | 与注册名精确相等 |
| 模型 | `model` | 与 catalog 的模型值精确相等 |
| 性别 | `gender` | 与 `male`/`female` 等 catalog 值精确相等 |
| 年龄 | `age` | 目标枚举存在于音色的年龄数组中 |
| 状态 | `status` | `all`、`enabled` 或 `disabled` |

响应的 `filters.providers/models/genders/ages` 从未筛选的完整 catalog 计算，所以切换某个筛选后，其余下拉仍显示全局可选值。空值表示“全部”。

每行还展示 `voice_id`、名称、`category`、`tags` 和 `description`。这些字段帮助人工判断声音风格，但当前页面和 `GET /api/voices` **没有** category、tag、description 或自由文本筛选参数。它们不是隐藏的客户端筛选；需要按这些字段查找时只能在返回 JSON 中自行处理。

目录记录的稳定管理 key 是：

```text
provider|model|voice_id
```

缺少模型时使用字面值 `unknown`。同一个 `voice_id` 出现在不同 provider 或模型时会显示为不同记录，修改也互相隔离；调用 API 时必须 URL 编码整个 key。

## 编辑年龄数组

每个音色可以勾选零个或多个年龄：

- `child`：儿童；
- `teen`：少年；
- `young_adult`：青年；
- `middle_aged`：中年；
- `senior`：老年。

保存会 `PATCH /api/voices/{voice_key}` 并提交完整数组，不是增量增加单项。服务端拒绝非字符串、未知枚举和重复项，持久化时按上述年龄顺序排序；空数组合法，表示没有年龄声明。保存失败时当前页面把勾选恢复为服务端最后一次成功返回的值并显示错误。

年龄 override 不修改 provider 自带的 catalog 文件。`ProviderRegistry.list_tts_voices()` 返回音色时会把 override 应用到 `VoiceConfig` 的副本，所以新的匹配调用立即使用内存中的新年龄；正在运行且已经完成音色分配的任务不会被重写。

## 启用和禁用

音色默认启用。点击“禁用音色”或“启用音色”会独立提交布尔 `enabled`：

- Web catalog 总是以 `include_disabled=True` 聚合音色，所以被禁用的记录仍能在 `status=all/disabled` 中查看、编辑、重新启用和查看旧片段；
- 常规 `ProviderRegistry.list_tts_voices()` 默认排除禁用项，因此后续 CLI/Web 的 LLM 和 rule 匹配都不会选择它；`storyteller list-voices` 等普通 registry 列表也看不到禁用项；
- 已保存项目里的旧 `voice_config` 和已有音频不会被删除，正在运行且已选定该音色的任务也不会被追溯改写。

如果筛选后没有记录，先切回 `status=all`，再清除 provider/model/gender/age 条件。禁用最后一个可用音色可能使后续生成报“没有可用 TTS 音色”。

## 试听片段从哪里来

“试听片段”不是 provider 提供的 demo，也不会临时调用 TTS。`VoiceClipCatalog` 每次请求都会扫描 `<project_dir>` 下可加载项目的已保存剧本和分句 MP3：

1. 优先使用 line 自己的 `voice_config`；
2. 否则使用对应角色的 `voice_config`；
3. narration 仍未找到时，尝试 id 为 `narrator` 的角色音色；
4. 只接受项目目录内部实际存在的 `.mp3` 文件，优先 line 的 `audio_path`，再尝试 `audio/<line_id>.mp3`。

列表展示故事标题、角色名、台词和项目创建时间，并按时间从新到旧排序。当前 `duration_ms` 固定为 `null`。损坏项目、缺失音频、项目目录外路径和非 MP3 文件会被跳过，不会阻断其他片段。

旧项目的 line 音色可能没有 `model`。系统先用 `provider|unknown|voice_id` 查找；如果 catalog 中只有一个记录同时匹配 provider 和 `voice_id`，则改为归到该唯一模型。多个模型共享同一个标识时不会猜测具体模型：若 catalog 本身有 `model=null` 的 `unknown` 记录，片段仍归到该记录；否则不会归到任一条管理记录。页面显示“暂无故事生成片段”时不会自动生成试听。

音频 URL 由 `voice_key` 和 `clip_id`（`project_id:line_id`）构成。服务端重新解析 catalog 后才发送 `audio/mpeg`，并拒绝含 `/` 或 `\` 的不安全片段 id。

## 本地持久化

年龄和启用状态保存在：

```text
<data_dir>/config/voice-overrides.json
```

文件以 `provider|model|voice_id` 为 key，每项可含 `age`、`enabled` 和 UTC `updated_at`。一次更新只修改提交的字段，并保留同一音色的另一个字段。写入流程在同目录创建临时文件、flush/fsync 后用 `os.replace()` 原子替换；不会留下正常完成的 `.tmp` 文件。

服务启动时读取一次 override 文件。文件不存在、不可读、JSON 损坏或顶层不是对象时，当前实现静默回退为空 override，也不会自动修复原文件。provider/模型/voice id 改名会产生新的 key，旧 key 不再生效。

## 备份、恢复和重置

项目没有为 `voice-overrides.json` 创建自动历史或滚动备份。应把它和项目数据一起纳入备份：

```bash
VOICE_DATA_DIR="${STORYTELLER_DATA_DIR:-./.storyteller}"
cp "$VOICE_DATA_DIR/config/voice-overrides.json" "./voice-overrides.backup.json"
```

恢复时先停止 Web/CLI 生成进程，确认备份是 JSON 对象，再复制回同一 data directory 的 `config/voice-overrides.json`，最后重启服务。必须重启，因为已创建的 `VoiceOverrideStore` 不会自动重新读取磁盘。恢复文件中的 key 只有在当前 catalog 仍存在相同 provider、model 和 voice id 时才会生效。

需要恢复 provider 默认值时，也应在服务停止后把当前文件移到备份位置或用确认过的空对象 `{}` 替换，再重启。不要只在服务运行时删除文件：进程内仍保留已经加载和刚修改过的 override，下一次页面修改可能再次写回。

## 故障排查

- 列表请求 401：重新登录，确认浏览器携带 `storyteller_session` cookie。
- 修改后重启失效：检查实际 `STORYTELLER_DATA_DIR` 和 `<data_dir>/config/voice-overrides.json`，以及 key 中的 model 是否改变。
- 页面有音色但匹配池为空：检查 `status=disabled`、调用方 provider/voice allowlist，以及是否把所有允许音色禁用。
- 片段计数为 0：确认项目可加载、line/角色保存了 voice config，并且分句文件是项目目录内存在的 `.mp3`。
- 两个模型共用 voice id 但旧片段没有 model：系统不会随机选择具体模型；检查是否存在 `model=null` 的 `unknown` 记录，否则现有片段会被忽略。
