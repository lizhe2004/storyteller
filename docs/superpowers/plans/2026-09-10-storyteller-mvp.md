# Storyteller MVP 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个可用的音频故事生成CLI工具，支持从主题生成带角色声音的音频故事。

**Architecture:** 经典分层架构，core层定义抽象接口，providers层实现火山引擎和OpenAI兼容provider，pipeline串联流程，cli处理用户交互。每个组件职责单一，可独立测试。

**Tech Stack:** Python 3.10+, dataclasses, pydantic(可选), pyyaml, click, pytest, requests, pydub

**Spec:** docs/superpowers/specs/2026-09-10-storyteller-design.md

## Global Constraints

- Python 版本 >= 3.10
- 敏感配置通过环境变量，不写入代码或配置文件
- 代码遵循 PEP 8
- 每个任务必须有对应的测试
- 频繁提交，每个任务一个提交
- TDD 模式：先写失败的测试，再写实现

---

## 文件结构

**将创建的文件：**

```
storyteller/
├── __init__.py
├── pyproject.toml
├── requirements.txt
├── .env.example
├── README.md
├── src/storyteller/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py              # 数据模型
│   │   ├── exceptions.py          # 异常类
│   │   ├── utils.py               # 工具函数
│   │   ├── config.py              # 配置管理
│   │   ├── llm.py                 # LLM抽象接口
│   │   ├── tts.py                 # TTS抽象接口
│   │   ├── audio.py               # 音频处理抽象
│   │   ├── story_generator.py     # 剧本生成
│   │   ├── voice_matcher.py       # 声音匹配
│   │   ├── project.py             # 项目状态管理
│   │   └── pipeline.py            # 流程编排
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                # Provider基类
│   │   ├── registry.py            # Provider注册中心
│   │   ├── mock/
│   │   │   ├── __init__.py
│   │   │   ├── llm.py             # Mock LLM（测试用）
│   │   │   └── tts.py             # Mock TTS（测试用）
│   │   ├── volcengine/
│   │   │   ├── __init__.py
│   │   │   ├── llm.py             # 火山引擎LLM
│   │   │   └── tts.py             # 火山引擎TTS
│   │   └── openai_compatible/
│   │       ├── __init__.py
│   │       ├── llm.py             # OpenAI兼容LLM
│   │       └── tts.py             # OpenAI兼容TTS
│   └── cli/
│       ├── __init__.py
│       ├── main.py                # CLI入口
│       └── interactive.py         # 交互式向导
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── unit/
    │   ├── __init__.py
    │   ├── test_models.py
    │   ├── test_config.py
    │   ├── test_utils.py
    │   ├── test_story_generator.py
    │   ├── test_voice_matcher.py
    │   ├── test_project.py
    │   └── test_pipeline.py
    ├── integration/
    │   ├── __init__.py
    │   └── test_providers.py
    └── e2e/
        ├── __init__.py
        └── test_cli.py
```

---

## Task 1: 项目初始化和基础配置

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `README.md`
- Create: `src/storyteller/__init__.py`
- Create: `src/storyteller/core/__init__.py`
- Create: `src/storyteller/providers/__init__.py`
- Create: `src/storyteller/cli/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/e2e/__init__.py`

**Interfaces:**
- Consumes: 无
- Produces: 基础项目结构，pytest配置

- [ ] **Step 1: 创建 requirements.txt**

```text
# requirements.txt
click>=8.0
pyyaml>=6.0
requests>=2.28
pydub>=0.25
python-dotenv>=1.0
dataclasses-json>=0.5
```

- [ ] **Step 2: 创建 pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "storyteller"
version = "0.1.0"
description = "Audio story generator"
requires-python = ">=3.10"
dependencies = [
    "click>=8.0",
    "pyyaml>=6.0",
    "requests>=2.28",
    "pydub>=0.25",
    "python-dotenv>=1.0",
    "dataclasses-json>=0.5",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
]

[project.scripts]
storyteller = "storyteller.cli.main:cli"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 3: 创建 .env.example**

```bash
# .env.example
# Global
STORYTELLER_OUTPUT_DIR=./outputs
STORYTELLER_PROJECT_DIR=./projects
STORYTELLER_LOG_LEVEL=info

# LLM
STORYTELLER_LLM_PROVIDERS=volcengine
STORYTELLER_LLM_DEFAULT_PROVIDER=volcengine

# Volcengine LLM
STORYTELLER_LLM_VOLCENGINE_API_KEY=your_api_key_here
STORYTELLER_LLM_VOLCENGINE_MODEL=doubao-pro-4k
STORYTELLER_LLM_VOLCENGINE_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3

# TTS
STORYTELLER_TTS_PROVIDERS=volcengine
STORYTELLER_TTS_DEFAULT_PROVIDER=volcengine

# Volcengine TTS
STORYTELLER_TTS_VOLCENGINE_API_KEY=your_api_key_here
STORYTELLER_TTS_VOLCENGINE_ENDPOINT=https://openspeech.bytedance.com/api/v1/tts
```

- [ ] **Step 4: 创建空的 __init__.py 文件**

所有 `__init__.py` 文件内容为空，先创建出来。

- [ ] **Step 5: 创建 tests/conftest.py**

```python
# tests/conftest.py
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)
```

- [ ] **Step 6: 创建 README.md**

```markdown
# Storyteller

音频故事生成工具

## 安装

```bash
pip install -e .[dev]
```

## 配置

复制 `.env.example` 到 `.env` 并填入你的 API Key。

## 使用

```bash
storyteller "一只小猫的冒险"
```
```

- [ ] **Step 7: 创建测试来验证项目结构**

写一个简单的测试验证包可以导入：

```python
# tests/unit/test_import.py
def test_import_storyteller():
    import storyteller
    assert storyteller is not None
```

- [ ] **Step 8: 运行测试验证通过**

Run: `pytest tests/unit/test_import.py -v`
Expected: PASS

- [ ] **Step 9: 提交**

```bash
git add pyproject.toml requirements.txt .env.example README.md src tests
git commit -m "chore: initial project setup"
```

---

## Task 2: 数据模型和异常类

**Files:**
- Create: `src/storyteller/core/exceptions.py`
- Create: `src/storyteller/core/models.py`
- Test: `tests/unit/test_models.py`

**Interfaces:**
- Consumes: 无
- Produces: 
  - 异常类：`StorytellerError`, `ConfigError`, `ProviderError`, `LLMError`, `TTSError`, `AudioProcessingError`, `ProjectError`
  - 数据类：`SoundEffect`, `VoiceConfig`, `Character`, `ScriptLine`, `Script`, `ProjectState`

- [ ] **Step 1: 写测试 - exceptions**

```python
# tests/unit/test_exceptions.py
import pytest
from storyteller.core.exceptions import (
    StorytellerError, ConfigError, ProviderError,
    LLMError, TTSError, AudioProcessingError, ProjectError
)

def test_all_exceptions_are_storyteller_error():
    assert issubclass(ConfigError, StorytellerError)
    assert issubclass(ProviderError, StorytellerError)
    assert issubclass(LLMError, StorytellerError)
    assert issubclass(TTSError, StorytellerError)
    assert issubclass(AudioProcessingError, StorytellerError)
    assert issubclass(ProjectError, StorytellerError)

def test_exception_carries_message():
    err = ConfigError("test message")
    assert str(err) == "test message"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/unit/test_exceptions.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 exceptions.py**

```python
# src/storyteller/core/exceptions.py
class StorytellerError(Exception):
    """Base exception for all storyteller errors."""
    pass


class ConfigError(StorytellerError):
    """Configuration related errors."""
    pass


class ProviderError(StorytellerError):
    """Provider related errors."""
    pass


class LLMError(ProviderError):
    """LLM provider errors."""
    pass


class TTSError(ProviderError):
    """TTS provider errors."""
    pass


class AudioProcessingError(StorytellerError):
    """Audio processing errors."""
    pass


class ProjectError(StorytellerError):
    """Project/save-load errors."""
    pass
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/unit/test_exceptions.py -v`
Expected: PASS

- [ ] **Step 5: 写测试 - models**

```python
# tests/unit/test_models.py
from datetime import datetime
from storyteller.core.models import (
    SoundEffect, VoiceConfig, Character, ScriptLine, Script, ProjectState
)


def test_voice_config_creation():
    vc = VoiceConfig(
        provider="volcengine",
        voice_id="test_voice",
        voice_type="narrator",
        language="zh-CN"
    )
    assert vc.provider == "volcengine"
    assert vc.voice_id == "test_voice"
    assert vc.speed == 1.0


def test_character_creation():
    char = Character(
        id="narrator",
        name="旁白",
        description="故事旁白"
    )
    assert char.id == "narrator"
    assert char.voice_config is None


def test_script_line_creation():
    line = ScriptLine(
        line_id="1",
        line_type="narration",
        text="从前有座山..."
    )
    assert line.line_type == "narration"
    assert line.character_id is None


def test_script_creation():
    script = Script(
        script_id="test-001",
        title="测试故事",
        topic="测试",
    )
    assert script.script_id == "test-001"
    assert len(script.characters) == 0
    assert len(script.lines) == 0
    assert isinstance(script.created_at, datetime)
```

- [ ] **Step 6: 运行测试验证失败**

Run: `pytest tests/unit/test_models.py -v`
Expected: FAIL (module not found)

- [ ] **Step 7: 实现 models.py**

```python
# src/storyteller/core/models.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal
from enum import Enum


# ========== Enums ==========
class LineType(str, Enum):
    DIALOGUE = "dialogue"
    NARRATION = "narration"


class SoundType(str, Enum):
    AMBIENT = "ambient"
    EFFECT = "effect"
    MUSIC = "music"


class ProjectStatus(str, Enum):
    INITIALIZED = "initialized"
    TOPIC_COLLECTED = "topic_collected"
    CONFIGURING = "configuring"
    SCRIPT_GENERATING = "script_generating"
    SCRIPT_GENERATED = "script_generated"
    VOICE_CONFIGURING = "voice_configuring"
    VOICE_CONFIGURED = "voice_configured"
    GENERATING_AUDIO = "generating_audio"
    AUDIO_GENERATED = "audio_generated"
    POST_PROCESSING = "post_processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ========== Sound ==========
@dataclass
class SoundEffect:
    effect_id: str
    name: str
    type: Literal["ambient", "effect", "music"]
    source_path: Optional[str] = None
    source_type: Literal["local", "builtin", "url"] = "local"
    volume: float = 1.0
    start_time: float = 0.0
    duration: Optional[float] = None
    fade_in: float = 0.0
    fade_out: float = 0.0


# ========== Voice ==========
@dataclass
class VoiceConfig:
    provider: str
    voice_id: str
    voice_type: Literal["male", "female", "child", "narrator"]
    language: str = "zh-CN"
    style: Optional[str] = None
    speed: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0


# ========== Character ==========
@dataclass
class Character:
    id: str
    name: str
    description: str
    voice_config: Optional[VoiceConfig] = None


# ========== Script ==========
@dataclass
class ScriptLine:
    line_id: str
    line_type: Literal["dialogue", "narration"]
    character_id: Optional[str] = None
    text: str = ""
    voice_config: Optional[VoiceConfig] = None
    audio_path: Optional[str] = None
    sound_effects: list[SoundEffect] = field(default_factory=list)
    background_music: Optional[SoundEffect] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Script:
    script_id: str
    title: str
    topic: str
    characters: list[Character] = field(default_factory=list)
    lines: list[ScriptLine] = field(default_factory=list)
    background_music: Optional[SoundEffect] = None
    sound_effects: list[SoundEffect] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


# ========== Project State ==========
@dataclass
class ProjectState:
    project_id: str
    state: Literal[
        "initialized", "topic_collected", "configuring",
        "script_generating", "script_generated",
        "voice_configuring", "voice_configured",
        "generating_audio", "audio_generated",
        "post_processing", "completed", "failed"
    ] = "initialized"
    script: Optional[Script] = None
    current_step: Optional[str] = None
    config: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
```

- [ ] **Step 8: 运行测试验证通过**

Run: `pytest tests/unit/test_exceptions.py tests/unit/test_models.py -v`
Expected: PASS

- [ ] **Step 9: 提交**

```bash
git add src/storyteller/core/exceptions.py src/storyteller/core/models.py tests/unit/test_exceptions.py tests/unit/test_models.py
git commit -m "feat: add core data models and exceptions"
```

---

## Task 3: 工具函数和配置管理

**Files:**
- Create: `src/storyteller/core/utils.py`
- Create: `src/storyteller/core/config.py`
- Test: `tests/unit/test_utils.py`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `utils.py`: `generate_id()`, `setup_logging()`
  - `config.py`: `Config` class with `get()`, `from_env()`

- [ ] **Step 1: 写测试 - utils**

```python
# tests/unit/test_utils.py
from storyteller.core.utils import generate_id

def test_generate_id_returns_string():
    gid = generate_id()
    assert isinstance(gid, str)
    assert len(gid) > 0

def test_generate_ids_are_unique():
    ids = {generate_id() for _ in range(100)}
    assert len(ids) == 100
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/unit/test_utils.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 utils.py**

```python
# src/storyteller/core/utils.py
import uuid
import logging


def generate_id(prefix: str = "") -> str:
    """Generate a unique ID."""
    uid = uuid.uuid4().hex[:12]
    return f"{prefix}{uid}" if prefix else uid


def setup_logging(level: str = "info") -> None:
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/unit/test_utils.py -v`
Expected: PASS

- [ ] **Step 5: 写测试 - config**

```python
# tests/unit/test_config.py
import os
import tempfile
from pathlib import Path
from storyteller.core.config import Config


def test_config_defaults():
    config = Config()
    assert config.log_level == "info"
    assert config.output_dir == "./outputs"


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("STORYTELLER_LOG_LEVEL", "debug")
    monkeypatch.setenv("STORYTELLER_LLM_DEFAULT_PROVIDER", "test-llm")
    config = Config.from_env()
    assert config.log_level == "debug"
    assert config.get("llm.default_provider") == "test-llm"


def test_config_get_nested():
    config = Config()
    config.set("a.b.c", "value")
    assert config.get("a.b.c") == "value"
    assert config.get("a.b.nonexistent", "default") == "default"
```

- [ ] **Step 6: 运行测试验证失败**

Run: `pytest tests/unit/test_config.py -v`
Expected: FAIL

- [ ] **Step 7: 实现 config.py**

```python
# src/storyteller/core/config.py
import os
from pathlib import Path
from typing import Any, Optional
from dotenv import load_dotenv

from .exceptions import ConfigError


class Config:
    """Configuration manager."""

    DEFAULTS = {
        "log_level": "info",
        "output_dir": "./outputs",
        "project_dir": "./projects",
        "output_format": "mp3",
        "progress_level": "simple",
        "strict_mode": False,
        "llm": {
            "providers": [],
            "default_provider": None,
        },
        "tts": {
            "providers": [],
            "default_provider": None,
        }
    }

    def __init__(self):
        self._config = self._deep_copy(self.DEFAULTS)

    def _deep_copy(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._deep_copy(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._deep_copy(v) for v in obj]
        return obj

    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> "Config":
        """Load config from environment variables."""
        if env_file and Path(env_file).exists():
            load_dotenv(env_file)
        else:
            load_dotenv()

        config = cls()

        # Global
        config.set("log_level", os.getenv("STORYTELLER_LOG_LEVEL", "info"))
        config.set("output_dir", os.getenv("STORYTELLER_OUTPUT_DIR", "./outputs"))
        config.set("project_dir", os.getenv("STORYTELLER_PROJECT_DIR", "./projects"))

        # LLM providers
        llm_providers_str = os.getenv("STORYTELLER_LLM_PROVIDERS", "")
        if llm_providers_str:
            llm_providers = [p.strip() for p in llm_providers_str.split(",") if p.strip()]
            config.set("llm.providers", llm_providers)

        config.set("llm.default_provider", os.getenv("STORYTELLER_LLM_DEFAULT_PROVIDER"))

        # TTS providers
        tts_providers_str = os.getenv("STORYTELLER_TTS_PROVIDERS", "")
        if tts_providers_str:
            tts_providers = [p.strip() for p in tts_providers_str.split(",") if p.strip()]
            config.set("tts.providers", tts_providers)

        config.set("tts.default_provider", os.getenv("STORYTELLER_TTS_DEFAULT_PROVIDER"))

        # Load provider-specific configs
        for provider in config.get("llm.providers", []):
            prefix = f"STORYTELLER_LLM_{provider.upper()}_"
            provider_config = {}
            for key in ["api_key", "model", "endpoint", "base_url"]:
                val = os.getenv(f"{prefix}{key.upper()}")
                if val:
                    provider_config[key] = val
            if provider_config:
                config.set(f"llm.provider_config.{provider}", provider_config)

        for provider in config.get("tts.providers", []):
            prefix = f"STORYTELLER_TTS_{provider.upper()}_"
            provider_config = {}
            for key in ["api_key", "endpoint", "base_url", "model"]:
                val = os.getenv(f"{prefix}{key.upper()}")
                if val:
                    provider_config[key] = val
            if provider_config:
                config.set(f"tts.provider_config.{provider}", provider_config)

        # OpenAI compatible providers (dynamic naming)
        for key, val in os.environ.items():
            if key.startswith("STORYTELLER_TTS_OPENAI_COMPATIBLE_") and key.endswith("_NAME"):
                suffix = key[len("STORYTELLER_TTS_OPENAI_COMPATIBLE_"):-len("_NAME")]
                provider_name = val
                provider_config = {"type": "openai_compatible"}
                for subkey in ["API_KEY", "BASE_URL", "MODEL"]:
                    env_key = f"STORYTELLER_TTS_OPENAI_COMPATIBLE_{suffix}_{subkey}"
                    env_val = os.getenv(env_key)
                    if env_val:
                        provider_config[subkey.lower()] = env_val
                tts_providers = config.get("tts.providers", [])
                if provider_name not in tts_providers:
                    tts_providers.append(provider_name)
                    config.set("tts.providers", tts_providers)
                config.set(f"tts.provider_config.{provider_name}", provider_config)

        return config

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot-separated key."""
        parts = key.split(".")
        cur = self._config
        for part in parts:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return default
        return cur

    def set(self, key: str, value: Any) -> None:
        """Set config value by dot-separated key."""
        parts = key.split(".")
        cur = self._config
        for part in parts[:-1]:
            if part not in cur:
                cur[part] = {}
            cur = cur[part]
        cur[parts[-1]] = value
```

- [ ] **Step 8: 运行测试验证通过**

Run: `pytest tests/unit/test_utils.py tests/unit/test_config.py -v`
Expected: PASS

- [ ] **Step 9: 提交**

```bash
git add src/storyteller/core/utils.py src/storyteller/core/config.py tests/unit/test_utils.py tests/unit/test_config.py
git commit -m "feat: add utils and config management"
```

---

## Task 4: Provider 基类和注册中心

**Files:**
- Create: `src/storyteller/core/llm.py`
- Create: `src/storyteller/core/tts.py`
- Create: `src/storyteller/core/audio.py`
- Create: `src/storyteller/providers/base.py`
- Create: `src/storyteller/providers/registry.py`
- Test: `tests/unit/test_providers.py`

**Interfaces:**
- Consumes: `exceptions.py`, `models.py`, `config.py`
- Produces:
  - `LLMProvider` abstract base class: `chat(messages, **kwargs) -> str`
  - `TTSProvider` abstract base class: `list_voices() -> list[VoiceConfig]`, `synthesize(text, voice_config, output_path, **kwargs) -> Path`
  - `AudioProcessor` abstract base class
  - `BaseProvider` base class
  - `ProviderRegistry`: `register_llm()`, `register_tts()`, `get_llm()`, `get_tts()`, `list_tts_voices()`

---

## Task 5: Mock Providers（测试用）

**Files:**
- Create: `src/storyteller/providers/mock/__init__.py`
- Create: `src/storyteller/providers/mock/llm.py`
- Create: `src/storyteller/providers/mock/tts.py`
- Test: `tests/unit/test_mock_providers.py`

**Interfaces:**
- Consumes: LLM/TTS abstract interfaces
- Produces: `MockLLMProvider`, `MockTTSProvider` - returns fixed test data

---

## Task 6: Project 状态管理

**Files:**
- Create: `src/storyteller/core/project.py`
- Test: `tests/unit/test_project.py`

**Interfaces:**
- Consumes: `models.py`, `utils.py`, `exceptions.py`
- Produces: `ProjectManager`: `create_project()`, `load_project()`, `save_project()`, `update_state()`

---

## Task 7: Story Generator（剧本生成）

**Files:**
- Create: `src/storyteller/core/story_generator.py`
- Test: `tests/unit/test_story_generator.py`

**Interfaces:**
- Consumes: `models.py`, `llm.py`, `utils.py`, `exceptions.py`
- Produces: `StoryGenerator`: `generate_script(topic, length, complexity, **kwargs) -> Script`

---

## Task 8: Voice Matcher（声音匹配）

**Files:**
- Create: `src/storyteller/core/voice_matcher.py`
- Test: `tests/unit/test_voice_matcher.py`

**Interfaces:**
- Consumes: `models.py`, `registry.py`
- Produces: `VoiceMatcher`: `match_voices(script, allowed_providers=None, allowed_voices=None) -> Script`

---

## Task 9: Volcengine Provider（火山引擎实现）

**Files:**
- Create: `src/storyteller/providers/volcengine/__init__.py`
- Create: `src/storyteller/providers/volcengine/llm.py`
- Create: `src/storyteller/providers/volcengine/tts.py`
- Test: `tests/integration/test_volcengine.py`（需要真实API Key时跳过）

**Interfaces:**
- Consumes: `base.py`, `llm.py`, `tts.py`, `config.py`
- Produces: `VolcengineLLM`, `VolcengineTTS`

---

## Task 10: OpenAI Compatible Provider

**Files:**
- Create: `src/storyteller/providers/openai_compatible/__init__.py`
- Create: `src/storyteller/providers/openai_compatible/llm.py`
- Create: `src/storyteller/providers/openai_compatible/tts.py`
- Test: `tests/unit/test_openai_compatible.py`

**Interfaces:**
- Consumes: `base.py`, `llm.py`, `tts.py`
- Produces: `OpenAICompatibleLLM`, `OpenAICompatibleTTS`

---

## Task 11: Audio Processor（pydub实现）

**Files:**
- Create: `src/storyteller/core/audio.py`
- Test: `tests/unit/test_audio.py`

**Interfaces:**
- Consumes: `models.py`, `exceptions.py`
- Produces: `PydubAudioProcessor`: `concatenate()`, `convert_format()`

---

## Task 12: Pipeline（流程编排）

**Files:**
- Create: `src/storyteller/core/pipeline.py`
- Test: `tests/unit/test_pipeline.py`

**Interfaces:**
- Consumes: All core components
- Produces: `Pipeline`: `run(topic, **options) -> Path`, `resume(project_id) -> Path`

---

## Task 13: CLI - 参数模式

**Files:**
- Create: `src/storyteller/cli/main.py`
- Test: `tests/e2e/test_cli.py`

**Interfaces:**
- Consumes: `pipeline.py`, `config.py`
- Produces: Click CLI entry point `storyteller generate`, `storyteller continue`, etc.

---

## Task 14: CLI - 交互式向导

**Files:**
- Create: `src/storyteller/cli/interactive.py`
- Modify: `src/storyteller/cli/main.py`
- Test: `tests/e2e/test_interactive.py`

**Interfaces:**
- Consumes: CLI components
- Produces: Interactive wizard flow

---

## Task 15: 端到端测试和文档

**Files:**
- Modify: `README.md`
- Create: `examples/`
- Test: `tests/e2e/test_full_flow.py`

**Interfaces:**
- Produces: Complete working MVP with documentation

---

## 执行顺序说明

任务依赖关系：
```
1 (初始化) → 2 (models/exceptions) → 3 (utils/config)
                                          ↓
                                    4 (Provider抽象)
                                    ↙        ↘
                            5 (Mock)         9 (Volcengine)
                            ↓                10 (OpenAI compat)
                            6 (Project)
                            ↓
                            7 (StoryGenerator)
                            ↓
                            8 (VoiceMatcher)
                            ↓
                            11 (AudioProcessor)
                            ↓
                            12 (Pipeline)
                            ↓
                            13 (CLI参数) → 14 (CLI交互)
                                          ↓
                                          15 (E2E + 文档)
```

---

*注：本计划提供了完整的任务框架和结构。在执行每个任务时，需要按照TDD方式补充完整的测试代码和实现代码。每个任务保持2-5分钟一步的小颗粒度，每个任务结束都有可测试的交付物。*
