# Provider 命令行选用与音效 Provider 独立化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 LLM/TTS/音效三类 provider「配置即注册、CLI 可选用」，并把音效升级为与 llm/tts 同构的独立 provider 分组（独立 key、独立 CLI 参数）。

**Architecture:** `Config._load_provider_group` 在显式 `*_PROVIDERS` 名单之外扫描环境变量自动发现 provider；`ProviderRegistry` 增加与 TTS 同构的 sound 段；bootstrap 增加 sound 类型分发；pipeline 的音效 provider 改为从 registry 解析（注入仍最高优先），并在音色匹配前对未知 TTS provider 快速失败；CLI generate/continue/make-sound 与向导接入 `--sound-provider`。

**Tech Stack:** Python ≥3.8、click、pytest（FakeSession/monkeypatch 既有风格），不触真实 API。

**Spec:** `docs/superpowers/specs/2026-09-11-provider-cli-selection-and-sound-providers-design.md` — 执行者须同时读 spec 与本计划；冲突以 spec 为准。

## Global Constraints

- 测试统一用仓库 venv：`.venv/bin/python -m pytest`；全部为本地测试，禁止触真实 API
- 密钥只从环境变量读；禁止把真实 key 写进入库文件；`.env` 已被 gitignore，`.env.example` 只含占位符
- 旧变量 `STORYTELLER_SFX_VOLCENGINE_*` 一律不再读取，**不做向后兼容**
- 音效 key 只从 `STORYTELLER_SOUND_<NAME>_API_KEY` 读取，缺失即报错，**不回退 TTS key**
- 自动发现规则：环境变量中存在任一 `STORYTELLER_<KIND>_<NAME>_{TYPE,API_KEY,MODEL,ENDPOINT,BASE_URL,RESOURCE_ID}` 即注册该 provider；最终名单 = 显式名单（去重）+ 发现项按字母序追加
- TTS 分组扫描跳过 `OPENAI_COMPATIBLE` 前缀（仍由 `_load_openai_compatible_tts` 处理）
- 严格 TDD：每个行为先写失败测试、看它按预期失败，再写最小实现
- provider 注册是懒加载（注册工厂时不构造实例、不触网）
- 测试注入的 `Pipeline(sound_provider=...)` 保持最高优先，现有 `tests/e2e/test_pipeline.py` 音效测试不改
- MockSoundProvider 写的是可闻 440Hz 正弦音（响度闸门要求），mock 音效 provider 不需要 API key

---

### Task 1: Config 自动发现 + sound 分组加载

**Files:**
- Modify: `src/storyteller/core/config.py`（DEFAULTS 34-38、`from_env` 86-89、`_load_sound` 116-139、`_load_provider_group` 141-173）
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Produces: `Config.from_env()` 后 `sound.providers`（list[str]）、`sound.default_provider`（str|None）、`sound.provider_config.<name>`（dict）；llm/tts/sound 三个分组都支持环境变量自动发现，发现项排序规则为「显式名单原序在前，发现项按名字母序追加，大小写不敏感去重」。

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_config.py` 末尾追加：

```python
def test_tts_provider_auto_discovered_without_providers_list(monkeypatch):
    # Configuring per-provider vars is enough to become selectable;
    # no STORYTELLER_TTS_PROVIDERS edit required.
    monkeypatch.setenv("STORYTELLER_TTS_ALIYUN_TYPE", "aliyun")
    monkeypatch.setenv("STORYTELLER_TTS_ALIYUN_API_KEY", "dashscope-key")
    config = Config.from_env()
    assert config.get("tts.providers") == ["aliyun"]
    assert config.get("tts.provider_config.aliyun.type") == "aliyun"
    assert config.get("tts.provider_config.aliyun.api_key") == "dashscope-key"


def test_listed_providers_first_discovered_sorted_and_deduped(monkeypatch):
    monkeypatch.setenv("STORYTELLER_TTS_PROVIDERS", "volcengine")
    monkeypatch.setenv("STORYTELLER_TTS_VOLCENGINE_API_KEY", "vkey")
    monkeypatch.setenv("STORYTELLER_TTS_MOCK_API_KEY", "unused")
    monkeypatch.setenv("STORYTELLER_TTS_ALIYUN_API_KEY", "akey")
    config = Config.from_env()
    assert config.get("tts.providers") == ["volcengine", "aliyun", "mock"]


def test_llm_auto_discovery_parity(monkeypatch):
    monkeypatch.setenv("STORYTELLER_LLM_VOLCENGINE_API_KEY", "llm-key")
    config = Config.from_env()
    assert config.get("llm.providers") == ["volcengine"]
    assert config.get("llm.provider_config.volcengine.api_key") == "llm-key"


def test_sound_group_loads_providers_default_and_config(monkeypatch):
    monkeypatch.setenv("STORYTELLER_SOUND_PROVIDERS", "volcengine")
    monkeypatch.setenv("STORYTELLER_SOUND_DEFAULT_PROVIDER", "volcengine")
    monkeypatch.setenv("STORYTELLER_SOUND_VOLCENGINE_API_KEY", "sound-key")
    monkeypatch.setenv("STORYTELLER_SOUND_VOLCENGINE_MODEL", "seed-audio-1.0")
    config = Config.from_env()
    assert config.get("sound.providers") == ["volcengine"]
    assert config.get("sound.default_provider") == "volcengine"
    assert config.get("sound.provider_config.volcengine.api_key") == "sound-key"
    assert config.get("sound.provider_config.volcengine.model") == "seed-audio-1.0"


def test_sound_reserved_names_are_not_providers(monkeypatch):
    monkeypatch.setenv("STORYTELLER_SOUND_ENABLED", "true")
    monkeypatch.setenv("STORYTELLER_SOUND_DIR", "/tmp/sounds")
    config = Config.from_env()
    assert config.get("sound.providers") == []
    assert config.get("sound.enabled") is True
    assert config.get("sound.dir") == "/tmp/sounds"


def test_legacy_sfx_vars_are_no_longer_read(monkeypatch):
    monkeypatch.setenv("STORYTELLER_SFX_VOLCENGINE_API_KEY", "old-key")
    monkeypatch.setenv("STORYTELLER_SFX_VOLCENGINE_MODEL", "old-model")
    config = Config.from_env()
    assert config.get("sound.providers") == []
    assert config.get("sound.provider_config.volcengine") is None
```

- [ ] **Step 2: 运行确认 RED**

Run: `.venv/bin/python -m pytest tests/unit/test_config.py -q`
Expected: 新增 6 个测试 FAIL（sound.providers 不存在/为旧行为、SFX 旧变量仍被读取等），原有测试仍 PASS。

- [ ] **Step 3: 更新 DEFAULTS 与 from_env**

`src/storyteller/core/config.py` 的 `DEFAULTS` 中 sound 块改为：

```python
        "sound": {
            "enabled": False,
            "dir": None,
            "providers": [],
            "default_provider": None,
            "provider_config": {},
        },
```

`from_env` 中 86-89 行的分组加载改为（顺序：llm、tts、openai 兼容追加、sound 分组、sound 开关/目录）：

```python
        cls._load_provider_group(config, "llm")
        cls._load_provider_group(config, "tts")
        cls._load_openai_compatible_tts(config)
        cls._load_provider_group(config, "sound")
        cls._load_sound(config)
```

- [ ] **Step 4: 重写 _load_sound（删除 SFX 读取）**

把 `_load_sound` 整体替换为：

```python
    @staticmethod
    def _load_sound(config):
        enabled = os.getenv("STORYTELLER_SOUND_ENABLED", "").strip().lower()
        if enabled in ("1", "true", "yes", "on"):
            config.set("sound.enabled", True)
        sound_dir = os.getenv("STORYTELLER_SOUND_DIR")
        if sound_dir:
            config.set("sound.dir", sound_dir)
```

- [ ] **Step 5: 重写 _load_provider_group（自动发现）**

把 `_load_provider_group` 整体替换为：

```python
    # Per-provider config keys shared by the llm/tts/sound groups.
    _PROVIDER_CONFIG_KEYS = (
        "type", "api_key", "model", "endpoint", "base_url", "resource_id",
    )

    @staticmethod
    def _load_provider_group(config, kind):
        """Load one provider group (llm/tts/sound).

        Names in STORYTELLER_<KIND>_PROVIDERS come first (default enablement
        and ordering). Any other name with a per-provider env var is
        auto-discovered and appended in sorted order, so configuring a key
        is enough to make a provider CLI-selectable without editing the
        PROVIDERS list.
        """
        upper = kind.upper()
        group_prefix = "STORYTELLER_{}_".format(upper)

        providers_env = os.getenv(group_prefix + "PROVIDERS", "")
        providers = [p.strip() for p in providers_env.split(",") if p.strip()]

        config.set(
            "{}.default_provider".format(kind),
            os.getenv(group_prefix + "DEFAULT_PROVIDER"),
        )

        # The suffix allowlist alone excludes reserved names (PROVIDERS,
        # DEFAULT_PROVIDER, ENABLED, DIR all lack a recognised suffix).
        discovered = set()
        for env_key in os.environ:
            if not env_key.startswith(group_prefix):
                continue
            rest = env_key[len(group_prefix):]
            if kind == "tts" and rest.startswith("OPENAI_COMPATIBLE"):
                continue
            parts = rest.rsplit("_", 1)
            if len(parts) != 2:
                continue
            name, suffix = parts
            if not name or suffix.lower() not in Config._PROVIDER_CONFIG_KEYS:
                continue
            discovered.add(name.lower())

        seen = {p.lower() for p in providers}
        for name in sorted(discovered):
            if name not in seen:
                providers.append(name)
                seen.add(name)
        config.set("{}.providers".format(kind), providers)

        for provider in providers:
            provider_prefix = "STORYTELLER_{}_{}_".format(
                upper, provider.upper()
            )
            provider_config = {}
            for key in Config._PROVIDER_CONFIG_KEYS:
                value = os.getenv(provider_prefix + key.upper())
                if value:
                    provider_config[key] = value
            if provider_config:
                config.set(
                    "{}.provider_config.{}".format(kind, provider),
                    provider_config,
                )
```

- [ ] **Step 6: 运行确认 GREEN**

Run: `.venv/bin/python -m pytest tests/unit/test_config.py -q`
Expected: 全部 PASS（含既有 9 个 + 新增 6 个）。

- [ ] **Step 7: 提交**

```bash
git add src/storyteller/core/config.py tests/unit/test_config.py
git commit -m "feat: auto-discover configured providers and add sound config group"
```

---

### Task 2: ProviderRegistry 增加 sound 段

**Files:**
- Modify: `src/storyteller/providers/registry.py`
- Test: `tests/unit/test_registry.py`

**Interfaces:**
- Consumes: `SoundEffectProvider`（`storyteller.core.sfx`，抽象方法 `name` 属性与 `generate(...)`）
- Produces: `registry.register_sound(name, factory)`、`get_sound(name)`（懒加载缓存，未知名抛 `ProviderError`）、`set_default_sound(name)`、`get_default_sound()`、`list_sound_names()`。

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_registry.py` 顶部导入区加：

```python
from storyteller.core.sfx import SoundEffectProvider
```

文件末尾追加：

```python
# ========== ProviderRegistry Sound ==========
class FakeSound(SoundEffectProvider):
    @property
    def name(self):
        return "fake-sound"

    def generate(
        self, prompt, output_path, *,
        audio_format="mp3", sample_rate=None, references=None,
    ):
        return output_path, None


def test_registry_register_and_get_sound():
    config = Config()
    registry = ProviderRegistry(config)
    registry.register_sound("fake", FakeSound)
    sound = registry.get_sound("fake")
    assert isinstance(sound, FakeSound)
    assert sound.name == "fake-sound"


def test_registry_sound_instances_are_cached():
    config = Config()
    registry = ProviderRegistry(config)
    registry.register_sound("fake", FakeSound)
    assert registry.get_sound("fake") is registry.get_sound("fake")


def test_registry_get_unknown_sound_raises():
    config = Config()
    registry = ProviderRegistry(config)
    with pytest.raises(ProviderError):
        registry.get_sound("nonexistent")


def test_registry_default_sound_and_names():
    config = Config()
    registry = ProviderRegistry(config)
    registry.register_sound("fake", FakeSound)
    registry.set_default_sound("fake")
    assert registry.get_default_sound() is not None
    assert registry.list_sound_names() == ["fake"]
```

- [ ] **Step 2: 运行确认 RED**

Run: `.venv/bin/python -m pytest tests/unit/test_registry.py -q`
Expected: 4 个新测试 FAIL（`AttributeError: 'ProviderRegistry' object has no attribute 'register_sound'`）。

- [ ] **Step 3: 实现 sound 段**

在 `src/storyteller/providers/registry.py` 的 `__init__` 中追加两个字典：

```python
        self._sound_factories = {}
        self._sound_instances = {}
        self._default_sound = None
```

在 `list_tts_names` 之后、`# ----- Voice aggregation -----` 之前插入：

```python
    # ----- Sound -----
    def register_sound(self, name, factory):
        """Register a sound provider. factory is a class/callable taking
        (config) and returning a SoundEffectProvider instance."""
        self._sound_factories[name] = factory

    def get_sound(self, name):
        if name not in self._sound_factories:
            raise ProviderError("Unknown sound provider: {}".format(name))
        if name not in self._sound_instances:
            self._sound_instances[name] = self._sound_factories[name](self.config)
        return self._sound_instances[name]

    def set_default_sound(self, name):
        if name not in self._sound_factories:
            raise ProviderError("Unknown sound provider: {}".format(name))
        self._default_sound = name

    def get_default_sound(self):
        if self._default_sound is None:
            return None
        return self.get_sound(self._default_sound)

    def list_sound_names(self):
        return list(self._sound_factories.keys())
```

同时把类 docstring 第一句 `"""Central registry for LLM and TTS providers.` 改为 `"""Central registry for LLM, TTS, and sound providers.`。

- [ ] **Step 4: 运行确认 GREEN**

Run: `.venv/bin/python -m pytest tests/unit/test_registry.py -q`
Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/storyteller/providers/registry.py tests/unit/test_registry.py
git commit -m "feat: add sound provider support to ProviderRegistry"
```

---

### Task 3: Bootstrap 注册 sound providers

**Files:**
- Modify: `src/storyteller/providers/bootstrap.py`
- Test: `tests/unit/test_bootstrap.py`

**Interfaces:**
- Consumes: Task 1 的 `sound.providers` / `sound.provider_config.<name>` / `sound.default_provider`；Task 2 的 registry sound 接口；`MockSoundProvider`（`storyteller.providers.mock.sfx`，name="mock"）、`VolcengineSoundProvider`（`storyteller.providers.volcengine.sfx`，name="volcengine"）
- Produces: `register_providers_from_config(config, registry)` 现在也注册音效：`type=mock` → MockSoundProvider；`type` 缺省或 `volcengine` → VolcengineSoundProvider；其他 type（aliyun/openai_compatible/未知）安静跳过。

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_bootstrap.py` 末尾追加：

```python
def test_register_mock_sound_provider():
    config = Config()
    config.set("sound.providers", ["mock"])
    config.set("sound.default_provider", "mock")
    config.set("sound.provider_config.mock", {"type": "mock"})

    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)

    assert registry.list_sound_names() == ["mock"]
    assert registry.get_sound("mock").name == "mock"
    assert registry.get_default_sound() is not None


def test_register_volcengine_sound_provider_lazily():
    config = Config()
    config.set("sound.providers", ["volcengine"])
    config.set(
        "sound.provider_config.volcengine",
        {"api_key": "sound-key"},
    )

    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)

    # Factory registered without instantiation (missing key would raise at
    # construction time; here the key exists, but listing must stay lazy).
    assert registry.list_sound_names() == ["volcengine"]


def test_unsupported_sound_type_is_skipped():
    config = Config()
    config.set("sound.providers", ["aliyun"])
    config.set(
        "sound.provider_config.aliyun",
        {"type": "aliyun", "api_key": "k"},
    )

    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)

    assert registry.list_sound_names() == []
```

- [ ] **Step 2: 运行确认 RED**

Run: `.venv/bin/python -m pytest tests/unit/test_bootstrap.py -q`
Expected: 3 个新测试 FAIL（`list_sound_names` 存在但返回空，或 AttributeError——Task 2 已合入时返回空）。

- [ ] **Step 3: 加防护导入**

在 `src/storyteller/providers/bootstrap.py` 现有 mock 导入块（24-29 行）之后追加：

```python
try:
    from .volcengine.sfx import VolcengineSoundProvider
except ImportError:  # pragma: no cover
    VolcengineSoundProvider = None

try:
    from .mock.sfx import MockSoundProvider
except ImportError:  # pragma: no cover
    MockSoundProvider = None
```

- [ ] **Step 4: 接线注册与默认值**

`register_providers_from_config` 中加一行：

```python
    _register_llms(config, registry)
    _register_tts(config, registry)
    _register_sounds(config, registry)
    _set_defaults(config, registry)
```

在 `_register_tts` 之后新增：

```python
def _register_sounds(config, registry):
    for name in config.get("sound.providers", []) or []:
        provider_config = config.get(
            "sound.provider_config.{}".format(name), {}
        ) or {}
        provider_type = provider_config.get("type")

        if provider_type == "mock" and MockSoundProvider:
            registry.register_sound(
                name, lambda c: MockSoundProvider(c)
            )
        elif provider_type in (None, "volcengine") and VolcengineSoundProvider:
            registry.register_sound(
                name, lambda c: VolcengineSoundProvider(c)
            )
        # Other types (aliyun/openai_compatible/...) have no sound
        # implementation yet — skip quietly, like missing LLM impls.
```

`_set_defaults` 末尾追加：

```python
    sound_default = config.get("sound.default_provider")
    if sound_default:
        try:
            registry.set_default_sound(sound_default)
        except ProviderError:
            pass  # not registered, ignore
```

并把 `register_providers_from_config` docstring 中的 `Register LLM and TTS providers` 改为 `Register LLM, TTS, and sound providers`。

- [ ] **Step 5: 运行确认 GREEN**

Run: `.venv/bin/python -m pytest tests/unit/test_bootstrap.py -q`
Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add src/storyteller/providers/bootstrap.py tests/unit/test_bootstrap.py
git commit -m "feat: bootstrap sound providers from config"
```

---

### Task 4: VolcengineSoundProvider 只认独立音效 key

**Files:**
- Modify: `src/storyteller/providers/volcengine/sfx.py`（docstring 17-24、`__init__` 26-42）
- Test: `tests/integration/test_volcengine_sfx.py`（删除 164-177 的复用测试，新增不回退测试）

**Interfaces:**
- Produces: 构造只读 `sound.provider_config.volcengine`；缺 key 抛
  `TTSError("Volcengine sound api_key is missing: set STORYTELLER_SOUND_VOLCENGINE_API_KEY")`。

- [ ] **Step 1: 改测试（先红）**

删除 `tests/integration/test_volcengine_sfx.py` 中的整个
`test_reuses_tts_key_when_sound_key_absent` 函数（164-177 行），在原位替换为：

```python
def test_tts_key_is_not_used_as_fallback():
    config = Config()
    config.set(
        "tts.provider_config.volcengine",
        {"api_key": "tts-key", "endpoint": _ENDPOINT},
    )
    with pytest.raises(TTSError) as exc:
        VolcengineSoundProvider(config)
    message = str(exc.value)
    assert "STORYTELLER_SOUND_VOLCENGINE_API_KEY" in message
    # The unrelated TTS key must not appear in the error either.
    assert "tts-key" not in message
```

- [ ] **Step 2: 运行确认 RED**

Run: `.venv/bin/python -m pytest tests/integration/test_volcengine_sfx.py -q`
Expected: 新测试 FAIL（当前实现回退到 tts-key，构造成功）。

- [ ] **Step 3: 修改实现**

`src/storyteller/providers/volcengine/sfx.py` 类 docstring 中

```
Reuses the TTS api key unless a dedicated sound key is
configured.
```

改为：

```
Reads its dedicated key from STORYTELLER_SOUND_VOLCENGINE_API_KEY;
there is no fallback to the TTS key.
```

`__init__` 前半段替换为：

```python
    def __init__(self, config, session=None):
        super().__init__(config)
        sound_cfg = config.get("sound.provider_config.volcengine", {}) or {}

        self.api_key = sound_cfg.get("api_key")
        self.endpoint = (
            sound_cfg.get("endpoint") or _DEFAULT_ENDPOINT
        ).rstrip("/")
        self.model = sound_cfg.get("model") or _DEFAULT_MODEL

        if not self.api_key:
            raise TTSError(
                "Volcengine sound api_key is missing: set "
                "STORYTELLER_SOUND_VOLCENGINE_API_KEY"
            )

        self._session = session or requests.Session()
```

- [ ] **Step 4: 运行确认 GREEN**

Run: `.venv/bin/python -m pytest tests/integration/test_volcengine_sfx.py -q`
Expected: 全部 PASS（含原有的 `test_missing_key_raises`）。

- [ ] **Step 5: 提交**

```bash
git add src/storyteller/providers/volcengine/sfx.py tests/integration/test_volcengine_sfx.py
git commit -m "refactor: sound provider requires dedicated SOUND key, drop TTS fallback"
```

---

### Task 5: Pipeline 从 registry 解析音效 provider + TTS 选用快速失败

**Files:**
- Modify: `src/storyteller/core/pipeline.py`（`_execute_pipeline` 121-124、`_get_sound_provider` 350-356）
- Test: `tests/e2e/test_pipeline.py`

**Interfaces:**
- Consumes: Task 2 的 `registry.get_sound/list_sound_names`；`config.get("sound.default_provider")`
- Produces: `_get_sound_provider()` 解析顺序 = 注入实例 > config 默认名（须已注册）> 首个已注册音效 provider > 抛 `TTSError("No sound provider configured: ...")`；`run/resume` 的 `tts_providers` kwarg 含未注册名时在音色匹配前抛 TTSError。

- [ ] **Step 1: 写失败测试**

`tests/e2e/test_pipeline.py` 顶部导入区加：

```python
from storyteller.core.exceptions import TTSError
```

在音效测试区（`test_sound_disabled_by_default_ignores_cues` 之后）追加：

```python
def _make_registry_sound_pipeline(tmp_path, llm, library):
    """Like _make_sound_pipeline, but the sound provider comes from the
    registry (config-selected) instead of constructor injection."""
    from storyteller.providers.mock.sfx import MockSoundProvider

    config = Config()
    config.set("data_dir", str(tmp_path / ".storyteller"))
    config.resolve_paths()
    config.set("sound.enabled", True)
    config.set("sound.dir", str(tmp_path / "sounds"))
    config.set("sound.default_provider", "mock")
    config.set("llm.default_provider", "mock")
    config.set("tts.default_provider", "mock")
    pipeline = Pipeline(config, sound_library=library)
    pipeline.registry.register_llm("mock", lambda c: llm)
    pipeline.registry.register_tts("mock", MockTTSProvider)
    pipeline.registry.register_sound("mock", MockSoundProvider)
    return pipeline


def test_run_resolves_sound_provider_from_registry(tmp_path):
    from storyteller.providers.mock.sfx import MockSoundProvider
    from storyteller.core.sound_library import SoundLibrary

    config = Config()
    llm = MockLLMProvider(config)
    llm.set_response(_sound_script())
    library = SoundLibrary(tmp_path / "sounds")
    pipeline = _make_registry_sound_pipeline(tmp_path, llm, library)

    result_path = Path(pipeline.run("雨夜"))
    assert result_path.exists()
    # Both cues generated through the registry-resolved mock provider.
    assert len(library.all()) == 2
    assert isinstance(pipeline._get_sound_provider(), MockSoundProvider)


def test_sound_enabled_without_any_provider_raises(tmp_path):
    # The mock default script has no cues, so use _sound_script(): the
    # soundtrack stage only resolves the provider when pending cues exist.
    config = Config()
    config.set("data_dir", str(tmp_path / ".storyteller"))
    config.resolve_paths()
    config.set("sound.enabled", True)
    config.set("sound.dir", str(tmp_path / "sounds"))
    config.set("llm.default_provider", "mock")
    config.set("tts.default_provider", "mock")
    llm = MockLLMProvider(config)
    llm.set_response(_sound_script())
    pipeline = Pipeline(config)
    pipeline.registry.register_llm("mock", lambda c: llm)
    pipeline.registry.register_tts("mock", MockTTSProvider)
    # No sound provider registered at all.

    with pytest.raises(TTSError, match="No sound provider configured"):
        pipeline.run("雨夜")


def test_unknown_tts_provider_fails_before_matching(tmp_path):
    pipeline = _make_pipeline(tmp_path)
    with pytest.raises(TTSError, match="Unknown TTS provider"):
        pipeline.run("雨夜", tts_providers=["aliyun"])
```

- [ ] **Step 2: 运行确认 RED**

Run: `.venv/bin/python -m pytest tests/e2e/test_pipeline.py -q`
Expected: 3 个新测试 FAIL（registry 解析路径仍硬编码 Volcengine 会因缺 key 抛别的 TTSError；无 provider 用例得到的是火山缺 key 错误；未知 tts 目前走到空音色错误）。

- [ ] **Step 3: 实现音效 provider 解析**

把 `_get_sound_provider` 整体替换为：

```python
    def _get_sound_provider(self):
        if self._sound_provider is not None:
            return self._sound_provider
        names = self.registry.list_sound_names()
        name = self.config.get("sound.default_provider")
        if name not in names:
            # An unregistered default is ignored the same way bootstrap
            # ignores it; fall back to the first registered provider.
            name = names[0] if names else None
        if name is None:
            raise TTSError(
                "No sound provider configured: set "
                "STORYTELLER_SOUND_<NAME>_API_KEY "
                "(use --sound-provider to choose one)"
            )
        self._sound_provider = self.registry.get_sound(name)
        return self._sound_provider
```

- [ ] **Step 4: 实现 TTS 选用校验**

在 `_execute_pipeline` Step 2（`if state.state not in ("voice_configured", ...)` 块内、`tts_voices = self.registry.list_tts_voices()` 之前）插入：

```python
            selected_tts = kwargs.get("tts_providers")
            if selected_tts is not None:
                known_tts = self.registry.list_tts_names()
                unknown_tts = [p for p in selected_tts if p not in known_tts]
                if unknown_tts:
                    raise TTSError(
                        "Unknown TTS provider(s): {}. Configured providers: "
                        "{}. Set STORYTELLER_TTS_<NAME>_API_KEY for each "
                        "(and STORYTELLER_TTS_<NAME>_TYPE for non-Volcengine "
                        "implementations), or choose from the configured list."
                        .format(
                            ", ".join(unknown_tts),
                            ", ".join(known_tts) or "(none)",
                        )
                    )
```

- [ ] **Step 5: 运行确认 GREEN**

Run: `.venv/bin/python -m pytest tests/e2e/test_pipeline.py -q`
Expected: 全部 PASS（含原有注入式音效测试，证明注入优先未变）。

- [ ] **Step 6: 提交**

```bash
git add src/storyteller/core/pipeline.py tests/e2e/test_pipeline.py
git commit -m "feat: resolve sound provider via registry and fail fast on unknown TTS selection"
```

---

### Task 6: CLI generate/continue 的 --sound-provider 与 continue 参数补齐

**Files:**
- Modify: `src/storyteller/cli/main.py`（`_build_pipeline` 85-97、`generate` 装饰器 119-130、`continue_` 装饰器 179-201）
- Test: `tests/e2e/test_cli.py`

**Interfaces:**
- Consumes: Task 2/3 的 registry sound 列表；config `sound.default_provider`
- Produces: `generate` 与 `continue` 均支持 `--sound-provider NAME`（写入 `sound.default_provider`）；`continue` 另支持 `--default-llm-provider`、`--default-tts-provider`；显式指定的音效 provider 未注册时在任何生成前 ClickException 并列出已注册名。

- [ ] **Step 1: 写失败测试**

把 `tests/e2e/test_cli.py` 的 `_MOCK_ENV` 改为：

```python
_MOCK_ENV = {
    "STORYTELLER_LLM_PROVIDERS": "mock",
    "STORYTELLER_LLM_MOCK_TYPE": "mock",
    "STORYTELLER_LLM_DEFAULT_PROVIDER": "mock",
    "STORYTELLER_TTS_PROVIDERS": "mock",
    "STORYTELLER_TTS_MOCK_TYPE": "mock",
    "STORYTELLER_TTS_DEFAULT_PROVIDER": "mock",
    "STORYTELLER_SOUND_PROVIDERS": "mock",
    "STORYTELLER_SOUND_MOCK_TYPE": "mock",
}
```

在 `test_generate_dry_run` 之后追加：

```python
def test_generate_with_sound_provider_flag():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["generate", "测试故事", "--with-sfx", "--sound-provider", "mock"],
            env=_MOCK_ENV,
        )
        assert result.exit_code == 0, result.output


def test_generate_unknown_sound_provider_fails_before_generation():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["generate", "测试故事", "--sound-provider", "nope"],
            env=_MOCK_ENV,
        )
        assert result.exit_code != 0
        assert "Unknown sound provider" in result.output
        assert "mock" in result.output


def test_continue_accepts_provider_selection_flags():
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Unknown project, but click must accept every flag first
        # (regression: continue used to lack these options).
        result = runner.invoke(
            cli,
            [
                "continue", "proj_does_not_exist",
                "--default-llm-provider", "mock",
                "--default-tts-provider", "mock",
                "--sound-provider", "mock",
            ],
            env=_MOCK_ENV,
        )
        assert result.exit_code != 0
        assert "no such option" not in result.output.lower()
```

- [ ] **Step 2: 运行确认 RED**

Run: `.venv/bin/python -m pytest tests/e2e/test_cli.py -q`
Expected: 3 个新测试 FAIL（`no such option: --sound-provider`）；既有测试应仍 PASS。

- [ ] **Step 3: _build_pipeline 写入与校验**

把 `_build_pipeline` 整体替换为：

```python
def _build_pipeline(**options):
    config = Config.from_env()
    _apply_options(config, **options)

    # Provider overrides from CLI
    if options.get("default_llm_provider"):
        config.set("llm.default_provider", options["default_llm_provider"])
    if options.get("default_tts_provider"):
        config.set("tts.default_provider", options["default_tts_provider"])
    if options.get("sound_provider"):
        config.set("sound.default_provider", options["sound_provider"])

    pipeline = Pipeline(config)
    register_providers_from_config(config, pipeline.registry)

    requested_sound = options.get("sound_provider")
    if requested_sound is not None:
        available = pipeline.registry.list_sound_names()
        if requested_sound not in available:
            raise click.ClickException(
                "Unknown sound provider: {}. Configured sound providers: "
                "{}. Set STORYTELLER_SOUND_<NAME>_API_KEY to configure one."
                .format(requested_sound, ", ".join(available) or "(none)")
            )
    return pipeline
```

- [ ] **Step 4: generate 加选项**

在 `generate` 的 `--sound-dir` 装饰器之后加：

```python
@click.option(
    "--sound-provider",
    default=None,
    help="本次运行使用的音效 provider（覆盖环境默认）",
)
```

（该参数经 `**options` 流入 `_build_pipeline`，无需改函数签名。）

- [ ] **Step 5: continue 加三个选项**

在 `continue_` 的 `--sound-dir` 装饰器之后加：

```python
@click.option("--default-llm-provider", default=None, help="默认LLM provider")
@click.option("--default-tts-provider", default=None, help="默认TTS provider")
@click.option(
    "--sound-provider",
    default=None,
    help="本次运行使用的音效 provider（覆盖环境默认）",
)
```

（三个参数均经 `**options` 被 `_build_pipeline(**options)` 消费。）

- [ ] **Step 6: 运行确认 GREEN**

Run: `.venv/bin/python -m pytest tests/e2e/test_cli.py -q`
Expected: 全部 PASS。

- [ ] **Step 7: 提交**

```bash
git add src/storyteller/cli/main.py tests/e2e/test_cli.py
git commit -m "feat: --sound-provider on generate/continue and continue provider parity"
```

---

### Task 7: make-sound 走 registry 并支持 --sound-provider

**Files:**
- Modify: `src/storyteller/cli/main.py`（`make_sound` 396-437）
- Test: `tests/e2e/test_cli.py`

**Interfaces:**
- Consumes: `ProviderRegistry(config)` + `register_providers_from_config`；解析顺序 CLI 参数 > `sound.default_provider` > 首个已注册音效 provider；全无则 ClickException。
- Produces: `make-sound --sound-provider NAME`，不再硬编码 `VolcengineSoundProvider`。

- [ ] **Step 1: 写失败测试**

在 `tests/e2e/test_cli.py` 末尾追加：

```python
def test_make_sound_uses_registry_provider():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["make-sound", "舒缓的雨声", "--sound-provider", "mock"],
            env=_MOCK_ENV,
        )
        assert result.exit_code == 0, result.output
        assert "Generated" in result.output


def test_make_sound_without_configured_provider_errors():
    runner = CliRunner()
    env = {
        "STORYTELLER_LLM_PROVIDERS": "mock",
        "STORYTELLER_TTS_PROVIDERS": "mock",
    }
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli, ["make-sound", "风声"], env=env
        )
        assert result.exit_code != 0
        assert "No sound provider configured" in result.output
```

- [ ] **Step 2: 运行确认 RED**

Run: `.venv/bin/python -m pytest tests/e2e/test_cli.py -q`
Expected: 两个新测试 FAIL（`no such option: --sound-provider`；当前 make-sound 直接构造火山 provider 报缺 key，错误文案不同）。

- [ ] **Step 3: 重写 make-sound**

把 `make_sound` 整体替换为：

```python
# ========== make-sound ==========
@cli.command(name="make-sound")
@click.argument("prompt")
@click.option("--name", default=None, help="音效名称（默认取提示词开头）")
@click.option(
    "--kind",
    type=click.Choice(["sfx", "ambient", "music"]),
    default="sfx",
    help="类型：sfx 短促音效 / ambient 环境声 / music 音乐",
)
@click.option("--description", default="", help="这条音效的描述（便于检索复用）")
@click.option("--tags", default="", help="逗号分隔的标签")
@click.option("--format", "audio_format", default="mp3", help="输出格式 mp3/wav")
@click.option("--sound-dir", default=None, help="音效库目录（默认 <data-dir>/sounds）")
@click.option(
    "--sound-provider",
    default=None,
    help="使用的音效 provider（默认取 STORYTELLER_SOUND_DEFAULT_PROVIDER）",
)
def make_sound(prompt, name, kind, description, tags, audio_format,
               sound_dir, sound_provider):
    """用文字提示生成/复用一个音效，写入全局音效库。"""
    config = Config.from_env()
    if sound_dir:
        config.set("sound.dir", sound_dir)

    from ..core.sound_library import SoundLibrary
    from ..providers.registry import ProviderRegistry

    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)

    chosen = sound_provider or config.get("sound.default_provider")
    available = registry.list_sound_names()
    if chosen is None and available:
        chosen = available[0]
    if chosen is None or chosen not in available:
        raise click.ClickException(
            "No sound provider configured: set "
            "STORYTELLER_SOUND_<NAME>_API_KEY (or pass --sound-provider)."
        )

    library = SoundLibrary(
        config.get("sound.dir") or "./.storyteller/sounds"
    )
    try:
        provider = registry.get_sound(chosen)
        path, record, created = library.get_or_create(
            provider,
            prompt=prompt,
            name=name or prompt[:12],
            kind=kind,
            description=description,
            tags=[t.strip() for t in tags.split(",") if t.strip()],
            audio_format=audio_format,
        )
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(str(exc))

    if created:
        click.echo("Generated: {}".format(path))
    else:
        click.echo("Cache hit (no API call): {}".format(path))
    click.echo("Name: {}  kind: {}".format(record["name"], record["kind"]))
```

- [ ] **Step 4: 运行确认 GREEN**

Run: `.venv/bin/python -m pytest tests/e2e/test_cli.py -q`
Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/storyteller/cli/main.py tests/e2e/test_cli.py
git commit -m "feat: make-sound selects sound provider via registry"
```

---

### Task 8: 向导音效开关与 provider 选择

**Files:**
- Modify: `src/storyteller/cli/interactive.py`（`run_wizard` 49-75、新增 `_prompt_sound`）
- Modify: `src/storyteller/cli/main.py`（`wizard` 命令 27-42）
- Test: `tests/e2e/test_cli.py`

**Interfaces:**
- Produces: `run_wizard()` 返回 8 元组
  `(pipeline, topic, length, complexity, output_format, tts_providers, with_sfx, sound_provider)`，
  其中 `with_sfx: bool`（默认跟随 `STORYTELLER_SOUND_ENABLED`，直接回车取该默认），
  `sound_provider: str|None`（启用且有 2+ provider 时让用户选；恰好 1 个直接用它；0 个为 None）。

- [ ] **Step 1: 更新/新增测试**

把 `test_wizard_full_flow` 的输入序列注释与列表改为（末尾新增一个音效提问，回车=不启用）：

```python
        # Input sequence: topic, length, complexity, format, voice-mode,
        # sound on/off (empty = default off)
        user_input = "\n".join(
            [
                "小猫迷路了",  # topic
                "2",           # length: medium
                "1",           # complexity: simple
                "1",           # format: mp3
                "1",           # voice mode: auto
                "",            # sound: no
            ]
        ) + "\n"
```

把 `test_wizard_rejects_empty_topic` 的列表末尾同样补一个 `""`（在最后一个 `"1"` 之后加一行 `                "",            # sound: no`）。

文件末尾追加：

```python
def test_wizard_enables_sound_with_single_provider():
    runner = CliRunner()
    env = dict(_MOCK_ENV)
    env["STORYTELLER_SOUND_PROVIDERS"] = "mock"
    with runner.isolated_filesystem():
        user_input = "\n".join(
            ["雨夜", "2", "1", "1", "1", "y"]
        ) + "\n"
        result = runner.invoke(cli, [], input=user_input, env=env)
        assert result.exit_code == 0, result.output
        assert "Done" in result.output


def test_wizard_chooses_between_multiple_sound_providers():
    runner = CliRunner()
    env = dict(_MOCK_ENV)
    env.update(
        {
            "STORYTELLER_SOUND_PROVIDERS": "mock,mock2",
            "STORYTELLER_SOUND_MOCK_TYPE": "mock",
            "STORYTELLER_SOUND_MOCK2_TYPE": "mock",
        }
    )
    with runner.isolated_filesystem():
        user_input = "\n".join(
            ["雨夜", "2", "1", "1", "1", "y", "1"]
        ) + "\n"
        result = runner.invoke(cli, [], input=user_input, env=env)
        assert result.exit_code == 0, result.output
        assert "音效 provider" in result.output
```

- [ ] **Step 2: 运行确认 RED**

Run: `.venv/bin/python -m pytest tests/e2e/test_cli.py -q`
Expected: 两个旧向导测试 FAIL（输入耗尽后行为异常/非零退出），两个新测试 FAIL。

- [ ] **Step 3: interactive.py 新增提问并扩展返回值**

`run_wizard` 中

```python
    pipeline = _build_pipeline(config)
    tts_providers = _prompt_voice_mode(pipeline, config)

    return pipeline, topic, length, complexity, output_format, tts_providers
```

替换为：

```python
    pipeline = _build_pipeline(config)
    tts_providers = _prompt_voice_mode(pipeline, config)
    with_sfx, sound_provider = _prompt_sound(pipeline, config)

    return (
        pipeline, topic, length, complexity, output_format,
        tts_providers, with_sfx, sound_provider,
    )
```

在 `_prompt_voice_mode` 之后新增：

```python
def _prompt_sound(pipeline, config):
    """Ask whether to enable sound effects, and which provider when >1."""
    default_enabled = bool(config.get("sound.enabled"))
    click.echo("\n音效与背景音乐：")
    raw = click.prompt(
        "是否启用音效与背景音乐？(y/n)",
        default="y" if default_enabled else "n",
        show_default=True,
    )
    enabled = parse_yes_no(raw, default=default_enabled)
    if not enabled:
        return False, None

    names = pipeline.registry.list_sound_names()
    if len(names) == 1:
        return True, names[0]
    if len(names) > 1:
        click.echo("\n选择音效 provider：")
        for i, name in enumerate(names, start=1):
            click.echo("  [{}] {}".format(i, name))
        chosen = parse_choice(click.prompt("请选择", default="1"), names, 0)
        return True, chosen
    # Enabled but no provider configured; let the run fail with the clear
    # config error rather than rejecting the answer in the wizard.
    return True, None
```

- [ ] **Step 4: main.py wizard 命令接线**

把 `wizard` 函数整体替换为：

```python
@cli.command()
def wizard():
    """交互式向导模式（无参数运行时的默认入口）。"""
    from .interactive import run_wizard

    (
        pipeline, topic, length, complexity, output_format,
        tts_providers, with_sfx, sound_provider,
    ) = run_wizard()
    if with_sfx:
        pipeline.config.set("sound.enabled", True)
    if sound_provider:
        pipeline.config.set("sound.default_provider", sound_provider)
    kwargs = {"output_format": output_format}
    if tts_providers:
        kwargs["tts_providers"] = tts_providers
    try:
        output_path = pipeline.run(
            topic, length=length, complexity=complexity, **kwargs
        )
    except Exception as exc:
        raise click.ClickException(str(exc))
    click.echo("Done! Output: {}".format(output_path))
```

- [ ] **Step 5: 运行确认 GREEN**

Run: `.venv/bin/python -m pytest tests/e2e/test_cli.py tests/unit/test_interactive.py -q`
Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add src/storyteller/cli/interactive.py src/storyteller/cli/main.py tests/e2e/test_cli.py
git commit -m "feat: wizard prompts for sound on/off and sound provider"
```

---

### Task 9: 文档与 .env.example 迁移

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: .env.example 标注 PROVIDERS 语义为可选**

把 15-17 行：

```
# ===== LLM Provider =====
STORYTELLER_LLM_PROVIDERS=volcengine
```

改为：

```
# ===== LLM Provider =====
# PROVIDERS 为可选的默认启用/排序列表：配了下面的 per-provider 变量即可被
# --default-llm-provider 选用，不必把名字写进这里
STORYTELLER_LLM_PROVIDERS=volcengine
```

把 24-25 行：

```
# ===== TTS Provider =====
STORYTELLER_TTS_PROVIDERS=volcengine
```

改为：

```
# ===== TTS Provider =====
# PROVIDERS 为可选的默认启用/排序列表：配了 per-provider 变量即可被
# --tts-providers / --default-tts-provider 选用，不必把名字写进这里
STORYTELLER_TTS_PROVIDERS=volcengine
```

- [ ] **Step 2: .env.example 替换音效块**

把 43-51 行整个音效块替换为：

```
# ===== 音效 / 背景音乐（seed-audio，默认关闭）=====
# 开启后写剧本会附带音效/BGM 提示，生成时自动混音；CLI 也可用 --with-sfx 开启
STORYTELLER_SOUND_ENABLED=false
# 全局共享音效库目录（相同音效只生成一次，跨项目复用）；留空即 <DATA_DIR>/sounds
# STORYTELLER_SOUND_DIR=./.storyteller/sounds
# 音效是独立 provider 分组（与 LLM/TTS 同构）：配了 key 即可被 --sound-provider
# 选用；下面两个 PROVIDERS/DEFAULT 变量均可选
# STORYTELLER_SOUND_PROVIDERS=volcengine
# STORYTELLER_SOUND_DEFAULT_PROVIDER=volcengine
# 独立音效 Key（不复用 TTS Key；启用音效必填）
STORYTELLER_SOUND_VOLCENGINE_API_KEY=
STORYTELLER_SOUND_VOLCENGINE_MODEL=seed-audio-1.0
# STORYTELLER_SOUND_VOLCENGINE_ENDPOINT=https://openspeech.bytedance.com/api/v3/tts/create
```

- [ ] **Step 3: README 配置表更新**

把 README 配置表中这一行：

```
| `STORYTELLER_SFX_VOLCENGINE_API_KEY` | 音效 Key（seed-audio），留空则复用 TTS Key |
```

替换为：

```
| `STORYTELLER_SOUND_VOLCENGINE_API_KEY` | 音效 Key（seed-audio），独立配置、不复用 TTS Key；启用音效必填 |
| `STORYTELLER_SOUND_PROVIDERS` / `STORYTELLER_SOUND_DEFAULT_PROVIDER` | 可选的音效 provider 启用名单/默认（同 LLM/TTS 规则，配了 key 即可被 `--sound-provider` 选用） |

表格结束后另起一段补一句说明（不要插进表格中间）：

```
> `*_PROVIDERS` 均为可选项，只决定默认启用与排序；只要配了某 provider 的 per-provider 变量（如 `STORYTELLER_TTS_ALIYUN_API_KEY`），就能直接用命令行参数选用，不必改名单。
```

- [ ] **Step 4: README 命令参数表更新**

generate 参数表中 `--with-sfx` 行之后插入两行：

```
| `--sound-provider` | 本次使用的音效 provider（需配合 `--with-sfx`） | 否 | 环境默认 | provider 名，如 `volcengine` |
```

continue 段落（`沿用项目已保存的...` 那段）把可选参数列表句：

```
可选参数（含义与 `generate` 相同）：`--output-format/-f`、`--tts-providers`、`--voice-ids`、`--voice-matcher`、`--with-sfx`、`--sound-dir`、`--data-dir`、`--strict-mode`。
```

替换为：

```
可选参数（含义与 `generate` 相同）：`--output-format/-f`、`--tts-providers`、`--voice-ids`、`--default-llm-provider`、`--default-tts-provider`、`--voice-matcher`、`--with-sfx`、`--sound-provider`、`--sound-dir`、`--data-dir`、`--strict-mode`。
```

make-sound 参数表末尾（`--sound-dir` 行之后）加一行：

```
| `--sound-provider` | 使用的音效 provider | 否 | `STORYTELLER_SOUND_DEFAULT_PROVIDER` 或首个已配置 provider | provider 名 |
```

「通用说明」中 generate/continue 共用列表：

```
- `generate` 与 `continue` 共用：`--tts-providers`、`--voice-ids`、`--voice-matcher`、`--with-sfx`、`--sound-dir`、`--data-dir`、`--strict-mode`、`--output-format`。
```

替换为：

```
- `generate` 与 `continue` 共用：`--tts-providers`、`--voice-ids`、`--default-llm-provider`、`--default-tts-provider`、`--voice-matcher`、`--with-sfx`、`--sound-provider`、`--sound-dir`、`--data-dir`、`--strict-mode`、`--output-format`。
```

- [ ] **Step 5: README 音效段与阿里云段更新**

在「## 音效与背景音乐」标题段正文第一句

```
`--with-sfx`（或 `STORYTELLER_SOUND_ENABLED=true`）开启后：
```

之后紧接着补充一段：

```
> 音效是与 LLM/TTS 同构的独立 provider 分组：用 `STORYTELLER_SOUND_VOLCENGINE_API_KEY` 配置独立 Key（**不复用、不回退 TTS Key**），可用 `--sound-provider NAME`（generate/continue/make-sound）或 `STORYTELLER_SOUND_DEFAULT_PROVIDER` 选择。旧变量 `STORYTELLER_SFX_VOLCENGINE_*` 已移除。
```

把「接入阿里云百炼 TTS」段中的：

```
STORYTELLER_TTS_PROVIDERS=volcengine,aliyun
STORYTELLER_TTS_ALIYUN_TYPE=aliyun
STORYTELLER_TTS_ALIYUN_API_KEY=your_dashscope_key
```

代码块替换为：

```
# 配了 TYPE + API_KEY 即自动注册，可直接 --tts-providers aliyun 选用；
# 不必再把 aliyun 加进 STORYTELLER_TTS_PROVIDERS（该名单只控制默认启用/排序）
STORYTELLER_TTS_ALIYUN_TYPE=aliyun
STORYTELLER_TTS_ALIYUN_API_KEY=your_dashscope_key
# 可选：业务空间专属域名（替换 WorkspaceId），不填走通用域名
# STORYTELLER_TTS_ALIYUN_ENDPOINT=https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com
```

（同段后面关于 `STORYTELLER_TTS_DEFAULT_PROVIDER` 的句子保留不动。）

- [ ] **Step 6: 提交文档**

```bash
git add .env.example README.md
git commit -m "docs: document provider auto-discovery and independent sound provider config"
```

---

### Task 10: 全量验证、本机 .env 迁移、记忆更新

**Files:**
- 本地 `.env`（gitignored，不入库）
- Modify: `/Users/lizhe/.claude/projects/-Users-lizhe-Documents-workspace-audio-story-generator/memory/storyteller-project.md`

- [ ] **Step 1: 全量测试**

Run: `.venv/bin/python -m pytest -q`
Expected: 全部 PASS，无 warning。

- [ ] **Step 2: wheel 打包自检（新文件均随包）**

Run:

```bash
rm -rf /tmp/storyteller-wheels \
  && .venv/bin/pip wheel . --no-deps -w /tmp/storyteller-wheels >/dev/null 2>&1 \
  && unzip -l /tmp/storyteller-wheels/storyteller-*.whl | grep -E "registry.py|bootstrap.py|sfx.py"
```

Expected: 列出 `providers/registry.py`、`providers/bootstrap.py`、`providers/volcengine/sfx.py`、`providers/mock/sfx.py`（均为包内 .py，本任务无新增数据文件）。

- [ ] **Step 3: 迁移本机 .env（不提交）**

编辑被 gitignore 的本地 `.env`：

- 删除或注释 `STORYTELLER_SFX_VOLCENGINE_API_KEY` / `_MODEL` / `_ENDPOINT`；
- 新增 `STORYTELLER_SOUND_VOLCENGINE_API_KEY=<原来的音效key值>`（若原来留空复用 TTS key，则把火山 **TTS** key 值复制到这里）；
- 可选加 `STORYTELLER_SOUND_DEFAULT_PROVIDER=volcengine`。

验证：

```bash
grep -n "STORYTELLER_SFX_" .env; echo "---"; grep -n "STORYTELLER_SOUND_" .env
```

Expected: 第一条无输出；第二条显示新变量。确认 `git status --short` 不含 `.env`。

- [ ] **Step 4: CLI 真机冒烟（手动，可选但建议）**

Run:

```bash
.venv/bin/storyteller make-sound "轻柔的笛声" --sound-provider volcengine
```

Expected: `Generated: ...`（真实 seed-audio 调用，产生一次 API 费用）；再跑一次应 `Cache hit`。若报缺 key，按错误信息检查 Step 3。

- [ ] **Step 5: 更新项目记忆**

在记忆文件「音效/BGM 端到端」那条中，把关于 key 的描述

```
Key 缺省复用 TTS key，可用 `STORYTELLER_SFX_VOLCENGINE_API_KEY/MODEL/ENDPOINT` 覆盖
```

改为：

```
音效是独立 provider 分组（2026/09/11 重构）：`STORYTELLER_SOUND_PROVIDERS/DEFAULT_PROVIDER/SOUND_<NAME>_{API_KEY,MODEL,ENDPOINT}`，与 LLM/TTS 同构；只从 `STORYTELLER_SOUND_VOLCENGINE_API_KEY` 读 key，不回退 TTS key；旧 `STORYTELLER_SFX_VOLCENGINE_*` 已移除不兼容。CLI generate/continue/make-sound 有 `--sound-provider`，向导弹音效开关/选择
```

并在合适位置（阿里云 TTS 记录之后或该条内）补一句配置模型变化：

```
- Provider 配置即注册（2026/09/11）：llm/tts/sound 三类统一，存在 `STORYTELLER_<KIND>_<NAME>_*` 变量即自动发现注册，`*_PROVIDERS` 降为可选的默认启用/排序列表；`--tts-providers` 选未配置名时提前报带环境变量提示的错误
```

- [ ] **Step 6: 最终提交检查**

Run: `git status --short && git log --oneline -10`
Expected: 工作区干净（`.env`、`.storyteller/` 不出现）；10 个任务的提交都在。
