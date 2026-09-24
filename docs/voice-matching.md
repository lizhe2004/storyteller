# 角色与音色匹配

本文描述当前 `VoiceMatcher` 如何把剧本角色映射到 TTS 音色。`provider`、`model`、`voice_id` 的配置语义见[配置参考](configuration.md)，音色的编辑和禁用见[音色管理](voice-management.md)。

## 输入与入口

剧本中的每个 `Character` 提供以下匹配输入：

- `id`、`name`、`description`；
- `gender`：`male` 或 `female`；
- `age`：`child`、`teen`、`young_adult`、`middle_aged` 或 `senior`；
- `voice_preferences`：按 `type`（音色分类）和正权重描述偏好；
- 最终写回的 `voice_config`。

剧本生成提示词要求每个非旁白角色填写 `gender`、`age`、`description` 和 `voice_preferences`。有效的 `gender`/`age` 是后续匹配的权威输入；它们应由剧本描述角色本身，而不是让匹配器从 provider、模型名或音色名猜角色身份。

为兼容旧项目或不完整剧本，非旁白缺少合法字段时，`VoiceMatcher.match_voices()` 才会从角色名和描述推断：性别按显式性别、亲属称谓和代词判断，无法判断时默认 `male`；年龄先识别“5岁”一类数字，再识别儿童、少年、中年、老年关键词，无法判断时默认 `young_adult`。这种回退可能误判，所以新剧本不应依赖它。

匹配的主要入口是：

- CLI/同步生成：`Pipeline._execute_pipeline()` 创建 `VoiceMatcher`，传入配置的 matcher 模式、允许的 TTS providers 和可选 `voice_ids`；
- Web 生成：`StreamOrchestrator` 创建 `VoiceMatcher`，传入当前任务的 LLM、TTS providers，以及 `job_id`、`project_id`、`phase=voices` 日志上下文；
- 实际分配：`VoiceMatcher.match_voices()`；候选采样：`_sample_voice_candidates()`；规则选择：`_rule_pick()`。

## 当前数据流

```text
剧本 Character
  │  有效 gender/age 直接使用；旧数据才从 name + description 推断
  ▼
识别旁白并把旁白排在其他角色之前
  │  _is_narrator(): id/name 含 旁白、narrator、说书、叙述
  ▼
ProviderRegistry.list_tts_voices()
  │  限定 allowed_providers / allowed_voice_ids
  │  应用本地年龄 override
  │  默认删除 disabled 音色
  ▼
每个角色的候选池（LLM 模式，每角色最多 10 个）
  │  性别池 → 有精确年龄则年龄池 → 分类偏好加权采样
  │  event=voice_matching_character_candidates
  ▼
按 voice_id 合并候选并稳定排序，构造完整 prompt
  │  event=voice_matching_prompt
  ▼
LLM 返回 assignments JSON
  │  event=llm_request_* / event=voice_matching_llm_response
  ▼
校验角色 id、整数下标、范围、重复下标和对话角色性别
  │  无效或缺失的角色分配被丢弃
  ▼
逐角色规则回退；优先未使用 voice_id，耗尽后才复用
  ▼
Character.voice_config + event=voice_matching_completed
```

没有可用音色时，`match_voices()` 抛出 `ProviderError`，不会虚构默认音色。

## 候选池规则

### Provider、模型和禁用状态

`ProviderRegistry` 聚合当前已注册且被调用方允许的 provider 音色。`allowed_voice_ids` 只按 `voice_id` 过滤；本地 override 随后替换年龄数组，`enabled: false` 的音色默认被删除。因此禁用状态同时影响 LLM 和 rule 模式。

匹配算法不硬编码 `aliyun`、`volcengine` 或任何模型名。新增 provider/模型只要注册并返回统一的 `VoiceConfig` 元数据（特别是 `gender`、`age`、`category`、`description`），就进入相同流程。把 provider/model 写成角色规则会让业务语义依赖厂商命名，也会使新增模型绕过统一匹配。`default_provider` 只是 `_rule_pick()` 的可选优先项；当前 CLI/Web 调用没有传入它。

候选合并当前按 `voice_id` 去重，规则去重也按 `voice_id` 记录已使用项，而不是按 Web 管理用的 `provider|model|voice_id` key。多个 provider/模型复用同一个 `voice_id` 时，匹配阶段会把它们视为同一标识；管理页面仍会把它们显示为不同记录。

### 性别与年龄

对具有目标性别的角色，`_gender_pool()` 依次选择：

1. 精确 `male`/`female` 音色；
2. 如果不存在精确项，选择没有性别元数据的音色；
3. 如果连中性项也没有，才保留全部音色。

所以性别是强优先约束，但在目录没有可用同性别音色时，规则模式会降级到中性乃至任意音色。LLM 结果校验更严格：任何具有目标性别的角色（包括带合法性别的旁白）若与音色性别不完全相等，该项会被丢弃，再走规则回退。

音色的 `age` 始终是数组；一个音色可同时覆盖相邻年龄，例如 `['child', 'teen']`。如果性别池中至少有一个音色包含角色的目标年龄，LLM 的角色采样池只保留包含该年龄的音色；一个也没有时，不清空池，而是保留整个性别池作为回退。合并后的 LLM 结果目前不再次校验年龄，年龄约束主要发生在每角色采样阶段。rule 模式按“与数组中最近年龄的距离”排序，并在距离相同时优先只声明目标年龄的单年龄音色。

### 分类偏好和采样

每个角色最多采样 10 个候选。若合格池不超过 10 个，原样保留全部候选，不按偏好重新排序。超过 10 个时：

- 忽略缺少 `type`，以及权重缺失、为空或转成数字后不大于 0 的偏好；若手工构造的偏好包含无法转成数字的非空权重，采样会抛错，`_safe_llm_assign()` 会放弃本次全部 LLM 分配并让所有角色走 rule 回退；
- 如果存在偏好分类之外的音色，随机保留一个，避免候选池完全被偏好类别占满；
- 其余名额按各分类权重分配，再从相应分类随机采样；
- 仍有空位时从剩余合格音色随机补齐。

各角色池合并后，先放 `category == '有声阅读'` 的音色，再按性别、最年轻的声明年龄和 `voice_id` 排序，序号才写入 LLM prompt。随机采样意味着大目录中的具体候选可在不同运行间变化。

## 旁白处理

`_is_narrator()` 只检查角色 `id` 和 `name` 是否包含旁白关键词，不检查台词类型。识别出的旁白先匹配，以便优先占用合适音色。

旁白的 `gender` 和 `age` 分别校验、分别保留。当前行为由目标性别决定：

- 旁白有合法 `gender`：候选池按该性别约束，LLM 结果也校验该性别；规则回退使用普通角色排序。合法 `age` 若存在会同时参与候选筛选和年龄排序；
- 旁白缺少合法 `gender`：不做性别筛选，LLM prompt 明示“旁白、无性别限制、优先有声阅读类”，rule 排序也优先 `有声阅读`。若它仍有合法 `age`，候选池和 rule 会继续用该年龄收窄；
- 旧剧本同时缺少两项时，目标性别和年龄均为 `None`，才是完全不受性别/年龄限制的兼容路径。

因此“旁白无性别限制”只适用于缺少合法旁白性别的兼容路径。`有声阅读` 是软排序信号，不是独立 voice type，也不是绝对要求。

## 三类角色的候选池示例

假设启用的 catalog 是内置 mock 的四个音色：

| 音色 | 性别 | 年龄数组 | 分类 |
| --- | --- | --- | --- |
| `narrator_01` 少儿故事 | female | `[young_adult]` | 有声阅读 |
| `female_01` 温柔妈妈 | female | `[middle_aged]` | 通用场景 |
| `child_01` 稚嫩童声 | male | `[child, teen]` | 角色扮演 |
| `male_01` 青年男声 | male | `[young_adult]` | 通用场景 |

剧本角色如下：

| 角色 | 剧本元数据 | 每角色采样结果 | 原因 |
| --- | --- | --- | --- |
| `narrator` 旁白 | `gender=null`, `age=null` | 四个音色 | 兼容旁白不限制性别/年龄；后续偏好有声阅读 |
| 小明 | `male`, `child` | 仅 `child_01` | 男声池中存在包含 `child` 的年龄数组，年龄池收窄 |
| 熊妈妈 | `female`, `middle_aged` | 仅 `female_01` | 女声池中存在精确覆盖 `middle_aged` 的音色 |

三个角色池按 `voice_id` 合并后，prompt 的稳定顺序是 `narrator_01`、`female_01`、`child_01`、`male_01`。LLM 看到的是这份全局序号表和每个角色的需求；有效分配后尽量不重复。若 LLM 漏掉熊妈妈，规则回退会在尚未使用的女声里按年龄距离选音色。

## LLM、rule 与回退

`mode=rule` 完全不调用 LLM，也不读取角色的 `voice_preferences`。具有目标性别的角色依次按以下键排序：最近年龄、是否为单年龄精确项、是否为 `有声阅读`（此类角色最后才用）、最年轻声明年龄、`voice_id`。缺少目标性别的兼容旁白则优先 `有声阅读`。在排序结果中先选未使用的 `voice_id`；如果所有可选音色都已使用，复用排名最高者。

`mode=llm` 且传入 LLM 时只调用一次，温度为 `0.3`。返回值应为：

```json
{"assignments":[{"character_id":"kid","voice_index":3}]}
```

以下情况不会中断整个匹配，而是让受影响角色走 rule 回退：调用异常、无法提取 JSON、顶层或 `assignments` 类型错误、未知角色、布尔或非整数下标、越界、重复候选下标、对话角色性别不符。一次有效 LLM 选择会占用对应 `voice_id`，后续回退优先其他音色。`mode=llm` 但没有传入 LLM 时也直接使用规则。

## 日志如何串联

日志默认写到 stderr，并由生成流程写入 `<data_dir>/logs/storyteller.log`。Web 路径的开始、LLM 请求计时、完成事件带 `job_id`、`project_id`、`phase=voices`；CLI 当前没有这些 Web 任务字段。按同一次调用的时间顺序检索：

1. `voice_matching_started`：角色数和模式；
2. `voice_matching_character_candidates`：每个角色的性别、年龄，以及候选的 provider、voice id、语言、名称、性别、年龄、分类和描述；仅 LLM 模式产生；
3. `voice_matching_prompt`：发送给模型的完整 system/user prompt；
4. `llm_request_started`、`llm_request_completed` 或 `llm_request_failed`：请求耗时和错误；
5. `voice_matching_llm_response`：成功调用后的原始模型文本；
6. `voice_matching_completed`：总角色数、模式和总耗时。

候选日志和 LLM response 行当前不重复写入 `job_id`/`project_id`，也没有逐角色“最终分配”事件。排障时先用带上下文的 start/prompt/completed 缩小时间窗口，再按相邻日志检查候选与 response；最终采用的 `voice_config` 以保存后的项目剧本为准。完整 prompt 和模型结果可能含故事角色描述，不应公开粘贴未脱敏日志。

## 相关代码

- `src/storyteller/core/story_generator.py`：生成并规范化角色元数据和偏好；
- `src/storyteller/core/voice_matcher.py`：候选池、LLM 校验、规则回退和日志；
- `src/storyteller/providers/registry.py`：provider 聚合、override 和禁用过滤；
- `src/storyteller/core/voice_overrides.py`：年龄数组和启用状态持久化。
