# 移除 voice_type，音色统一为 gender + age 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除 `VoiceConfig.voice_type` 这个把「性别/儿童/旁白」混在一起的字段，改为正交的 `gender` + `age` 两个维度，并让旁白角色对「有声阅读」类音色只做软偏好而非硬隔离。

**Architecture:** 音色的身份属性变为 `gender`（male/female/None）+ `age`（child/teen/young_adult/middle_aged/senior）；「适合旁白」不入库，由 `category == "有声阅读"` 通过 `is_narration_voice()` 现算。对话角色匹配仍做性别硬约束 + 年龄软约束；旁白角色无性别约束，候选池为全库、有声阅读类排前。`list-voices` 改为表格（名称/音色ID/性别/年龄段/场景）+ 表下特质描述，并显示 provider 元信息。

**Tech Stack:** Python ≥3.8、dataclasses、Click、pytest、火山 seed-tts 2.0。无新依赖。

**Spec:** 本计划源自 brainstorming 对话结论（软偏好方案），无独立 spec 文件；设计要点见上。

## Global Constraints

- 运行 Python 一律用仓库虚拟环境：`.venv/bin/python`、`.venv/bin/pytest`、`.venv/bin/storyteller`。
- 不安装新依赖（numpy 等不装）；表格用标准库手写，不引 tabulate。
- `.env` / 真实密钥禁止提交；本重构全部走 mock，不触发真实 LLM/TTS。
- 向后兼容：反序列化旧 `project.json` 时忽略其中遗留的 `voice_type`，`gender` 缺失则为 `None`，旧项目 `continue` 不报错。
- 提交粒度：每个 Task 末尾一次 commit；仅在 Task 内明确要求时提交。
- 文案：CLI 与注释用中文；代码标识符用英文。

**关键映射（贯穿全计划）：**

| 旧 voice_type | 新表示 |
|---|---|
| `male` | `gender="male"` |
| `female` | `gender="female"` |
| `child` | `age="child"`（gender 仍为 male/female） |
| `narrator` | 删除；改用 `is_narration_voice(voice)`（`category=="有声阅读"`） |

年龄段中文标签沿用 `_AGE_LABELS`；性别中文标签新增 `_GENDER_LABELS = {"male":"男","female":"女"}`；`gender is None` 显示为「中性」。

---

## File Structure

- `src/storyteller/core/models.py` — `VoiceConfig` 删 `voice_type`、新增 `gender`。
- `src/storyteller/core/project.py` — 音色序列化同步（删 voice_type、加 gender、容忍旧数据）。
- `src/storyteller/core/voice_matcher.py` — 匹配逻辑重写：gender+age、旁白软偏好、LLM prompt 调整、新增 `is_narration_voice` / `_infer_gender`。
- `src/storyteller/core/pipeline.py` — `_find_narrator_voice` 兜底改用 `is_narration_voice`。
- `src/storyteller/providers/volcengine/tts.py` — `list_voices` 去 voice_type 用 gender；新增 display 元信息。
- `src/storyteller/providers/mock/tts.py` — MOCK_VOICES 去 voice_type、补 gender；display 元信息。
- `src/storyteller/providers/openai_compatible/tts.py` — 内建音色表改为 (id, gender)，中性音色 gender=None；display 元信息。
- `scripts/build_voice_catalog.py` — 去 voice_type 推导与排序，记录只保留 gender/age/category。
- `src/storyteller/providers/volcengine/voices.json` — 由脚本重新生成。
- `src/storyteller/cli/main.py` — `list-voices` 表格/JSON 重写 + provider 头。
- 测试：`tests/unit/test_models.py`、`test_voice_catalog.py`、`test_voice_matcher.py`、`test_registry.py`、`test_openai_compatible_tts.py`、`tests/integration/test_volcengine_tts.py`、`tests/e2e/test_pipeline.py`、`tests/e2e/test_cli.py`。
- `README.md` — list-voices、音色匹配章节同步。

---

## Task 1: VoiceConfig 模型与序列化改为 gender + age

**Files:**
- Modify: `src/storyteller/core/models.py:62-75`
- Modify: `src/storyteller/core/project.py:125-160`
- Test: `tests/unit/test_models.py`

**Interfaces:**
- Produces: `VoiceConfig(provider, voice_id, *, gender: Optional[str]=None, age=None, category=None, name=None, description=None, language="zh-CN", style=None, speed=1.0, pitch=1.0, volume=1.0)` —— 不再有 `voice_type` 参数或属性。

- [ ] **Step 1: 改失败测试 `tests/unit/test_models.py`**

把 `test_voice_config_creation` 与 `test_character_with_voice` 里的 `voice_type=` 改为 `gender=`，并新增一条中性音色断言：

```python
# ========== VoiceConfig ==========
def test_voice_config_creation():
    vc = VoiceConfig(
        provider="volcengine",
        voice_id="test_voice",
        gender="female",
        language="zh-CN",
    )
    assert vc.provider == "volcengine"
    assert vc.voice_id == "test_voice"
    assert vc.gender == "female"
    assert vc.speed == 1.0
    assert vc.pitch == 1.0
    assert vc.volume == 1.0
    assert vc.style is None


def test_voice_config_neutral_gender_defaults_none():
    vc = VoiceConfig(provider="p", voice_id="alloy")
    assert vc.gender is None
    assert not hasattr(vc, "voice_type")
```

`test_character_with_voice` 中把 `voice_type="male"` 改为 `gender="male"`。

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/pytest tests/unit/test_models.py -q`
Expected: FAIL（`VoiceConfig` 仍有 `voice_type`、无 `gender`）。

- [ ] **Step 3: 修改 `models.py`**

把 `VoiceConfig` 字段块改为：

```python
@dataclass
class VoiceConfig:
    provider: str
    voice_id: str
    language: str = "zh-CN"
    style: Optional[str] = None
    speed: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0
    # Identity hints used by semantic (LLM) voice matching.
    # gender is male/female, or None for gender-neutral voices.
    name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
```

（删除 `voice_type: Literal[...]` 那一行；确认文件顶部 `Literal` 若不再被本文件使用可保留 import，不强行清理。）

- [ ] **Step 4: 修改 `project.py` 序列化**

`_voice_to_dict` 中删除 `"voice_type": vc.voice_type,`、加入 `"gender": vc.gender,`；`_voice_from_dict` 删除 `voice_type=data["voice_type"],`、改为 `gender=data.get("gender"),`（用 `.get` 容忍旧数据）。最终两块为：

```python
def _voice_to_dict(vc):
    if vc is None:
        return None
    return {
        "provider": vc.provider,
        "voice_id": vc.voice_id,
        "language": vc.language,
        "style": vc.style,
        "speed": vc.speed,
        "pitch": vc.pitch,
        "volume": vc.volume,
        "name": vc.name,
        "gender": vc.gender,
        "age": vc.age,
        "category": vc.category,
        "description": vc.description,
    }


def _voice_from_dict(data):
    if not data:
        return None
    return VoiceConfig(
        provider=data["provider"],
        voice_id=data["voice_id"],
        language=data.get("language", "zh-CN"),
        style=data.get("style"),
        speed=data.get("speed", 1.0),
        pitch=data.get("pitch", 1.0),
        volume=data.get("volume", 1.0),
        name=data.get("name"),
        gender=data.get("gender"),
        age=data.get("age"),
        category=data.get("category"),
        description=data.get("description"),
    )
```

注意：`_voice_from_dict` 不再读取 `data["voice_type"]`，因此旧 JSON 中遗留的该键被自然忽略。

- [ ] **Step 5: 跑 models 测试并补一条旧数据兼容测试**

在 `tests/unit/test_models.py` 末尾追加（验证旧 project.json 可加载）：

```python
def test_voice_from_dict_ignores_legacy_voice_type():
    from storyteller.core.project import _voice_from_dict

    legacy = {
        "provider": "volcengine",
        "voice_id": "old_voice",
        "voice_type": "narrator",  # legacy key, must be ignored
        "name": "旧旁白",
    }
    vc = _voice_from_dict(legacy)
    assert vc.voice_id == "old_voice"
    assert vc.gender is None
    assert not hasattr(vc, "voice_type")
```

Run: `.venv/bin/pytest tests/unit/test_models.py -q`
Expected: PASS（全库此刻仍可能有其他文件引用 voice_type 而失败，本 Task 只需 test_models 绿；不跑全量）。

- [ ] **Step 6: Commit**

```bash
git add src/storyteller/core/models.py src/storyteller/core/project.py tests/unit/test_models.py
git commit -m "refactor: replace VoiceConfig.voice_type with gender field"
```

---

## Task 2: 重建音色目录脚本与 voices.json（去 voice_type）

**Files:**
- Modify: `scripts/build_voice_catalog.py`
- Regenerate: `src/storyteller/providers/volcengine/voices.json`
- Test: `tests/unit/test_voice_catalog.py`

**Interfaces:**
- Produces: voices.json 每条记录含 `voice_id, name, gender(male/female), age, category, description, tags, language, bilingual, resource_id`，**不再含 voice_type**。

- [ ] **Step 1: 改失败测试 `tests/unit/test_voice_catalog.py`**

把顶部常量与断言更新为：

```python
import pytest

from storyteller.providers.volcengine.tts import load_voice_catalog

VALID_GENDERS = {"male", "female"}
VALID_AGES = {"child", "teen", "young_adult", "middle_aged", "senior"}
VALID_RESOURCES = {"seed-tts-2.0"}
NARRATION_CATEGORY = "有声阅读"


@pytest.fixture(autouse=True)
def _clear_cache():
    load_voice_catalog.cache_clear()
    yield
    load_voice_catalog.cache_clear()


def test_catalog_loads_and_is_nonempty():
    assert len(load_voice_catalog()) > 200


def test_catalog_records_have_required_fields():
    for v in load_voice_catalog():
        assert v["voice_id"]
        assert v["name"]
        assert "voice_type" not in v
        assert v["gender"] in VALID_GENDERS
        assert v["age"] in VALID_AGES
        assert v["language"] == "zh-CN"
        assert v["resource_id"] in VALID_RESOURCES
        assert isinstance(v["bilingual"], bool)
        assert "description" in v and isinstance(v["tags"], list)


def test_catalog_voice_ids_unique():
    voices = load_voice_catalog()
    ids = [v["voice_id"] for v in voices]
    assert len(ids) == len(set(ids))


def test_catalog_excludes_service_and_accent_voices():
    for v in load_voice_catalog():
        assert v["category"] not in ("客服场景", "陪聊", "直播")
        assert "口音" not in v["category"]


def test_catalog_has_narration_and_child_voices():
    voices = load_voice_catalog()
    assert any(v["category"] == NARRATION_CATEGORY for v in voices)
    children = [v for v in voices if v["age"] == "child"]
    assert len(children) >= 5


def test_catalog_narration_voices_sort_first():
    voices = load_voice_catalog()
    first_non_narration = next(
        i for i, v in enumerate(voices) if v["category"] != NARRATION_CATEGORY
    )
    assert all(
        v["category"] == NARRATION_CATEGORY for v in voices[:first_non_narration]
    )


def test_catalog_is_2_0_only_and_has_bilingual():
    voices = load_voice_catalog()
    assert {v["resource_id"] for v in voices} == VALID_RESOURCES
    assert any(v["bilingual"] for v in voices)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/unit/test_voice_catalog.py -q`
Expected: FAIL（现有 voices.json 仍含 voice_type）。

- [ ] **Step 3: 改 `scripts/build_voice_catalog.py`**

删除 `_TYPE_ORDER`、`_voice_type()`、`NARRATOR_CATEGORIES` 中仅供 voice_type 用的引用；保留 `_primary_category`（仍负责筛选与 category 取值）。具体改动：

1. 删除常量行 `_TYPE_ORDER = {...}`。
2. 删除整个函数：

```python
def _voice_type(age, gender, primary):
    if age == "child":
        return "child"
    if primary in NARRATOR_CATEGORIES:
        return "narrator"
    return gender
```

   保留 `NARRATOR_CATEGORIES = {"有声阅读"}`（排序还要用）。
3. 记录 dict 中删除 `"voice_type": _voice_type(age, gender, primary),` 这一行（gender/age/category 保留）。
4. 排序块替换为：有声阅读类在前（少儿故事仍最前）→ 性别 → 年龄 → 名称：

```python
_GENDER_ORDER = {"female": 0, "male": 1}
_AGE_ORDER = {"child": 0, "teen": 1, "young_adult": 2,
              "middle_aged": 3, "senior": 4}


def _sort_key(v):
    if "少儿故事" in v["name"]:
        narration_rank = 0
    elif v["category"] in NARRATOR_CATEGORIES:
        narration_rank = 1
    else:
        narration_rank = 2
    return (
        narration_rank,
        _GENDER_ORDER.get(v["gender"], 9),
        _AGE_ORDER.get(v["age"], 9),
        v["name"],
    )
```

   并把 main() 里的 `voices.sort(key=lambda v: (...))` 整段换成 `voices.sort(key=_sort_key)`。
5. main() 末尾统计从 by voice_type 改为 by gender：

```python
    genders = {}
    for v in voices:
        genders[v["gender"]] = genders.get(v["gender"], 0) + 1
    print("Wrote {} voices to {}".format(len(voices), OUT))
    print("By gender:", genders)
    print("By resource:", resources)
    print("Bilingual:", sum(1 for v in voices if v["bilingual"]))
    print("Skipped:", skipped)
```

（`resources` 统计保持原样。）

- [ ] **Step 4: 重新生成 voices.json**

Run: `.venv/bin/python scripts/build_voice_catalog.py`
Expected: 打印 `Wrote 249 voices ...`（数量可能随原始数据略变，以脚本输出为准），`By gender: {'female': ..., 'male': ...}`。

- [ ] **Step 5: 校验生成结果并跑测试**

Run:
```bash
.venv/bin/python -c "import json; d=json.load(open('src/storyteller/providers/volcengine/voices.json')); v=d['voices'][0]; assert 'voice_type' not in v; print('keys:', sorted(v.keys())); print('first:', v['name'], v['gender'], v['age'], v['category'])"
.venv/bin/pytest tests/unit/test_voice_catalog.py -q
```
Expected: 打印的 keys 不含 voice_type；首条为有声阅读类；测试 PASS。

- [ ] **Step 6: Commit**

```bash
git add scripts/build_voice_catalog.py src/storyteller/providers/volcengine/voices.json tests/unit/test_voice_catalog.py
git commit -m "refactor: drop voice_type from voice catalog, keep gender/age/category"
```

---

## Task 3: 三个 TTS provider 适配 gender + display 元信息

**Files:**
- Modify: `src/storyteller/providers/volcengine/tts.py:64-77`
- Modify: `src/storyteller/providers/mock/tts.py`
- Modify: `src/storyteller/providers/openai_compatible/tts.py:13-67`

**Interfaces:**
- Produces: 三个 provider 的 `list_voices()` 返回的 `VoiceConfig` 均带 `gender`、不带 voice_type；实例带 `display_name`（str）与 `display_description`（str）属性，供 CLI 读取。

- [ ] **Step 1: 写失败测试（openai 中性性别）**

在 `tests/unit/test_openai_compatible_tts.py` 的 `test_openai_tts_lists_builtin_voices` 内追加断言：

```python
def test_openai_tts_lists_builtin_voices():
    tts = _tts()
    voices = tts.list_voices()
    by_id = {v.voice_id: v for v in voices}
    assert "alloy" in by_id
    assert "nova" in by_id
    assert "shimmer" in by_id
    assert by_id["alloy"].gender is None
    assert by_id["nova"].gender == "female"
    assert by_id["onyx"].gender == "male"
    assert all(not hasattr(v, "voice_type") for v in voices)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/unit/test_openai_compatible_tts.py -q`
Expected: FAIL（构造 VoiceConfig 仍传 voice_type，Task 1 已删该字段 → TypeError）。

- [ ] **Step 3: 改 openai_compatible/tts.py**

内建表改为 `(voice_id, gender)`，并加 display 属性：

```python
_BUILTIN_VOICES = [
    ("alloy", None),
    ("echo", None),
    ("fable", None),
    ("onyx", "male"),
    ("nova", "female"),
    ("shimmer", "female"),
    ("coral", "female"),
]
```

`list_voices` 改为：

```python
    def list_voices(self, **kwargs):
        return [
            VoiceConfig(
                provider=self.provider_name,
                voice_id=voice_id,
                gender=gender,
                language="zh-CN",
            )
            for voice_id, gender in _BUILTIN_VOICES
        ]
```

在类中加两个属性（紧邻已有 `name` property）：

```python
    @property
    def display_name(self):
        return self.provider_name

    @property
    def display_description(self):
        return "OpenAI 兼容 TTS 服务（{}）".format(self.model)
```

- [ ] **Step 4: 改 mock/tts.py**

把 MOCK_VOICES 四个音色的 `voice_type=` 行替换为 `gender=`（值：narrator_01 → `gender="female"`；male_01 → `"male"`；female_01 → `"female"`；child_01 → `"male"`，child_01 保留 `age="child"`）。在 `MockTTSProvider` 类中加：

```python
    @property
    def display_name(self):
        return "Mock（测试）"

    @property
    def display_description(self):
        return "测试用桩 provider，合成结果为静音音频"
```

- [ ] **Step 5: 改 volcengine/tts.py**

`list_voices` 中删除 `voice_type=record["voice_type"],`、保留 `gender=record.get("gender"),`（该行在之前半成品里已存在，确认无重复）。在类中 `name` property 旁加：

```python
    @property
    def display_name(self):
        return "火山引擎"

    @property
    def display_description(self):
        return "seed-tts 2.0 语音合成（火山方舟）"
```

（CLI 头部会统一追加「（N 个音色）」，故描述里不再写数量，避免重复。）

同时更新 `load_voice_catalog` 的 docstring 字段清单（约 237-239 行）：把 `voice_type` 从 "voice_id, name, gender, age, voice_type, category, ..." 中去掉。

- [ ] **Step 6: 更新火山集成测试里的构造参数**

`tests/integration/test_volcengine_tts.py` 中所有 `VoiceConfig(... voice_type="female" ...)`（约 176/195/208/222/246 行）改为 `gender="female"`；约 264 行 `voice_type=record["voice_type"]` 改为 `gender=record["gender"]`。

Run:
```bash
sed -i '' 's/voice_type="female"/gender="female"/g; s/voice_type=record\["voice_type"\]/gender=record["gender"]/g' tests/integration/test_volcengine_tts.py
```
再用 grep 确认无遗漏：`grep -n voice_type tests/integration/test_volcengine_tts.py`（应无输出）。

- [ ] **Step 7: 跑相关测试**

Run:
```bash
.venv/bin/pytest tests/unit/test_openai_compatible_tts.py tests/unit/test_mock_providers.py tests/integration/test_volcengine_tts.py -q
```
Expected: PASS。

- [ ] **Step 8: Commit**

```bash
git add src/storyteller/providers/volcengine/tts.py src/storyteller/providers/mock/tts.py src/storyteller/providers/openai_compatible/tts.py tests/unit/test_openai_compatible_tts.py tests/unit/test_mock_providers.py tests/integration/test_volcengine_tts.py
git commit -m "refactor: adapt TTS providers to gender field, add display metadata"
```

---

## Task 4: 音色匹配逻辑重写（gender+age，旁白软偏好）

**Files:**
- Modify: `src/storyteller/core/voice_matcher.py`
- Test: `tests/unit/test_voice_matcher.py`

**Interfaces:**
- Produces:
  - `is_narration_voice(voice) -> bool`（模块级函数，pipeline 与 CLI 也会 import）。
  - `VoiceMatcher.match_voices(...)` 行为不变（入参/返回不变），内部按 gender+age 匹配。
  - 规则路径对对话角色：性别硬约束（同性别池为空时退到 gender=None 的中性音色，再退全库），年龄按距离排序，有声阅读类排最后；旁白角色：全库、有声阅读类排最前、无性别约束。

- [ ] **Step 1: 先重写测试 `tests/unit/test_voice_matcher.py`**

整体替换断言口径：把对 `voice_config.voice_type` 的断言换成对 `gender` / `age` / `category` 的断言。关键改动逐条：

- 顶部 import 增加 `from storyteller.core.voice_matcher import VoiceMatcher, _infer_age, _infer_gender, is_narration_voice`（`_infer_voice_type` 已删除）。
- `test_match_voices_assigns_narrator_voice`：

```python
def test_match_voices_assigns_narrator_voice():
    matcher = _make_matcher()
    narrator = Character(id="narrator", name="旁白", description="故事旁白")
    script = _make_script_with_characters(narrator)
    matcher.match_voices(script)
    assert narrator.voice_config is not None
    assert is_narration_voice(narrator.voice_config)
    assert narrator.voice_config.provider == "mock"
```

- 男性/女性/亲属称谓/数字年龄各例：把 `voice_type == "male"` 换成 `gender == "male"`、`"female"` 换 `gender == "female"`、儿童两例（72、84 行 kid、94 行 kid、223 行 boy）换成 `age == "child"`。
- `test_adult_described_with_child_word...`：`granny` 断言 `gender == "female"`、`kid` 断言 `age == "child"`。
- 96 行 teen：`assert teen.voice_config.gender == "male"`。
- `test_match_voices_uses_narrator_only_as_last_resort` 改写为「普通女声优先于有声阅读女声」：

```python
def test_match_voices_dialogue_prefers_character_female_before_narration():
    matcher = _make_matcher()
    first = Character(id="g0", name="女0", description="女孩")
    script = _make_script_with_characters(first)
    matcher.match_voices(script)
    # female_01 is a normal 通用场景 female voice; narrator_01 is the
    # 有声阅读 female voice and must not be grabbed first for dialogue.
    assert first.voice_config.voice_id == "female_01"
```

- `test_match_voices_respects_allowed_voice_ids`：允许集 `{"male_01"}`，旁白无性别约束，断言 `voice_id == "male_01"`（保持不变，voice_id 断言即可）。
- LLM 两调用例 `test_llm_classify_then_pick_assigns_voices`：候选新顺序（见 Step 3）为 `[narrator_01(有声阅读), female_01, child_01, male_01]`，narrator 选 index1、mom 选 index2 的 JSON 仍成立；保留对 `narrator_01` / `female_01` 的 voice_id 断言与 `mom.voice_config.description` 断言。
- `test_llm_classifies_boy_as_child_and_picks_child_voice`：单个男孩角色时候选顺序里非旁白按性别分组，male 池内 child 在前；assign index 1 应解析到 `child_01`。把断言改为 `boy.voice_config.voice_id == "child_01"` 与 `boy.voice_config.age == "child"`（去掉 voice_type 断言）。若按 Step 3 的全局排序 index1 不是 child，则在该测试里把 `voice_index` 写成 child_01 在候选列表中的实际序号（实现后运行确定，预期为 3）——以「voice_id == child_01」为最终断言，序号与实现保持一致。
- `_MultiFemaleTTS` 内两个 VoiceConfig 把 `voice_type="female"` 改为 `gender="female"`。
- 其余 fallback 用例（239/249/259/274/324 行）的 `voice_type == "female"` 全部改 `gender == "female"`。
- 新增性别硬约束测试：

```python
def test_dialogue_never_gets_opposite_gender():
    matcher = _make_matcher()
    boy = Character(id="boy", name="阿强", description="一个成年男人")
    script = _make_script_with_characters(boy)
    matcher.match_voices(script)
    assert boy.voice_config.gender == "male"
```

- 新增 `_infer_gender` 小测试：

```python
@pytest.mark.parametrize("desc,expected", [
    ("温柔的女孩", "female"),
    ("成年男子，勇敢", "male"),
    ("企鹅妈妈，温柔", "female"),
    ("一只小动物", "male"),  # default
])
def test_infer_gender(desc, expected):
    assert _infer_gender(desc) == expected
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/unit/test_voice_matcher.py -q`
Expected: FAIL（import `_infer_voice_type` 不存在、voice_type 属性缺失）。

- [ ] **Step 3: 重写 voice_matcher.py 相关部分**

保留：`_NARRATOR_KEYWORDS`、所有年龄/性别词表、`_AGE_LABELS`、`_infer_age`、`_is_narrator`、`_classify_characters`（不改）。

替换/新增以下内容。

常量与 prompt（替换 `_TYPE_LABELS`、`_GROUP_ORDER`、两个 system prompt 中涉及分组的措辞）：

```python
_GENDER_LABELS = {"male": "男", "female": "女"}
_AGE_RANK = {"child": 0, "teen": 1, "young_adult": 2,
             "middle_aged": 3, "senior": 4}
_GENDER_ORDER = {"female": 0, "male": 1}
NARRATION_CATEGORIES = {"有声阅读"}


def is_narration_voice(voice):
    """True for reading/narration-suited voices (soft signal, not a type)."""
    return voice.category in NARRATION_CATEGORIES
```

`_LLM_SYSTEM_PROMPT` 替换为：

```python
_LLM_SYSTEM_PROMPT = (
    "你是一位经验丰富的广播剧配音导演。请根据每个角色的设定，"
    "从给定的候选音色中挑选最贴切的一个。\n"
    "规则：\n"
    "1. 每个角色必须且只能选择一个候选音色，用候选前面的序号表示。\n"
    "2. 严格遵守性别：女性角色不可选男声，男性角色不可选女声；"
    "标注为旁白的角色无性别限制。\n"
    "3. 旁白角色优先选择「有声阅读」类、语气平稳连贯的音色；"
    "儿童故事也可以根据气质选择温暖的年轻音色或儿童音色。\n"
    "4. 年龄和气质要贴合：例如慈祥的老婆婆要避免年轻御姐音，"
    "优先中年/老年、语气温和缓慢的音色；孩子选儿童年龄段音色。\n"
    "5. 结合音色的名称、分类和描述里的语气、风格来判断，不要只看性别。\n"
    "6. 不同角色尽量选择不同的音色，序号不可重复。\n"
    "7. 只输出 JSON，不要任何额外文字，格式：\n"
    '{"assignments":[{"character_id":"角色id","voice_index":序号}]}'
)
```

删除 `_infer_voice_type`，新增：

```python
def _infer_gender(description):
    """Guess male/female from explicit words, kinship titles, pronouns.

    Defaults to male. Childhood no longer collapses gender: a child still
    has its own gender (age is tracked separately).
    """
    desc = description or ""
    if any(word in desc for word in _FEMALE_WORDS):
        return "female"
    if any(word in desc for word in _MALE_WORDS):
        return "male"
    return "male"
```

删除 `_type_preference`、`_flatten`、`_any_available`，新增打分/选池函数：

```python
def _age_distance(a, b):
    return abs(_AGE_RANK.get(a, 2) - _AGE_RANK.get(b, 2))


def _gender_pool(voices, gender):
    """Hard gender preference, falling back to neutral then any voice."""
    exact = [v for v in voices if v.gender == gender]
    if exact:
        return exact
    neutral = [v for v in voices if not v.gender]
    if neutral:
        return neutral
    return list(voices)


def _voice_sort_key(voice, age, narrator):
    if narrator:
        # Narration-suited voices first; ties by age then stable id.
        return (
            0 if is_narration_voice(voice) else 1,
            _AGE_RANK.get(voice.age, 9),
            voice.voice_id,
        )
    # Dialogue: reading voices are the last resort; otherwise nearest age.
    return (
        1 if is_narration_voice(voice) else 0,
        _age_distance(voice.age, age),
        _AGE_RANK.get(voice.age, 9),
        voice.voice_id,
    )
```

`match_voices` 主体替换分组/wanted 段（193-233 行）为：

```python
        narrators = [c for c in script.characters if _is_narrator(c)]
        others = [c for c in script.characters if not _is_narrator(c)]
        ordered = narrators + others

        # wanted[char_id] = (gender_or_None, age_or_None); narrator is (None, None).
        wanted = {c.id: (None, None) for c in narrators}
        classified = {}
        if self.mode == "llm" and self.llm is not None and others:
            classified = self._classify_characters(others)
        for character in others:
            text = "{} {}".format(character.name, character.description)
            if character.id in classified:
                gender, age = classified[character.id]
            else:
                gender = _infer_gender(text)
                age = _infer_age(text)
            wanted[character.id] = (gender, age)

        used_ids = set()
        llm_picks = {}
        if self.mode == "llm" and self.llm is not None:
            llm_picks = self._safe_llm_assign(ordered, wanted, voices)
            for voice in llm_picks.values():
                used_ids.add(voice.voice_id)

        for character in ordered:
            if character.id in llm_picks:
                character.voice_config = llm_picks[character.id]
                continue
            gender, age = wanted[character.id]
            chosen = self._rule_pick(
                voices, used_ids, default_provider,
                gender=gender, age=age, narrator=gender is None,
            )
            character.voice_config = chosen
            used_ids.add(chosen.voice_id)

        return script
```

`_safe_llm_assign(self, ordered, wanted, voices)`：把签名里的 `by_type` 换成 `voices`；调用 `_request_llm(ordered, wanted, voices)`；硬校验段（324-327 行）改为只校验对话角色性别：

```python
            want_gender = wanted[char_id][0]
            voice = candidates[index - 1]
            # Hard constraint for dialogue only: gender must agree.
            # Narrators (want_gender is None) have no gender restriction.
            if want_gender is not None and voice.gender != want_gender:
                continue
```

`_request_llm(self, ordered, wanted, voices)` 整段替换（单一候选池，有声阅读在前）：

```python
    def _request_llm(self, ordered, wanted, voices):
        candidates = sorted(
            voices,
            key=lambda v: (
                0 if is_narration_voice(v) else 1,
                _GENDER_ORDER.get(v.gender, 9),
                _AGE_RANK.get(v.age, 9),
                v.voice_id,
            ),
        )
        lines = []
        for voice in candidates:
            index = len(lines) + 1
            gender_label = _GENDER_LABELS.get(voice.gender, "中性")
            lines.append(
                "[{}] {} | {} | {} | {} | {}".format(
                    index,
                    voice.name or voice.voice_id,
                    gender_label,
                    _AGE_LABELS.get(voice.age, voice.age or "-"),
                    voice.category or "-",
                    voice.description or "-",
                )
            )

        char_lines = []
        for character in ordered:
            gender, age = wanted[character.id]
            if gender is None:
                need = "旁白（无性别限制，优先有声阅读类）"
            else:
                need = "{}声，年龄={}".format(
                    _GENDER_LABELS.get(gender, gender),
                    _AGE_LABELS.get(age, age or "-"),
                )
            char_lines.append(
                "- character_id={} 「{}」：{} ｜ {}".format(
                    character.id,
                    character.name,
                    character.description or "-",
                    need,
                )
            )

        user_content = (
            "候选音色列表：\n{}\n\n"
            "待分配角色：\n{}\n\n"
            "请为每个角色选择一个候选序号，按规定只输出 JSON。"
        ).format("\n".join(lines), "\n".join(char_lines))
        messages = [
            {"role": "system", "content": _LLM_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        response = self.llm.chat(messages, temperature=0.0)
        return candidates, response
```

`_rule_pick` 替换为：

```python
    def _rule_pick(self, voices, used_ids, default_provider,
                   *, gender, age, narrator):
        """Deterministic selection used at init and as LLM fallback."""
        pool = list(voices) if narrator else _gender_pool(voices, gender)
        ranked = sorted(pool, key=lambda v: _voice_sort_key(v, age, narrator))
        unused = [v for v in ranked if v.voice_id not in used_ids]
        if default_provider:
            on_default = [v for v in unused if v.provider == default_provider]
            if on_default:
                return on_default[0]
        if unused:
            return unused[0]
        # Every pool voice is already used: reuse the highest-ranked one.
        return ranked[0]
```

同步更新类 docstring（157-163 行），把 "gender/age/narrator type" 改为 "gender/age，旁白对有声阅读类软偏好"。

- [ ] **Step 4: 跑测试，校准 child LLM 用例序号**

Run: `.venv/bin/pytest tests/unit/test_voice_matcher.py -q`
Expected: 绝大多数 PASS。若 `test_llm_classifies_boy_as_child_and_picks_child_voice` 因候选序号失败，打印候选顺序确定 child_01 序号：

```bash
.venv/bin/python -c "
from storyteller.core.config import Config
from storyteller.providers.registry import ProviderRegistry
from storyteller.providers.mock.tts import MockTTSProvider
from storyteller.core.voice_matcher import is_narration_voice
r=ProviderRegistry(Config()); r.register_tts('mock', MockTTSProvider)
vs=r.list_tts_voices(['mock'])
key=lambda v:(0 if is_narration_voice(v) else 1, {'female':0,'male':1}.get(v.gender,9), {'child':0,'teen':1,'young_adult':2,'middle_aged':3,'senior':4}.get(v.age,9), v.voice_id)
for i,v in enumerate(sorted(vs,key=key),1): print(i, v.voice_id, v.gender, v.age, v.category)
"
```
把该测试 assign JSON 的 `voice_index` 改为 child_01 对应的序号（mock 下旁白 narrator_01 居首，非旁白 female_01 其后，male 中 child_01 在 male_01 前，预期为 3）。最终断言以 voice_id 为准。

- [ ] **Step 5: Commit**

```bash
git add src/storyteller/core/voice_matcher.py tests/unit/test_voice_matcher.py
git commit -m "refactor: match voices by gender+age with soft narration preference"
```

---

## Task 5: pipeline 旁白兜底改用 is_narration_voice

**Files:**
- Modify: `src/storyteller/core/pipeline.py:236-252`
- Test: `tests/e2e/test_pipeline.py:158-197`
- Also: `tests/unit/test_registry.py`、`tests/e2e/test_pipeline.py` 中其余 voice_type 引用

**Interfaces:**
- Consumes: Task 4 的 `is_narration_voice(voice)`。

- [ ] **Step 1: 改失败测试**

`tests/e2e/test_pipeline.py` 的 `test_narration_uses_narrator_voice_when_llm_omits_it` 末尾断言改为：

```python
    from storyteller.core.voice_matcher import is_narration_voice

    narration_call = next(c for c in tts.synth_calls if c["text"] == "天亮了。")
    assert is_narration_voice(narration_call["voice_config"])
    dialogue_call = next(c for c in tts.synth_calls if c["text"] == "早安！")
    assert dialogue_call["voice_config"].voice_id != narration_call["voice_config"].voice_id
```

`tests/unit/test_registry.py` 的 `FakeTTS.list_voices` 中 `voice_type="narrator"` 改为 `gender="female", category="有声阅读"`。

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/e2e/test_pipeline.py::test_narration_uses_narrator_voice_when_llm_omits_it tests/unit/test_registry.py -q`
Expected: FAIL（pipeline 仍引用 `.voice_type`）。

- [ ] **Step 3: 改 `pipeline.py` `_find_narrator_voice`**

顶部 import 增加：

```python
from .voice_matcher import is_narration_voice
```

（注意避免循环导入：voice_matcher 只依赖 models/exceptions/story_generator，不 import pipeline，安全。）

方法改为：

```python
    def _find_narrator_voice(self, script, char_voice_map):
        """Find a narrator voice, or fall back to any available voice."""
        narrator_keywords = ("narrator", "旁白", "说书", "叙述")
        for char in script.characters:
            text = "{} {}".format(char.id, char.name).lower()
            if any(kw in text for kw in narrator_keywords):
                voice = char_voice_map.get(char.id)
                if voice:
                    return voice
        # Fallback: prefer a reading/narration-suited voice so narration is
        # not read in the first dialogue character's timbre; then any voice.
        for voice in char_voice_map.values():
            if voice and is_narration_voice(voice):
                return voice
        for voice in char_voice_map.values():
            return voice
        return None
```

- [ ] **Step 4: 全仓搜残留 voice_type（src 与 tests）**

Run: `grep -rn "voice_type" src/ tests/ scripts/ || echo "CLEAN"`
Expected: 除注释/历史外应 `CLEAN`。若有残留（如其它 e2e/unit），逐条把构造参数改 `gender=`、断言改 `.gender`/`.age`/`is_narration_voice`。

- [ ] **Step 5: 跑全量测试**

Run: `.venv/bin/pytest tests/ -q`
Expected: 全绿（数量应仍为 225 左右，新增用例后略多）。

- [ ] **Step 6: Commit**

```bash
git add src/storyteller/core/pipeline.py tests/e2e/test_pipeline.py tests/unit/test_registry.py
git commit -m "refactor: narrator fallback uses narration category, not voice_type"
```

---

## Task 6: list-voices 表格/JSON 重写 + provider 头

**Files:**
- Modify: `src/storyteller/cli/main.py`（list-voices 段，约 238-330 行；Task 前半成品已加过 `--format/--kind`，本任务覆盖之）
- Test: `tests/e2e/test_cli.py`

**Interfaces:**
- Consumes: provider 实例的 `display_name` / `display_description`（Task 3）；`VoiceConfig.gender/age/category/name/description`。

- [ ] **Step 1: 写失败测试**

在 `tests/e2e/test_cli.py` 中把 `test_list_voices_shows_mock` 扩充，并新增 JSON 用例：

```python
def test_list_voices_shows_mock():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["list-voices", "--tts-providers", "mock"],
            env=_MOCK_ENV,
        )
        assert result.exit_code == 0, result.output
        assert "Mock（测试）" in result.output
        assert "narrator_01" in result.output
        assert "男" in result.output and "女" in result.output
        assert "有声阅读" in result.output
        # Table headers present, and the old confusing 类型 column is gone.
        for header in ("名称", "音色ID", "性别", "年龄段", "场景"):
            assert header in result.output
        assert "类型" not in result.output


def test_list_voices_json():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["list-voices", "--tts-providers", "mock", "--format", "json"],
            env=_MOCK_ENV,
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert isinstance(data, list) and data
        row = next(v for v in data if v["voice_id"] == "female_01")
        assert row["gender"] == "female"
        assert row["age"] == "middle_aged"
        assert row["category"] == "通用场景"
        assert all("voice_type" not in v for v in data)
```

（文件顶部加 `import json`。那个 `voice_type_header_absent` 辅助若别扭，可简化为直接 `assert "类型" not in result.output`——表头不再含「类型」二字，描述脚注里也不用该词，采用简化版即可。）

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/e2e/test_cli.py -q`
Expected: FAIL（旧输出无表头/无 provider 头）。

- [ ] **Step 3: 重写 list-voices 命令**

用以下整段替换现有 `list-voices` 命令及其辅助函数（删除半成品里的 `--kind` 选项与 `_print_voice_table`）：

```python
# ========== list-voices ==========
_AGE_CN = {
    "child": "儿童", "teen": "少年", "young_adult": "青年",
    "middle_aged": "中年", "senior": "老年",
}
_GENDER_CN = {"male": "男", "female": "女"}


@cli.command(name="list-voices")
@click.option("--tts-providers", default=None, help="要查询的provider，逗号分隔")
@click.option(
    "--format", "output_format",
    type=click.Choice(["table", "json"]), default="table",
    help="输出格式：table 表格（默认）或 json",
)
def list_voices(tts_providers, output_format):
    """列出所有可用的TTS音色。"""
    pipeline = _build_pipeline()
    providers = None
    if tts_providers:
        providers = [p.strip() for p in tts_providers.split(",") if p.strip()]
    else:
        providers = pipeline.registry.list_tts_names()

    try:
        voices = pipeline.registry.list_tts_voices(providers)
    except Exception as exc:
        raise click.ClickException(str(exc))

    if not voices:
        click.echo("没有可用的音色。请检查配置。")
        return

    if output_format == "json":
        import json as _json
        click.echo(_json.dumps(
            [_voice_row(v) for v in voices], ensure_ascii=False, indent=2
        ))
        return

    by_provider = {}
    for v in voices:
        by_provider.setdefault(v.provider, []).append(v)

    for provider_name in providers:
        pv = by_provider.get(provider_name)
        if not pv:
            continue
        tts = pipeline.registry.get_tts(provider_name)
        header = getattr(tts, "display_name", provider_name)
        desc = getattr(tts, "display_description", "")
        click.echo("【{}】{}（{} 个音色）".format(
            header, "  " + desc if desc else "", len(pv)))
        _print_voice_table(pv)
        footnotes = [v for v in pv if v.description]
        if footnotes:
            click.echo()
            for v in footnotes:
                click.echo("  · {}：{}".format(v.name or v.voice_id, v.description))
        click.echo()


def _voice_row(v):
    return {
        "provider": v.provider,
        "voice_id": v.voice_id,
        "name": v.name,
        "gender": v.gender,
        "age": v.age,
        "category": v.category,
        "description": v.description,
        "language": v.language,
    }


def _print_voice_table(voices):
    headers = ["名称", "音色ID", "性别", "年龄段", "场景"]
    rows = [
        [
            v.name or "-",
            v.voice_id,
            _GENDER_CN.get(v.gender, "中性"),
            _AGE_CN.get(v.age, "-"),
            v.category or "-",
        ]
        for v in voices
    ]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _display_width(cell))

    def border():
        return "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def fmt(cells):
        return "|" + "|".join(
            " {} ".format(cells[i] + " " * (widths[i] - _display_width(cells[i])))
            for i in range(len(cells))
        ) + "|"

    click.echo(border())
    click.echo(fmt(headers))
    click.echo(border())
    for row in rows:
        click.echo(fmt(row))
    click.echo(border())
```

并在文件顶部（import 区）加一个中日韩宽度估算辅助（表格对齐用，中文占两列）：

```python
def _display_width(text):
    """Approx. terminal cell width: CJK chars count as 2 columns."""
    import unicodedata
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
        for ch in str(text)
    )
```

- [ ] **Step 4: 运行 CLI 测试并人工查看输出**

Run: `.venv/bin/pytest tests/e2e/test_cli.py -q`
Expected: PASS。

再人工跑一次：

```bash
STORYTELLER_TTS_PROVIDERS=mock STORYTELLER_TTS_MOCK_TYPE=mock \
STORYTELLER_LLM_PROVIDERS=mock STORYTELLER_LLM_MOCK_TYPE=mock \
STORYTELLER_LLM_DEFAULT_PROVIDER=mock STORYTELLER_TTS_DEFAULT_PROVIDER=mock \
.venv/bin/storyteller list-voices
```
Expected: 显示【Mock（测试）】头、对齐表格（中文不错位）、表下 4 条 `· 名称：描述` 脚注。再追加 `--format json` 确认输出合法 JSON。

- [ ] **Step 5: 跑全量测试**

Run: `.venv/bin/pytest tests/ -q`
Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add src/storyteller/cli/main.py tests/e2e/test_cli.py
git commit -m "feat: readable list-voices table/json with provider info and gender/age"
```

---

## Task 7: README 同步与全量回归

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 list-voices 小节**

把 README 中 `#### storyteller list-voices` 小节替换为：

````markdown
#### `storyteller list-voices` — 列出可用音色

| 参数 | 含义 | 默认值 | 可选值 |
|------|------|--------|--------|
| `--tts-providers` | 限定查询的 provider，逗号分隔 | 全部已配置 provider | provider 名 |
| `--format` | 输出格式 | `table` | `table` / `json` |

按 provider 分组，先显示 provider 名称、说明与音色数，再用表格列出每个音色的**名称、音色 ID、性别、年龄段、场景**；表格下方用 `· 名称：特质` 逐条给出音色描述。

```text
【火山引擎】  seed-tts 2.0 语音合成（火山方舟）（249 个音色）
+----------+------------------------------+------+--------+----------+
| 名称     | 音色ID                       | 性别 | 年龄段 | 场景     |
+----------+------------------------------+------+--------+----------+
| 少儿故事 | zh_female_shaoergushi_...    | 女   | 青年   | 有声阅读 |
| ...      | ...                          | ...  | ...    | ...      |
+----------+------------------------------+------+--------+----------+

· 少儿故事：语调活泼、声线亲切，适配儿童故事的治愈女声
```

`--format json` 输出数组，每条含 `provider/voice_id/name/gender/age/category/description/language`，便于脚本处理。性别只有 `male`/`female`（OpenAI 兼容的中性音色为 `null`）；年龄段为 `child/teen/young_adult/middle_aged/senior`。
````

执行时先用真实 `storyteller list-voices` 输出核对表头与示例一致，再把示例里的表格虚线按真实列宽对齐。

- [ ] **Step 2: 更新「音色匹配」章节**

把 README「## 音色匹配」整节替换为：

```markdown
## 音色匹配

音色只用两个正交维度描述：**性别**（male/female，中性音色为 null）与**年龄段**（child/teen/young_adult/middle_aged/senior），另有来自官方分类的**场景**标签（有声阅读、通用场景、角色扮演等）。系统不再给音色贴「旁白/角色」的固定类型——儿童音色、温暖年轻女声同样可以念旁白。

默认 `llm` 模式分两步：

1. **角色分类（LLM 调用一）**：根据角色名 + 描述判定性别与年龄段。旁白角色按 id/名称确定性识别（旁白/narrator/说书/叙述），不参与分类。
2. **音色精选（LLM 调用二）**：把全部候选音色（有声阅读类排在最前）连同性别/年龄/场景/描述交给模型挑选。对话角色严格遵守性别、年龄与气质贴合；旁白角色无性别限制，优先有声阅读类，也可按故事气质选儿童或温暖音色。

任一步失败或返回非法结果，对应角色回退到确定性规则匹配：对话角色在同性别音色池里按年龄距离挑选（同性别池为空时退到中性音色），有声阅读类作为对话的最后备选；旁白角色在全库中优先有声阅读类。可用 `--voice-matcher rule` 或 `STORYTELLER_VOICE_MATCHER=rule` 完全走规则（不产生额外 LLM 调用）。

内置火山音色库约 249 个（仅 seed-tts-2.0，含中英文混读音色），由 `scripts/build_voice_catalog.py` 从 `data/` 下的官方清单整理生成，打包在 `src/storyteller/providers/volcengine/voices.json`。
```

- [ ] **Step 3: 全量回归 + 语法检查**

Run:
```bash
.venv/bin/python -c "import ast,glob; [ast.parse(open(f).read()) for f in glob.glob('src/**/*.py', recursive=True)]; print('all parse ok')"
.venv/bin/pytest tests/ -q
grep -rn "voice_type" src/ tests/ scripts/ README.md || echo "NO VOICE_TYPE REFERENCES"
```
Expected: 全绿；最后一条打印 `NO VOICE_TYPE REFERENCES`。

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update list-voices and voice matching for gender/age model"
```

---

## Self-Review 备注（执行者完成后核对）

- Task 1→6 的字段名统一为 `gender`，没有任何任务仍引用 `voice_type`。
- `is_narration_voice` 定义在 voice_matcher.py（Task 4），pipeline（Task 5）与 README 均引用它；CLI 不直接调用，仅显示 `category`。
- 候选排序在两处出现（`_request_llm` 全局序、`_rule_pick` 选池序），口径需一致：有声阅读在前（旁白）/在后（对话）。
- mock 音色的固定 voice_id（narrator_01/male_01/female_01/child_01）在多个测试里被硬编码，Task 3 改 mock 时不得改这些 ID。
- 旧项目兼容只靠 `_voice_from_dict` 忽略 voice_type；TTS 合成只用 voice_id/provider/resource_id，不读 voice_type，故老项目可继续 `continue`。
