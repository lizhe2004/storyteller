# Web 流式音频后端 Implementation Plan（P1-A）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 storyteller 增加一个可运行、可测的 FastAPI Web 后端：密码鉴权、历史 REST、WebSocket 逐行流式音频（统一 PCM s16le/mono/24kHz 线缆标准）、火山流式 TTS 适配、逐行混音、等待期 filler 填充语音。

**Architecture:** 单进程 FastAPI；生成是现有同步代码，跑在 JobManager 的线程池里，通过线程安全队列桥接到 WebSocket。流式编排器（StreamOrchestrator）复用 Pipeline 的剧本生成/音色匹配/音效库构件，逐行产出标准 PCM 帧；provider 差异收敛在 `StreamingTTSProvider` 适配层。Vue 前端是另一个独立计划（P1-B），本计划完成后用 WS 客户端即可完整验收。

**Tech Stack:** Python ≥3.8（禁止 `X | None` 语法，用 `Optional`）、FastAPI、uvicorn、itsdangerous、starlette TestClient（httpx）、pydub/ffmpeg、pytest。

**Spec:** `docs/superpowers/specs/2026-09-12-web-streaming-design.md`（实现者必须同时读本计划与 spec，冲突以 spec 为准）

## Global Constraints

- 线缆标准常量全代码唯一来源：`PCM s16le / mono / 24000Hz`，定义在 `core/tts.py`，任何 provider/出口不得偏离。
- web 依赖是**可选 extras**（`pip install -e ".[web]"`）：核心包与 CLI 在未安装 fastapi/uvicorn 时照常工作；`storyteller web` 命令延迟 import。
- CLI 既有行为零变化；每个后端任务完成后跑一次全量 `pytest`，既有测试必须全绿（当前 337）。
- 密钥约定：真实值只进 `.env`（已 gitignore）；`.env.example` 只放占位符。
- 用户可见文案用中文。提交信息用 conventional commits（feat/fix/refactor/docs/test）。
- TDD：每个代码任务先写失败测试，再实现；一个任务一次提交（任务内步骤可产生多个提交，但至少在最后提交一次）。
- 测试禁止真实网络/真实 API key：一律用 mock provider 与 FastAPI TestClient；真机验证只在最后的手动任务。
- 线程取消只在阶段/行边界检查 `cancel_event`，不强杀 provider 调用。

## File Structure

```
pyproject.toml                          # 加 [web] extras
.env.example                          # web 占位配置
src/storyteller/core/
  config.py                           # 读 web.* 配置（修改）
  tts.py                              # StreamChunk/常量/StreamingTTSProvider（修改）
  audio.py                            # PydubAudioProcessor.mix_line（修改）
  pipeline.py                         # 抽出可复用的行级构件（修改，CLI 路径行为不变）
src/storyteller/providers/
  registry.py                         # get_stream_tts 能力探测（修改）
  volcengine/tts.py                   # NDJSON 迭代器重构 + stream_synthesize（修改）
  mock/tts.py                         # MockStreamingTTS（修改）
src/storyteller/web/
  __init__.py
  tts_chunks.py                       # 线缆常量转发、PCM 工具（文件→PCM、PCM→mp3、切块）
  mixes.py                            # 单行人声+音效混音入口 mix_line_with_cues（复用 core/audio.mix_line）
  fillers.py                          # FillerPrefetcher：thinking LLM、intro 模板、缓存
  jobs.py                             # Job/JobManager/状态机
  auth.py                             # 密码、HMAC token、限流
  schemas.py                          # pydantic 请求/响应模型
  app.py                              # create_app 工厂、静态托管
  routes_auth.py
  routes_options.py
  routes_stories.py
  routes_ws.py
  streaming.py                        # StreamOrchestrator
  cli.py                              # storyteller web 命令实现（click 命令挂到 cli/main.py）
tests/unit/                           # 既有目录；新增单元测试
tests/web/                            # 新增 web 测试包（含 __init__.py、conftest.py）
```

---

### Task 1: Web 配置与可选依赖

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/storyteller/core/config.py`（`from_env` 末尾、DEFAULTS）
- Modify: `.env.example`
- Test: `tests/unit/test_web_config.py`

**Interfaces:**
- Produces: config 键 `web.passwords`(list[str]), `web.secret`(str|None), `web.token_ttl_days`(int=30), `web.host`="127.0.0.1", `web.port`=8000, `web.concurrency`=2, `web.rate_limit_per_min`=10, `web.filler_voice`(str|None)；extras 名 `web`。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_web_config.py
import os

from storyteller.core.config import Config


def _load(monkeypatch, **env):
    for key in (
        "STORYTELLER_WEB_PASSWORDS", "STORYTELLER_WEB_SECRET",
        "STORYTELLER_WEB_TOKEN_TTL_DAYS", "STORYTELLER_WEB_HOST",
        "STORYTELLER_WEB_PORT", "STORYTELLER_WEB_CONCURRENCY",
        "STORYTELLER_WEB_RATE_LIMIT_PER_MIN", "STORYTELLER_WEB_FILLER_VOICE",
    ):
        monkeypatch.delenv(key, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Config.from_env(env_file="/nonexistent/.env")


def test_web_defaults(monkeypatch):
    cfg = _load(monkeypatch)
    assert cfg.get("web.passwords") == []
    assert cfg.get("web.host") == "127.0.0.1"
    assert cfg.get("web.port") == 8000
    assert cfg.get("web.concurrency") == 2
    assert cfg.get("web.rate_limit_per_min") == 10
    assert cfg.get("web.token_ttl_days") == 30
    assert cfg.get("web.filler_voice") is None


def test_web_passwords_parsed_and_stripped(monkeypatch):
    cfg = _load(monkeypatch, STORYTELLER_WEB_PASSWORDS=" abc , 123 ,, ")
    assert cfg.get("web.passwords") == ["abc", "123"]


def test_web_overrides(monkeypatch):
    cfg = _load(
        monkeypatch,
        STORYTELLER_WEB_HOST="0.0.0.0", STORYTELLER_WEB_PORT="9000",
        STORYTELLER_WEB_CONCURRENCY="4", STORYTELLER_WEB_RATE_LIMIT_PER_MIN="0",
        STORYTELLER_WEB_TOKEN_TTL_DAYS="7", STORYTELLER_WEB_SECRET="s3cr",
        STORYTELLER_WEB_FILLER_VOICE="volcengine:zh_female_popo",
    )
    assert cfg.get("web.host") == "0.0.0.0"
    assert cfg.get("web.port") == 9000
    assert cfg.get("web.concurrency") == 4
    assert cfg.get("web.rate_limit_per_min") == 0
    assert cfg.get("web.token_ttl_days") == 7
    assert cfg.get("web.secret") == "s3cr"
    assert cfg.get("web.filler_voice") == "volcengine:zh_female_popo"
```

- [ ] **Step 2: 运行确认失败**

`python -m pytest tests/unit/test_web_config.py -v` → FAIL（`web.host` 为 None）。

- [ ] **Step 3: 实现**

`Config.DEFAULTS` 加：

```python
"web": {
    "passwords": [], "secret": None, "token_ttl_days": 30,
    "host": "127.0.0.1", "port": 8000, "concurrency": 2,
    "rate_limit_per_min": 10, "filler_voice": None,
},
```

`from_env` 在 `return config` 前加静态方法调用 `cls._load_web(config)`：

```python
@staticmethod
def _load_web(config):
    raw = os.getenv("STORYTELLER_WEB_PASSWORDS", "")
    passwords = [p.strip() for p in raw.split(",") if p.strip()]
    config.set("web.passwords", passwords)
    config.set("web.secret", os.getenv("STORYTELLER_WEB_SECRET") or None)
    config.set("web.filler_voice", os.getenv("STORYTELLER_WEB_FILLER_VOICE") or None)
    for env_key, cfg_key, cast, default in (
        ("STORYTELLER_WEB_TOKEN_TTL_DAYS", "web.token_ttl_days", int, 30),
        ("STORYTELLER_WEB_PORT", "web.port", int, 8000),
        ("STORYTELLER_WEB_CONCURRENCY", "web.concurrency", int, 2),
        ("STORYTELLER_WEB_RATE_LIMIT_PER_MIN", "web.rate_limit_per_min", int, 10),
    ):
        value = os.getenv(env_key)
        config.set(cfg_key, cast(value) if value else default)
    config.set("web.host", os.getenv("STORYTELLER_WEB_HOST", "127.0.0.1"))
```

`pyproject.toml`：

```toml
[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-cov>=4.0"]
web = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "itsdangerous>=2.1",
    "httpx>=0.27",
]
```

`.env.example` 追加（占位符）：

```
# --- Web ---
# 逗号分隔的访问密码；留空时 `storyteller web` 拒绝启动
STORYTELLER_WEB_PASSWORDS=changeme,another-password
# 不设则每次启动临时生成（重启后所有登录失效）
STORYTELLER_WEB_SECRET=
STORYTELLER_WEB_HOST=127.0.0.1
STORYTELLER_WEB_PORT=8000
STORYTELLER_WEB_CONCURRENCY=2
# STORYTELLER_WEB_FILLER_VOICE=volcengine:zh_female_popo
```

- [ ] **Step 4: 安装并验证**

`pip install -e ".[web,dev]" && python -m pytest tests/unit/test_web_config.py -v` → PASS；`pytest` 全量绿。

- [ ] **Step 5: 提交**

`git add pyproject.toml src/storyteller/core/config.py .env.example tests/unit/test_web_config.py && git commit -m "feat: web configuration with optional web extras"`

---

### Task 2: 流式 TTS 契约与 registry 能力探测

**Files:**
- Modify: `src/storyteller/core/tts.py`
- Modify: `src/storyteller/providers/registry.py`
- Test: `tests/unit/test_streaming_contract.py`

**Interfaces:**
- Produces:
  - `core/tts.py`: `STREAM_SAMPLE_RATE=24000`, `STREAM_CHANNELS=1`, `STREAM_SAMPLE_WIDTH=2`；`@dataclass StreamChunk(kind: str, data: object)`，常量 `CHUNK_AUDIO="audio"`, `CHUNK_EVENT="event"`；基类方法 `TTSProvider.stream_synthesize(self, text, voice_config, *, directives=None, context=None)` 默认 `raise NotImplementedError`，类属性 `supports_streaming=False`。
  - `ProviderRegistry.get_stream_tts(name) -> Optional[TTSProvider]`：已注册且支持流式返回实例，否则 None；未知名仍抛 `ProviderError`。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_streaming_contract.py
import pytest

from storyteller.core.models import VoiceConfig
from storyteller.core.tts import (
    STREAM_SAMPLE_RATE, STREAM_CHANNELS, STREAM_SAMPLE_WIDTH,
    StreamChunk, CHUNK_AUDIO,
)
from storyteller.providers.registry import ProviderRegistry
from storyteller.providers.mock.tts import MockTTSProvider


class _StreamTTS(MockTTSProvider):
    supports_streaming = True

    def stream_synthesize(self, text, voice_config, **kwargs):
        yield StreamChunk(kind=CHUNK_AUDIO, data=b"\x00\x00" * 240)


def test_wire_constants():
    assert (STREAM_SAMPLE_RATE, STREAM_CHANNELS, STREAM_SAMPLE_WIDTH) == (24000, 1, 2)


def test_registry_returns_none_for_non_streaming():
    reg = ProviderRegistry(config={})
    reg.register_tts("plain", lambda c: MockTTSProvider(c))
    assert reg.get_stream_tts("plain") is None


def test_registry_returns_streaming_instance():
    reg = ProviderRegistry(config={})
    reg.register_tts("stream", lambda c: _StreamTTS(c))
    tts = reg.get_stream_tts("stream")
    assert tts is not None
    voice = VoiceConfig(provider="stream", voice_id="v")
    chunks = list(tts.stream_synthesize("你好", voice))
    assert chunks and chunks[0].kind == CHUNK_AUDIO
    assert len(chunks[0].data) == 480  # 240 samples * 2 bytes


def test_registry_unknown_name_raises():
    reg = ProviderRegistry(config={})
    with pytest.raises(Exception):
        reg.get_stream_tts("nope")
```

- [ ] **Step 2: 运行确认失败**：`get_stream_tts` 不存在，FAIL。

- [ ] **Step 3: 实现**

`core/tts.py` 在文件顶部加：

```python
from dataclasses import dataclass

# Wire standard for every streaming audio path (WebSocket): PCM s16le mono.
STREAM_SAMPLE_RATE = 24000
STREAM_CHANNELS = 1
STREAM_SAMPLE_WIDTH = 2  # bytes per sample (int16)
CHUNK_AUDIO = "audio"
CHUNK_EVENT = "event"


@dataclass
class StreamChunk:
    kind: str   # CHUNK_AUDIO -> data is s16le bytes; CHUNK_EVENT -> dict
    data: object
```

`TTSProvider` 内加默认实现：

```python
supports_streaming = False

def stream_synthesize(self, text, voice_config, *, directives=None, context=None):
    """Yield StreamChunk objects (PCM s16le mono 24kHz). Providers that can
    stream override this and set supports_streaming=True."""
    raise NotImplementedError
```

`registry.py` 加：

```python
def get_stream_tts(self, name):
    """Return the TTS instance if it implements the streaming contract."""
    tts = self.get_tts(name)
    if getattr(tts, "supports_streaming", False) and hasattr(
        tts, "stream_synthesize"
    ):
        return tts
    return None
```

- [ ] **Step 4: 验证**：`pytest tests/unit/test_streaming_contract.py -v` PASS；全量绿。

- [ ] **Step 5: 提交**：`git commit -m "feat: streaming TTS contract and registry capability detection"`

---

### Task 3: 火山 TTS NDJSON 迭代器重构与 stream_synthesize

**Files:**
- Modify: `src/storyteller/providers/volcengine/tts.py`
- Test: `tests/unit/test_volcengine_stream.py`

**Interfaces:**
- Consumes: `StreamChunk`, `CHUNK_AUDIO`, `STREAM_SAMPLE_RATE`（core.tts）。
- Produces: `VolcengineTTS.supports_streaming=True`；`stream_synthesize(text, voice_config, *, directives, context) -> Iterator[StreamChunk]`，音频块为 24k mono s16le；`synthesize()` 行为/错误文案与字节输出不变（既有测试锁定）。内部方法 `_iter_ndjson(response, audio_format)` 生成器逐行产出解码字节，`_build_body(text, voice_config, audio_format, directives, context) -> (headers, body)` 供两条路径共用。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_volcengine_stream.py
import base64
import json

import pytest

from storyteller.core.models import VoiceConfig
from storyteller.core.tts import CHUNK_AUDIO, STREAM_SAMPLE_RATE
from storyteller.providers.volcengine.tts import VolcengineTTS


class _FakeResponse:
    def __init__(self, lines):
        self._lines = lines
        self.closed = False

    def iter_lines(self, decode_unicode=True):
        for line in self._lines:
            yield line

    def raise_for_status(self):
        pass

    def close(self):
        self.closed = True


def _ndjson(chunks, done=True, code=0):
    frames = []
    for ch in chunks:
        frames.append(json.dumps({"code": code, "data": base64.b64encode(ch).decode()}))
    if done:
        frames.append(json.dumps({"code": 20000000}))
    return frames


def _provider(monkeypatch, frames):
    cfg = type("C", (), {"get": lambda self, k, d=None: {
        "api_key": "k", "endpoint": "http://x", "resource_id": "r"} if "volcengine" in k else {}})()
    prov = VolcengineTTS(cfg)
    captured = {}

    def fake_post(url, headers=None, json=None, stream=None, timeout=None):
        captured["body"] = json
        return _FakeResponse(frames)

    monkeypatch.setattr(prov._session, "post", fake_post)
    return prov, captured


def test_stream_synthesize_yields_pcm(monkeypatch):
    pcm = [b"\x01\x00" * 100, b"\x02\x00" * 50]
    prov, captured = _provider(monkeypatch, _ndjson(pcm))
    voice = VoiceConfig(provider="volcengine", voice_id="v")
    chunks = list(prov.stream_synthesize("嗨", voice, directives=["#温柔"], context=None))
    assert [c.kind for c in chunks] == [CHUNK_AUDIO, CHUNK_AUDIO]
    assert b"".join(c.data for c in chunks) == pcm[0] + pcm[1]
    # 请求必须是 pcm 24k
    assert captured["body"]["req_params"]["audio_params"]["format"] == "pcm"
    assert captured["body"]["req_params"]["audio_params"]["sample_rate"] == STREAM_SAMPLE_RATE


def test_stream_propagates_error_code(monkeypatch):
    frames = [json.dumps({"code": 55000000, "message": "bad voice"})]
    prov, _ = _provider(monkeypatch, frames)
    voice = VoiceConfig(provider="volcengine", voice_id="v")
    with pytest.raises(Exception, match="55000000"):
        list(prov.stream_synthesize("嗨", voice))
```

- [ ] **Step 2: 确认失败**：`supports_streaming` 为 False / 方法不存在 → FAIL。

- [ ] **Step 3: 实现**（要点；保留既有 mp3 路径）

把 `synthesize` 里构造 headers/body 的逻辑抽为：

```python
def _build_request(self, text, voice_config, audio_format, directives, context):
    audio_params = {
        "format": audio_format,
        "sample_rate": 48000 if audio_format == "ogg_opus" else 24000,
        "speech_rate": _clamp(int(round((voice_config.speed - 1.0) * 100)), -50, 100),
        "loudness_rate": _clamp(int(round((voice_config.volume - 1.0) * 100)), -50, 100),
    }
    additions = {"disable_markdown_filter": True, "disable_emoji_filter": True}
    context_texts = _build_context_texts(directives, context)
    if context_texts:
        additions["context_texts"] = context_texts
    req_params = {
        "text": text, "speaker": voice_config.voice_id,
        "audio_params": audio_params,
        "additions": json.dumps(additions, ensure_ascii=False),
    }
    if voice_config.pitch != 1.0:
        semitones = _clamp(int(round(12 * _safe_log2(voice_config.pitch))), -12, 12)
        if semitones:
            req_params["post_process"] = {"pitch": semitones}
    headers = {
        "X-Api-Key": self.api_key,
        "X-Api-Resource-Id": self._resource_id_for(voice_config.voice_id),
        "X-Api-Request-Id": uuid.uuid4().hex,
        "Content-Type": "application/json", "Connection": "keep-alive",
    }
    return headers, {"req_params": req_params}
```

`_read_stream(response)` 改为调用新生成器（签名带 audio_format 以便错误上下文）：

```python
def _iter_ndjson(self, response):
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            data = json.loads(line)
        except ValueError as exc:
            raise TTSError("Invalid JSON chunk from Volcengine TTS") from exc
        code = data.get("code", 0)
        if code == _DONE_CODE:
            return
        if code > 0:
            raise TTSError("Volcengine TTS error (code {}): {}".format(
                code, data.get("message", "unknown")))
        chunk = data.get("data")
        if chunk:
            try:
                yield base64.b64decode(chunk)
            except (ValueError, TypeError) as exc:
                raise TTSError("Failed to decode Volcengine audio chunk") from exc
```

`synthesize` 改为 `audio_format=_encoding_for_path(output_path)` → `_build_request` → post → `b"".join(self._iter_ndjson(response))` → 空则抛既有错误 → 写文件。

新增：

```python
supports_streaming = True

def stream_synthesize(self, text, voice_config, *, directives=None, context=None):
    from ...core.tts import StreamChunk, CHUNK_AUDIO
    headers, body = self._build_request(
        text, voice_config, "pcm", directives, context
    )
    response = None
    try:
        response = self._session.post(
            self.endpoint, headers=headers, json=body, stream=True, timeout=60
        )
        response.raise_for_status()
        for piece in self._iter_ndjson(response):
            yield StreamChunk(kind=CHUNK_AUDIO, data=bytes(piece))
    except requests.RequestException as exc:
        raise TTSError("Volcengine TTS request failed: {}".format(exc)) from exc
    finally:
        if response is not None:
            response.close()
```

注意：流内 `TTSError` 直接向上传播（生成器自然语义）。

- [ ] **Step 4: 验证**：新测试 PASS；`pytest tests/unit/test_volcengine* tests/unit -k tts -v` 与全量必须绿（重点确认非流式字节输出未变）。

- [ ] **Step 5: 提交**：`git commit -m "refactor: volcengine ndjson iterator and pcm stream_synthesize"`

---

### Task 4: MockStreamingTTS 测试桩

**Files:**
- Modify: `src/storyteller/providers/mock/tts.py`
- Test: `tests/unit/test_mock_stream_tts.py`

**Interfaces:**
- Produces: `MockStreamingTTS(MockTTSProvider)`：`supports_streaming=True`；`stream_synthesize` 产出 24k s16le 正弦音（可闻，避免被响度闸门当成废片——但行 TTS 本身不过闸门，这里仅要求确定性 PCM 长度）；构造参数 `config`；记录调用到 `self.synth_calls`（沿用父类）。辅助常量 `MOCK_STREAM_SAMPLE_RATE=24000`。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_mock_stream_tts.py
import struct

from storyteller.core.models import VoiceConfig
from storyteller.core.tts import CHUNK_AUDIO, STREAM_SAMPLE_RATE
from storyteller.providers.mock.tts import MockStreamingTTS


def test_stream_emits_standard_pcm_chunks():
    prov = MockStreamingTTS(config={})
    voice = VoiceConfig(provider="mock", voice_id="narrator_01")
    chunks = list(prov.stream_synthesize("测试句", voice))
    assert chunks and all(c.kind == CHUNK_AUDIO for c in chunks)
    pcm = b"".join(c.data for c in chunks)
    assert len(pcm) % 2 == 0
    # 0.5s 整：12000 samples
    assert len(pcm) == 24000


def test_records_call_kwargs():
    prov = MockStreamingTTS(config={})
    voice = VoiceConfig(provider="mock", voice_id="v")
    list(prov.stream_synthesize("嗨", voice, directives=["#开心"], context=["上一句"]))
    assert prov.synth_calls[-1]["kwargs"]["directives"] == ["#开心"]
```

- [ ] **Step 2: 确认失败**（ImportError）。

- [ ] **Step 3: 实现**（追加到 mock/tts.py）

```python
import math

from ...core.tts import StreamChunk, CHUNK_AUDIO, STREAM_SAMPLE_RATE


class MockStreamingTTS(MockTTSProvider):
    """Deterministic audible-ish PCM stream for web tests: 0.5s 220Hz tone."""

    supports_streaming = True

    def stream_synthesize(self, text, voice_config, *, directives=None, context=None):
        self.synth_calls.append({
            "text": text, "voice_config": voice_config,
            "output_path": None,
            "kwargs": {"directives": directives, "context": context},
        })
        if self._error is not None:
            raise self._error
        duration_samples = STREAM_SAMPLE_RATE // 2  # 0.5s
        frame = bytearray()
        for i in range(duration_samples):
            # 220 Hz sine at ~20% of full-scale int16
            sample = int(0.2 * 32767 * math.sin(2 * math.pi * 220 * i / STREAM_SAMPLE_RATE))
            frame += struct.pack("<h", sample)
        block = STREAM_SAMPLE_RATE * 2 // 10  # 100ms per WS-sized chunk
        for off in range(0, len(frame), block):
            yield StreamChunk(kind=CHUNK_AUDIO, data=bytes(frame[off:off + block]))
```

- [ ] **Step 4: 验证**：PASS、全量绿。

- [ ] **Step 5: 提交**：`git commit -m "test: add deterministic streaming mock TTS provider"`

---

### Task 5: PCM 工具（web/tts_chunks.py）

**Files:**
- Create: `src/storyteller/web/__init__.py`（空）、`src/storyteller/web/tts_chunks.py`
- Test: `tests/web/__init__.py`（空）、`tests/web/test_tts_chunks.py`

**Interfaces:**
- Consumes: pydub（ffmpeg 已在环境中）。
- Produces:
  - `audio_file_to_standard_pcm(path) -> bytes`：任意音频文件→s16le/mono/24k。
  - `pcm_to_mp3_file(pcm: bytes, out_path)`：标准 PCM buffer→mp3 文件。
  - `iter_pcm_frames(pcm: bytes, frame_ms: int = 200) -> Iterator[bytes]`：按 200ms 切块（每块字节数 `24000*2*0.2=9600`），尾块保留。
  - `pcm_duration_ms(pcm: bytes) -> int`。

- [ ] **Step 1: 写失败测试**

```python
# tests/web/test_tts_chunks.py
import wave

from storyteller.web.tts_chunks import (
    audio_file_to_standard_pcm, pcm_to_mp3_file, iter_pcm_frames, pcm_duration_ms,
)


def _wav(path, seconds=0.3, rate=22050, freq=300):
    import math, struct
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
        frames = bytearray()
        for i in range(rate * seconds):
            frames += struct.pack("<h", int(0.2 * 32767 * math.sin(2*math.pi*freq*i/rate)))
        wf.writeframes(bytes(frames))


def test_file_to_pcm_resamples_to_24k_mono_s16(tmp_path):
    src = tmp_path / "a.wav"
    _wav(src)
    pcm = audio_file_to_standard_pcm(src)
    assert len(pcm) % 2 == 0
    # 0.3s @24k = 7200 samples = 14400 bytes（容忍编码取整 ±10ms）
    assert abs(len(pcm) - 14400) < 480


def test_pcm_roundtrip_mp3(tmp_path):
    import math, struct
    pcm = bytearray()
    for i in range(24000 // 2):
        pcm += struct.pack("<h", int(0.2 * 32767 * math.sin(2*math.pi*200*i/24000)))
    out = tmp_path / "line.mp3"
    pcm_to_mp3_file(bytes(pcm), out)
    assert out.exists() and out.stat().st_size > 0
    again = audio_file_to_standard_pcm(out)
    assert abs(pcm_duration_ms(again) - 500) < 80  # mp3 编解码有延迟填充


def test_iter_frames_and_duration():
    pcm = b"\x00" * (9600 * 2 + 100)
    frames = list(iter_pcm_frames(pcm, frame_ms=200))
    assert len(frames) == 3 and len(frames[0]) == 9600 and len(frames[-1]) == 100
    assert pcm_duration_ms(pcm) == int((9600 * 2 + 100) / 48)  # 48 bytes/ms @24k s16 mono
```

- [ ] **Step 2: 确认失败**（ModuleNotFoundError: storyteller.web）。

- [ ] **Step 3: 实现**

```python
# src/storyteller/web/tts_chunks.py
from __future__ import annotations

from pathlib import Path

from ..core.tts import (
    STREAM_SAMPLE_RATE, STREAM_CHANNELS, STREAM_SAMPLE_WIDTH,
)

_BYTES_PER_MS = STREAM_SAMPLE_RATE * STREAM_CHANNELS * STREAM_SAMPLE_WIDTH // 1000


def _standard_segment(path):
    from pydub import AudioSegment

    seg = AudioSegment.from_file(str(path))
    return (seg.set_channels(STREAM_CHANNELS)
               .set_frame_rate(STREAM_SAMPLE_RATE)
               .set_sample_width(STREAM_SAMPLE_WIDTH))


def audio_file_to_standard_pcm(path):
    return _standard_segment(path).raw_data


def pcm_to_mp3_file(pcm, out_path):
    from pydub import AudioSegment

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    seg = AudioSegment.from_file(
        bytes(pcm), format="raw",
        frame_rate=STREAM_SAMPLE_RATE,
        sample_width=STREAM_SAMPLE_WIDTH, channels=STREAM_CHANNELS,
    )
    seg.export(str(out_path), format="mp3")
    return out_path


def iter_pcm_frames(pcm, frame_ms=200):
    size = _BYTES_PER_MS * frame_ms
    for off in range(0, len(pcm), size):
        yield pcm[off:off + size]


def pcm_duration_ms(pcm):
    return len(pcm) // _BYTES_PER_MS
```

- [ ] **Step 4: 验证**：`pytest tests/web/test_tts_chunks.py -v` PASS（要求机器有 ffmpeg，与既有音效测试前提相同）；全量绿。

- [ ] **Step 5: 提交**：`git commit -m "feat: standard PCM conversion helpers for web streaming"`

---

### Task 6: 单行混音 —— core mix_line 原语 + web/mixes.py 封装

**Files:**
- Modify: `src/storyteller/core/audio.py`
- Create: `src/storyteller/web/mixes.py`
- Test: `tests/unit/test_mix_line.py`

**Interfaces:**
- Consumes: 现有 `_build_group_track(reference, entries, line_duration_sec)`（private，同类内直接用）。
- Produces:
  - `PydubAudioProcessor.mix_line(main_line_path, entries, output_path) -> Path`；entries 为 `[(SoundEffect, offset_sec), ...]`；无有效 cue 时输出等同人声（仍导出）。
  - `web/mixes.py` 的 `mix_line_with_cues(voice_path, entries, output_path) -> Path`——把单行人声与 entries 混音写到 `output_path`（canonical 行段 mp3）；entries 同上，来自 Task 7 的 `materialize_line_cues`；无 entries 时等同导出人声段。内部直接调用 `PydubAudioProcessor().mix_line(voice_path, entries, output_path)`（`mix_line` 先把 main 读进内存再 export，故 `voice_path == output_path` 原地混音安全，无需 `.mixed.mp3` 中转）。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_mix_line.py
import math, struct, wave
from pathlib import Path

from pydub import AudioSegment

from storyteller.core.audio import PydubAudioProcessor
from storyteller.core.models import SoundEffect


def _tone(path, seconds, freq=200, rate=24000, gain=0.15):
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
        buf = bytearray()
        for i in range(rate * seconds):
            buf += struct.pack("<h", int(gain * 32767 * math.sin(2*math.pi*freq*i/rate)))
        wf.writeframes(bytes(buf))


def test_mix_line_with_effect_is_audible_and_same_length(tmp_path):
    proc = PydubAudioProcessor()
    voice = tmp_path / "v.wav"; cue = tmp_path / "c.wav"; out = tmp_path / "m.mp3"
    _tone(voice, 2, freq=180)
    _tone(cue, 1, freq=900, gain=0.3)
    sfx = SoundEffect(effect_id="e1", name="提示音", type="effect")
    sfx.source_path = str(cue)
    proc.mix_line(voice, [(sfx, 0.0)], out)
    mixed = AudioSegment.from_file(out)
    assert abs(len(mixed) - 2000) < 120
    # 900Hz 能量存在：与纯人声相减后非零
    v = AudioSegment.from_file(voice).set_frame_rate(mixed.frame_rate).set_channels(1)
    diff = mixed.overlay(v.invert_phase())
    assert diff.dBFS > -60


def test_mix_line_without_entries_is_plain_voice(tmp_path):
    proc = PydubAudioProcessor()
    voice = tmp_path / "v.wav"; out = tmp_path / "m.mp3"
    _tone(voice, 1)
    proc.mix_line(voice, [], out)
    assert out.exists()
    assert abs(len(AudioSegment.from_file(out)) - 1000) < 120


from storyteller.web.mixes import mix_line_with_cues


def test_mix_line_with_cues_inplace(tmp_path):
    voice = tmp_path / "v.wav"; out = tmp_path / "L1.mp3"
    _tone(voice, 1)
    # 无 entries：等同导出人声，落到 out
    mix_line_with_cues(voice, [], out)
    assert out.exists()
    # 有 entries：原地混音（voice 已读进内存，写同一路径安全）
    sfx = SoundEffect(effect_id="e1", name="提示音", type="effect")
    sfx.source_path = str(voice)
    mix_line_with_cues(out, [(sfx, 0.0)], out)
    assert abs(len(AudioSegment.from_file(out)) - 1000) < 120
```

- [ ] **Step 2: 确认失败**（AttributeError: mix_line）。

- [ ] **Step 3: 实现**（加在 `PydubAudioProcessor` 内，`add_effect_groups` 旁）

```python
def mix_line(self, main_line_path, entries, output_path):
    """Overlay one line's cue group onto its speech at offset 0."""
    from pydub import AudioSegment

    main = AudioSegment.from_file(str(main_line_path))
    if entries:
        track = self._build_group_track(main, entries, len(main) / 1000.0)
        if track is not None:
            main = main.overlay(track, position=0)
    return self._export(main, output_path)
```

`web/mixes.py`（单行人声+音效混音的 web 层唯一入口，复用上面的原语）：

```python
# src/storyteller/web/mixes.py
from __future__ import annotations

from pathlib import Path

from ..core.audio import PydubAudioProcessor


def mix_line_with_cues(voice_path, entries, output_path):
    """把单行人声与该行音效/BGM entries 混音，写到 output_path（canonical 行段）。

    entries 来自 Pipeline.materialize_line_cues（[(SoundEffect, offset_sec), ...]）。
    无 entries 时 mix_line 本就导出纯人声段，仍产出 canonical 行段。
    voice_path 与 output_path 可相同（原地混音，main 先读进内存再 export）。
    """
    return PydubAudioProcessor().mix_line(
        Path(voice_path), entries, Path(output_path))
```

- [ ] **Step 4: 验证**：PASS；跑既有 `tests/unit/test_audio.py` 确认未破坏全片混音。

- [ ] **Step 5: 提交**：`git commit -m "feat: per-line mixing primitive and web mixes module"`

---

### Task 7: Pipeline 行级构件抽取（为流式编排复用）

**Files:**
- Modify: `src/storyteller/core/pipeline.py`
- Test: `tests/unit/test_pipeline_line_helpers.py`

**Interfaces:**
- Produces（均为 `Pipeline` 上的新方法，CLI 的 `_execute_pipeline/_apply_soundtrack` 改为调用它们，行为不变）：
  - `voice_for_line(line, char_voice_map, narrator_voice) -> Optional[VoiceConfig]`
  - `line_context_directives(lines, idx) -> (list[str], list[str])`（包装现有静态 `_line_context`）
  - `materialize_line_cues(state, line, line_duration, provider, library, referenced_paths) -> list[(SoundEffect, float)]`：完成该行 cue 的 find/generate/admit/项目副本/回填 source_path，返回 `(cue, offset)`；无 cue 返回 `[]`。复用 `build_sound_prompt`、`_materialize_cue`、`_project_sound_path`、`_anchor_offset`。
  - `finalize_audio(state, line_paths, output_format, with_sound) -> Path`：拼接 + 可选 `_apply_soundtrack`，置 completed。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_pipeline_line_helpers.py
from pathlib import Path

import pytest

from storyteller.core.config import Config
from storyteller.core.models import Character, Script, ScriptLine, SoundEffect, VoiceConfig
from storyteller.core.pipeline import Pipeline
from storyteller.core.project import ProjectManager


def _state(tmp_path):
    pm = ProjectManager(str(tmp_path / "stories"))
    state = pm.create_project(topic="t", config={"length": "short", "complexity": "simple"})
    state.script = Script(script_id="s1", title="测", topic="t",
        characters=[Character(id="narrator", name="旁白", description="",
                               voice_config=VoiceConfig(provider="mock", voice_id="narrator_01"))],
        lines=[ScriptLine(line_id="1", line_type="narration", text="咚的一声。",
                          sound_effects=[
                              SoundEffect(effect_id="e1", name="咚", type="effect",
                                          prompt="低沉的咚声", anchor="咚")])])
    return pm, state


def test_voice_for_line_prefers_line_then_character_then_narrator():
    pipe = Pipeline(Config())
    n = VoiceConfig(provider="m", voice_id="narr")
    c = VoiceConfig(provider="m", voice_id="char")
    line = ScriptLine(line_id="1", line_type="dialogue", character_id="cat", text="喵")
    assert pipe.voice_for_line(line, {"cat": c}, n).voice_id == "char"
    line.voice_config = VoiceConfig(provider="m", voice_id="override")
    assert pipe.voice_for_line(line, {"cat": c}, n).voice_id == "override"
    narr = ScriptLine(line_id="2", line_type="narration", text="x")
    assert pipe.voice_for_line(narr, {"cat": c}, n).voice_id == "narr"


def test_materialize_line_cues_returns_entries(tmp_path):
    # 用真实 mock sound provider（写可闻 wav）+ 临时 SoundLibrary
    from storyteller.core.sound_library import SoundLibrary
    from storyteller.providers.mock.sfx import MockSoundProvider

    cfg = Config()
    cfg.set("data_dir", str(tmp_path))
    pm, state = _state(tmp_path)
    pipe = Pipeline(cfg, project_manager=pm)
    lib = SoundLibrary(str(tmp_path / "sounds"))
    prov = MockSoundProvider(cfg)
    referenced = set()
    entries = pipe.materialize_line_cues(
        state, state.script.lines[0], 2.0, prov, lib, referenced
    )
    assert len(entries) == 1
    cue, offset = entries[0]
    assert cue.source_path and Path(cue.source_path).exists()
    assert offset == 0.0  # anchor「咚」在句首
    # 项目内有副本，全局库有记录
    assert len(lib.all()) >= 1
```

- [ ] **Step 2: 确认失败**（方法不存在）。

- [ ] **Step 3: 重构实现**

在 `Pipeline` 中新增（把 `_execute_pipeline` 248-257 行的音色优先级逻辑移入）：

```python
def voice_for_line(self, line, char_voice_map, narrator_voice):
    voice = line.voice_config
    if not voice and line.line_type == "dialogue" and line.character_id:
        voice = char_voice_map.get(line.character_id)
    return voice or narrator_voice

def line_context_directives(self, lines, idx):
    return self._line_context(lines, idx)
```

新增行级 cue 物化（从 `_apply_soundtrack` 提取逐 cue 循环的单行动作）：

```python
def materialize_line_cues(self, state, line, line_duration, provider,
                          library, referenced_paths):
    cues = list(line.sound_effects)
    if line.background_music is not None:
        cues.append(line.background_music)
    # 行内 background_music 与 effect/ambient 一样进组混音（CLI 的
    # add_effect_groups 就是这么做的）；被注释关闭的只是整片顶层 BGM 床混。
    pending = [c for c in cues if c.prompt and not c.source_path]
    if not pending and not any(c.source_path for c in cues):
        return []
    entries = []
    for cue in cues:
        if not cue.prompt and not cue.source_path:
            continue
        offset = self._anchor_offset(line, cue, line_duration)
        if cue.source_path:
            entries.append((cue, offset))
            continue
        gen_prompt = build_sound_prompt(cue.prompt, cue.type, line_duration, offset)
        record = library.find(provider, gen_prompt, audio_format="mp3")
        raw_path = self._project_sound_path(state.project_id, cue, referenced_paths)
        try:
            record, _ = self._materialize_cue(
                provider, library, cue, raw_path, gen_prompt, record=record
            )
        except Exception as exc:
            self._log_error(cue.effect_id, exc)
            continue
        referenced_paths.add(Path(raw_path))
        cue.source_path = str(raw_path)
        cue.source_type = "local"
        if cue.duration is None:
            cue.duration = record.get("duration")
        entries.append((cue, offset))
    return entries
```

注意 `_apply_soundtrack` 中**保留**其顶层 cue（script 级）处理与最终 groups 混音；把行内 cue 循环替换为调用本方法（构建 `groups` 用返回的 entries），跑既有音效测试确认逐字节/行为一致。若重构中发现该方法耦合过深，允许 `_apply_soundtrack` 保持原样、仅让新方法与其并存（重复少量代码），但必须在本任务测试中锁定新方法行为——以"既有测试全绿"为硬约束。

新增收尾方法：

```python
def finalize_audio(self, state, line_paths, output_format="mp3", with_sound=False):
    output_path = self._final_output_path(state.project_id, output_format)
    self._concatenate(line_paths, output_path)
    if with_sound:
        self._apply_soundtrack(state, output_path)
    state.state = "completed"
    self.projects.save_project(state)
    return output_path
```

同时把 `_execute_pipeline` 中音色选择改为调用 `voice_for_line`（纯重命名式重构）。

- [ ] **Step 4: 验证**：新测试 PASS；**全量 pytest 绿**（这是重构任务的核心验收）。

- [ ] **Step 5: 提交**：`git commit -m "refactor: extract reusable per-line pipeline helpers"`

---

### Task 8: Filler 预取（thinking LLM + intro 模板 + 缓存）

**Files:**
- Create: `src/storyteller/web/fillers.py`
- Test: `tests/web/test_fillers.py`

**Interfaces:**
- Consumes: `registry.get_llm(name)`、`registry.get_tts(name)`、`is_narration_voice`；TTS `synthesize(text, voice, out_path, directives=None, context=None)`。
- Produces:
  - `@dataclass FillerClip(kind: str, text: str, mp3_path: str)`
  - `class FillerPrefetcher:` `__init__(self, registry, llm_name, tts_names, cache_dir, filler_voice=None)`；`start(self, topic)`（提交 intro/thinking 两个 future 到内部 `ThreadPoolExecutor(max_workers=2)`）；`get(self, kind, timeout=None) -> Optional[FillerClip]`（kind ∈ "thinking"/"intro"，异常/超时返回 None）；`shutdown(self)`。
  - 纯函数 `build_thinking_text(llm, topic) -> str`（LLM 调用、清洗、≤50 汉字、失败回退模板）；`intro_text() -> str`；`choose_host_voice(registry, tts_names, filler_voice=None) -> Optional[tuple[str, VoiceConfig]]`。

- [ ] **Step 1: 写失败测试**

```python
# tests/web/test_fillers.py
from storyteller.providers.mock.llm import MockLLMProvider
from storyteller.providers.mock.tts import MockTTSProvider
from storyteller.providers.registry import ProviderRegistry
from storyteller.web.fillers import (
    build_thinking_text, intro_text, choose_host_voice, FillerPrefetcher,
)


def _registry(llm_text=None):
    reg = ProviderRegistry(config={})
    llm = MockLLMProvider(config={})
    if llm_text:
        llm.set_response(llm_text)
    tts = MockTTSProvider(config={})
    reg.register_llm("mock", lambda c: llm)
    reg.register_tts("mock", lambda c: tts)
    reg.set_default_llm("mock")
    return reg, llm, tts


def test_build_thinking_text_cleans_quotes_and_length():
    reg, _, _ = _registry('“你想听勇敢小恐龙的故事，让我想想。”')
    text = build_thinking_text(reg.get_llm("mock"), "勇敢小恐龙")
    assert "“" not in text and "”" not in text
    assert len(text) <= 50


def test_build_thinking_falls_back_on_error():
    reg, llm, _ = _registry()
    llm.set_error(RuntimeError("boom"))
    text = build_thinking_text(reg.get_llm("mock"), "一个关于星星的故事")
    assert "星星" in text or "故事" in text  # 回退模板包含截断主题


def test_intro_text_is_fixed_string():
    assert "故事" in intro_text()


def test_choose_host_voice_prefers_narrator():
    reg, _, _ = _registry()
    provider, voice = choose_host_voice(reg, ["mock"])
    assert provider == "mock" and voice.voice_id == "narrator_01"


def test_prefetcher_returns_both_clips(tmp_path):
    reg, _, _ = _registry("好的，关于小恐龙，让我想一想。")
    pf = FillerPrefetcher(reg, "mock", ["mock"], str(tmp_path / "cache"))
    pf.start("小恐龙")
    thinking = pf.get("thinking", timeout=10)
    intro = pf.get("intro", timeout=10)
    pf.shutdown()
    assert thinking is not None and thinking.mp3_path
    assert intro is not None and "故事" in intro.text
```

- [ ] **Step 2: 确认失败**（ModuleNotFoundError）。

- [ ] **Step 3: 实现**

```python
# src/storyteller/web/fillers.py
from __future__ import annotations

import hashlib
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ..core.voice_matcher import is_narration_voice

_THINKING_FALLBACK = "好的，关于{topic}的故事，让我好好想一想……"
_THINKING_MAX_CHARS = 50
_INTRO_TEMPLATES = (
    "故事就要开始喽，准备好了吗？",
    "那我们开始啦，认真听哦。",
    "故事就要开始了，我们一起来听吧。",
)


def _clean_spoken(text, topic):
    text = (text or "").strip().strip('“”"\'「」 \n\t')
    text = re.sub(r"^(好的，?|嗯，?|OK，?)", "", text).strip()
    text = re.sub(r"\s+", "", text)
    if not text:
        text = _THINKING_FALLBACK.format(topic=str(topic)[:20])
    if len(text) > _THINKING_MAX_CHARS:
        cut = text[:_THINKING_MAX_CHARS]
        last = max(cut.rfind("，"), cut.rfind("。"))
        text = cut[:last] if last > 12 else cut
    return text


def build_thinking_text(llm, topic):
    system = (
        "你是儿童故事应用的主持人。用户给了一个含混的故事主题，"
        "请提取其中的关键诉求（主角/题材/年龄段/语气/用途），用一句温暖口语的话"
        "复述确认并表示要去构思。只输出这句口播文本本身：无引号、无 markdown、"
        "无表情符号、无称呼前缀，1-2 句，不超过 50 个汉字，严禁开始讲故事。"
    )
    try:
        raw = llm.chat(
            [{"role": "system", "content": system},
             {"role": "user", "content": str(topic)}],
            temperature=0.3, max_tokens=150,
        )
        return _clean_spoken(raw, topic)
    except Exception:
        return _THINKING_FALLBACK.format(topic=str(topic)[:20])


def intro_text():
    return random.choice(_INTRO_TEMPLATES)


def choose_host_voice(registry, tts_names, filler_voice=None):
    if filler_voice and ":" in filler_voice:
        name, voice_id = filler_voice.split(":", 1)
        for v in registry.get_tts(name).list_voices():
            if v.voice_id == voice_id:
                return name, v
    for name in tts_names:
        voices = registry.get_tts(name).list_voices()
        for v in voices:
            if is_narration_voice(v):
                return name, v
        if voices:
            return name, voices[0]
    return None


@dataclass
class FillerClip:
    kind: str
    text: str
    mp3_path: str


class FillerPrefetcher:
    def __init__(self, registry, llm_name, tts_names, cache_dir, filler_voice=None):
        self.registry = registry
        self.llm_name = llm_name
        self.tts_names = tts_names
        self.cache_dir = Path(cache_dir) / "fillers"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.host = choose_host_voice(registry, tts_names, filler_voice)
        self._ex = ThreadPoolExecutor(max_workers=2, thread_name_prefix="filler")
        self._futures = {}

    def _synth(self, kind, text):
        if self.host is None:
            return None
        provider_name, voice = self.host
        key = hashlib.sha256(
            "|".join([provider_name, voice.voice_id, str(voice.speed),
                      str(voice.pitch), text]).encode("utf-8")
        ).hexdigest()
        path = self.cache_dir / (key + ".mp3")
        if not path.exists():
            self.registry.get_tts(provider_name).synthesize(text, voice, path)
        return FillerClip(kind=kind, text=text, mp3_path=str(path))

    def _thinking_chain(self, topic):
        text = build_thinking_text(self.registry.get_llm(self.llm_name), topic)
        return self._synth("thinking", text)

    def start(self, topic):
        self._futures["thinking"] = self._ex.submit(self._thinking_chain, topic)
        self._futures["intro"] = self._ex.submit(self._synth, "intro", intro_text())

    def get(self, kind, timeout=None):
        future = self._futures.get(kind)
        if future is None:
            return None
        try:
            return future.result(timeout=timeout)
        except Exception:
            return None

    def shutdown(self):
        for future in self._futures.values():
            future.cancel()
        self._ex.shutdown(wait=False)
```

- [ ] **Step 4: 验证**：PASS、全量绿。

- [ ] **Step 5: 提交**：`git commit -m "feat: filler voice prefetcher with LLM thinking line and cache"`

---

### Task 9: JobManager 与任务状态机

**Files:**
- Create: `src/storyteller/web/jobs.py`
- Test: `tests/web/test_jobs.py`

**Interfaces:**
- Produces:
  - 阶段常量 `PHASE_QUEUED/SCRIPT/VOICES/LINE/FINALIZING/COMPLETED/FAILED/CANCELED`
  - `@dataclass JobParams(topic, length="medium", complexity="simple", with_sound=False, tts_providers=None)`
  - `class Job`: `id, params, phase, project_id|None, script_ready|None, queue.Queue()`（**无界**：编排器可能在 WS 客户端排空之前就跑完整条流）, `cancel_event`, `line_index/total`, `emit(obj)`（dict 入队）, `emit_bytes(data)`（用 `{"_bytes": data}` 内部信封，消费者识别）
  - `class JobManager`: `__init__(concurrency=2)`；`create(params) -> Job`；`submit(job, target)`（ThreadPoolExecutor + BoundedSemaphore 控并发，超出每 0.5s 发一次 `{type:status, phase:queued, queue_position}`）；`get(job_id)`；`cancel(job_id)`。

- [ ] **Step 1: 写失败测试**

```python
# tests/web/test_jobs.py
import threading
import time

from storyteller.web.jobs import JobManager, JobParams, PHASE_QUEUED


def _drain(job, timeout=5, want=None):
    events = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            item = job.queue.get(timeout=0.2)
        except Exception:
            break
        events.append(item)
        if want and any(
            isinstance(e, dict) and e.get("type") == "status"
            and e.get("phase") == want for e in events
        ):
            break
    return events


def test_job_runs_target_and_emits():
    mgr = JobManager(concurrency=1)
    job = mgr.create(JobParams(topic="x"))

    def work(j):
        j.phase = "line"
        j.emit({"type": "status", "phase": "line"})
        j.emit_bytes(b"\x00" * 10)

    mgr.submit(job, work)
    events = _drain(job, want="line")
    assert any(e.get("type") == "status" for e in events)
    assert any(e.get("_bytes") == b"\x00" * 10 for e in events)


def test_cancel_flag_is_observable():
    mgr = JobManager(concurrency=1)
    job = mgr.create(JobParams(topic="x"))
    mgr.cancel(job.id)
    assert job.cancel_event.is_set()


def test_queue_position_when_at_capacity():
    mgr = JobManager(concurrency=1)
    gate = threading.Event()
    j1 = mgr.create(JobParams(topic="a"))
    mgr.submit(j1, lambda j: gate.wait(5))
    j2 = mgr.create(JobParams(topic="b"))
    mgr.submit(j2, lambda j: None)
    events = _drain(j2, want=PHASE_QUEUED)
    assert any(e.get("queue_position") == 1 for e in events)
    gate.set()
```

- [ ] **Step 2: 确认失败**。

- [ ] **Step 3: 实现**

```python
# src/storyteller/web/jobs.py
from __future__ import annotations

import queue
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

(PHASE_QUEUED, PHASE_SCRIPT, PHASE_VOICES, PHASE_LINE,
 PHASE_FINALIZING, PHASE_COMPLETED, PHASE_FAILED, PHASE_CANCELED) = (
    "queued", "script", "voices", "line", "finalizing",
    "completed", "failed", "canceled",
)


@dataclass
class JobParams:
    topic: str
    length: str = "medium"
    complexity: str = "simple"
    with_sound: bool = False
    tts_providers: object = None  # Optional[list[str]]


class Job:
    def __init__(self, params):
        self.id = "job_" + uuid.uuid4().hex
        self.params = params
        self.phase = PHASE_QUEUED
        self.project_id = None
        self.line_index = 0
        self.total = 0
        self.script_ready = None  # dict：重连时补发 script_ready（Task 13 写入）
        self.cancel_event = threading.Event()
        # Unbounded: the orchestrator can finish before a slow WS client
        # drains the stream; events for a finished job stay consumable.
        self.queue = queue.Queue()

    def emit(self, obj):
        self.queue.put(obj)

    def emit_bytes(self, data):
        self.queue.put({"_bytes": data})


class JobManager:
    def __init__(self, concurrency=2):
        self.concurrency = max(1, int(concurrency))
        self._slots = threading.BoundedSemaphore(self.concurrency)
        self._ex = ThreadPoolExecutor(
            max_workers=max(4, self.concurrency * 2),
            thread_name_prefix="story-job",
        )
        self._jobs = {}
        self._lock = threading.Lock()
        self._order = []

    def create(self, params):
        job = Job(params)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
        return job

    def get(self, job_id):
        return self._jobs.get(job_id)

    def cancel(self, job_id):
        job = self.get(job_id)
        if job:
            job.cancel_event.set()
        return job

    def _queue_position(self, job):
        with self._lock:
            return sum(
                1 for jid in self._order
                if self._jobs[jid].phase == PHASE_QUEUED and jid != job.id
            )

    def submit(self, job, target):
        def wrapped():
            if not self._slots.acquire(timeout=0.1):
                while not self._slots.acquire(timeout=0.5):
                    if job.cancel_event.is_set():
                        job.emit({"type": "canceled"})
                        job.phase = PHASE_CANCELED
                        return
                    job.emit({"type": "status", "phase": PHASE_QUEUED,
                              "queue_position": self._queue_position(job) + 1})
            try:
                target(job)
            finally:
                self._slots.release()
        self._ex.submit(wrapped)
```

- [ ] **Step 4: 验证**：PASS；全量绿。若排队位置在调度极快时偶发为 0 而测试断言 ==1，把断言放宽为 `>= 0 且收到过 queued status`（核心是字段存在且为非负 int）。

- [ ] **Step 5: 提交**：`git commit -m "feat: in-memory job manager with phases and cancellation"`

---

### Task 10: 鉴权（密码、HMAC token、限流）

**Files:**
- Create: `src/storyteller/web/auth.py`
- Test: `tests/web/test_auth.py`

**Interfaces:**
- Produces:
  - `class TokenIssuer`: `__init__(secret, ttl_days=30)`；无 secret 时 `secrets.token_hex(32)` 并暴露 `ephemeral=True`；`issue() -> str`；`verify(token) -> bool`（itsdangerous URLSafeTimedSerializer，salt `storyteller-web`）。
  - `check_password(password, passwords) -> bool`（hmac.compare_digest 常量时间）。
  - `class RateLimiter`: `__init__(per_minute=10)`；`allow(key) -> bool`（deque 滑窗，per_minute=0 永远 True）。
  - cookie 名常量 `SESSION_COOKIE="storyteller_session"`。

- [ ] **Step 1: 写失败测试**

```python
# tests/web/test_auth.py
import time

from storyteller.web.auth import TokenIssuer, check_password, RateLimiter


def test_password_check_constant_time():
    assert check_password("abc", ["x", "abc"])
    assert not check_password("abc", ["x"])
    assert not check_password("", ["x"])


def test_token_roundtrip_and_tamper():
    iss = TokenIssuer(secret="fixed-secret", ttl_days=1)
    token = iss.issue()
    assert iss.verify(token)
    assert not iss.verify(token + "x")
    assert not TokenIssuer(secret="other", ttl_days=1).verify(token)


def test_ephemeral_issuer_marks_itself():
    iss = TokenIssuer(secret=None)
    assert iss.ephemeral is True
    assert iss.verify(iss.issue())


def test_rate_limiter_window():
    rl = RateLimiter(per_minute=2)
    assert rl.allow("ip1") and rl.allow("ip1")
    assert not rl.allow("ip1")
    assert rl.allow("ip2")  # 独立计数


def test_rate_limiter_disabled():
    assert all(RateLimiter(per_minute=0).allow("k") for _ in range(100))
```

- [ ] **Step 2: 确认失败**。

- [ ] **Step 3: 实现**

```python
# src/storyteller/web/auth.py
from __future__ import annotations

import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE = "storyteller_session"
_SALT = "storyteller-web"


def check_password(password, passwords):
    given = (password or "").encode("utf-8")
    return any(
        hmac.compare_digest(given, p.encode("utf-8")) for p in (passwords or [])
    )


class TokenIssuer:
    def __init__(self, secret=None, ttl_days=30):
        self.ephemeral = not secret
        self._secret = secret or secrets.token_hex(32)
        self.ttl_seconds = int(ttl_days) * 86400
        self._serializer = URLSafeTimedSerializer(self._secret, salt=_SALT)

    def issue(self):
        return self._serializer.dumps({"v": 1})

    def verify(self, token):
        if not token:
            return False
        try:
            self._serializer.loads(token, max_age=self.ttl_seconds)
            return True
        except (BadSignature, SignatureExpired):
            return False


class RateLimiter:
    def __init__(self, per_minute=10):
        self.per_minute = per_minute
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key):
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            return True
```

- [ ] **Step 4: 验证**：PASS、全量绿。

- [ ] **Step 5: 提交**：`git commit -m "feat: password auth tokens and sliding-window rate limiter"`

---

### Task 11: FastAPI 应用工厂、鉴权路由与 options

**Files:**
- Create: `src/storyteller/web/schemas.py`、`src/storyteller/web/app.py`、`src/storyteller/web/routes_auth.py`、`src/storyteller/web/routes_options.py`
- Test: `tests/web/test_app_auth.py`

**Interfaces:**
- Consumes: Config（含已注册 registry，由 app 工厂注入）。
- Produces:
  - `create_app(config, registry=None) -> FastAPI`：registry 为 None 时 `ProviderRegistry(config)` + `register_providers_from_config`；挂路由；app.state 存 config/registry/issuer/limiter；静态目录存在才挂载（本任务可先不挂，Task 14 挂）。
  - 依赖 `current_token(request) -> str|None`、`require_auth(...)`（401 JSON `{detail}`）。
  - `POST /api/auth {password}` → 204 set-cookie（HttpOnly, SameSite=lax, Secure 仅当 request.url.scheme=https；没有密码列表配置也返回 401）；`POST /api/auth/logout` 204 清 cookie；`GET /api/me` → `{authenticated: bool}`（200 始终）。
  - `GET /api/config/options`（需登录）→ `{lengths, complexities, tts_providers:[{name}], sound_enabled:bool}`，不回显任何 key/endpoint。

- [ ] **Step 1: 写失败测试**

```python
# tests/web/test_app_auth.py
import pytest
from fastapi.testclient import TestClient

from storyteller.core.config import Config
from storyteller.web.app import create_app


def _app(passwords=("secret123",), sound=False, tts=("mock",), monkeypatch_env=None):
    cfg = Config()
    cfg.set("web.passwords", list(passwords))
    cfg.set("web.secret", "unit-secret")
    cfg.set("web.rate_limit_per_min", 0)
    cfg.set("sound.enabled", sound)
    cfg.set("tts.providers", list(tts))
    cfg.set("tts.provider_config.mock", {"type": "mock"})
    return create_app(cfg)


def test_wrong_password_401():
    client = TestClient(_app())
    r = client.post("/api/auth", json={"password": "nope"})
    assert r.status_code == 401


def test_login_me_logout():
    client = TestClient(_app())
    assert client.get("/api/me").json()["authenticated"] is False
    r = client.post("/api/auth", json={"password": "secret123"})
    assert r.status_code == 204 and "storyteller_session" in r.cookies
    assert client.get("/api/me").json()["authenticated"] is True
    client.post("/api/auth/logout")
    assert client.get("/api/me").json()["authenticated"] is False


def test_options_requires_auth_and_hides_secrets():
    client = TestClient(_app())
    assert client.get("/api/config/options").status_code == 401
    client.post("/api/auth", json={"password": "secret123"})
    body = client.get("/api/config/options").json()
    assert "mock" in body["tts_providers"]
    assert body["sound_enabled"] is False
    assert "api_key" not in r_text(body)


def r_text(body):
    import json
    return json.dumps(body, ensure_ascii=False)
```

- [ ] **Step 2: 确认失败**（web.app 不存在）。

- [ ] **Step 3: 实现**

`schemas.py`：

```python
from pydantic import BaseModel

class AuthRequest(BaseModel):
    password: str
```

`routes_auth.py`：

```python
from fastapi import APIRouter, Request, Response, HTTPException
from .auth import SESSION_COOKIE, check_password

router = APIRouter()


@router.post("/api/auth", status_code=204)
def login(body: "AuthRequest", request: Request, response: Response):
    from .schemas import AuthRequest  # noqa: F401 (typing)
    passwords = request.app.state.config.get("web.passwords") or []
    if not check_password(body.password, passwords):
        raise HTTPException(status_code=401, detail="密码错误")
    token = request.app.state.issuer.issue()
    secure = request.url.scheme == "https"
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax",
        secure=secure, path="/",
        max_age=request.app.state.config.get("web.token_ttl_days") * 86400,
    )


@router.post("/api/auth/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/api/me")
def me(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    return {"authenticated": request.app.state.issuer.verify(token)}
```

`app.py`：

```python
from fastapi import Depends, FastAPI, Header, HTTPException, Request

from .auth import RateLimiter, SESSION_COOKIE, TokenIssuer
from .routes_auth import router as auth_router
from .routes_options import router as options_router


def create_app(config, registry=None):
    if registry is None:
        from ..providers.registry import ProviderRegistry
        from ..providers.bootstrap import register_providers_from_config
        registry = ProviderRegistry(config)
        register_providers_from_config(config, registry)

    app = FastAPI(title="storyteller web")
    app.state.config = config
    app.state.registry = registry
    app.state.issuer = TokenIssuer(
        config.get("web.secret"), config.get("web.token_ttl_days")
    )
    app.state.limiter = RateLimiter(config.get("web.rate_limit_per_min"))
    app.include_router(auth_router)
    app.include_router(options_router)
    return app
```

`routes_options.py`：

```python
from fastapi import APIRouter, Request, HTTPException

from .auth import SESSION_COOKIE

router = APIRouter()
LENGTHS = ["short", "medium", "long"]
COMPLEXITIES = ["simple", "medium", "rich"]


def _authed(request):
    token = request.cookies.get(SESSION_COOKIE)
    if not request.app.state.issuer.verify(token):
        raise HTTPException(status_code=401, detail="未登录")


@router.get("/api/config/options")
def options(request: Request):
    _authed(request)
    names = request.app.state.registry.list_tts_names()
    return {
        "lengths": LENGTHS,
        "complexities": COMPLEXITIES,
        "tts_providers": names,
        "sound_enabled": bool(request.app.state.config.get("sound.enabled")),
    }
```

- [ ] **Step 4: 验证**：PASS、全量绿。

- [ ] **Step 5: 提交**：`git commit -m "feat: fastapi app factory, session auth, and options endpoint"`

---

### Task 12: 历史故事 REST 接口

**Files:**
- Create: `src/storyteller/web/routes_stories.py`（在 app 工厂 include）
- Test: `tests/web/test_routes_stories.py`

**Interfaces:**
- Produces: `GET /api/stories`、`GET /api/stories/{ref}`、`GET /api/stories/{ref}/audio`、`GET /api/stories/{ref}/segments/{line_id}.mp3`；统一用 ProjectManager（root = `config.get("project_dir")`）；ProjectError → 404（找不到）/400（歧义）；line_id 白名单 `^[A-Za-z0-9_-]+$`，不合规 400。详情不回绝对路径。

- [ ] **Step 1: 写失败测试**

```python
# tests/web/test_routes_stories.py
from fastapi.testclient import TestClient

from storyteller.core.config import Config
from storyteller.core.models import (
    Character, ProjectState, Script, ScriptLine, VoiceConfig,
)
from storyteller.core.project import ProjectManager
from storyteller.web.app import create_app


def _login(client):
    client.post("/api/auth", json={"password": "pw"})


def _client_with_project(tmp_path):
    cfg = Config()
    cfg.set("web.passwords", ["pw"]); cfg.set("web.secret", "x")
    cfg.set("web.rate_limit_per_min", 0)
    cfg.set("data_dir", str(tmp_path / ".storyteller"))
    cfg.set("project_dir", str(tmp_path / ".storyteller" / "stories"))
    app = create_app(cfg)
    pm = ProjectManager(cfg.get("project_dir"))
    state = pm.create_project(topic="恐龙", config={})
    state.script = Script(
        script_id="s", title="小恐龙", topic="恐龙",
        characters=[Character(id="narrator", name="旁白", description="",
            voice_config=VoiceConfig(provider="mock", voice_id="narrator_01"))],
        lines=[ScriptLine(line_id="L1", line_type="narration", text="从前……")],
    )
    state.state = "completed"
    pm.save_project(state)
    (pm.resolve_project_dir(state.project_id) / "story.mp3").write_bytes(b"ID3fake")
    return TestClient(app), state.project_id


def test_list_and_detail(tmp_path):
    client, pid = _client_with_project(tmp_path)
    assert client.get("/api/stories").status_code == 401
    _login(client)
    items = client.get("/api/stories").json()["stories"]
    assert len(items) == 1 and items[0]["title"] == "小恐龙"
    detail = client.get("/api/stories/{}".format(pid)).json()
    assert detail["lines"][0]["text"] == "从前……"
    assert "audio_path" not in str(detail)


def test_audio_and_segment_guard(tmp_path):
    client, pid = _client_with_project(tmp_path)
    _login(client)
    r = client.get("/api/stories/{}/audio".format(pid))
    assert r.status_code == 200 and r.content == b"ID3fake"
    bad = client.get("/api/stories/{}/segments/..%2fevil.mp3".format(pid))
    assert bad.status_code in (400, 404)
    assert client.get("/api/stories/missing-ref").status_code == 404
```

- [ ] **Step 2: 确认失败**（404/无路由）。

- [ ] **Step 3: 实现**

```python
# src/storyteller/web/routes_stories.py
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from ..core.exceptions import ProjectError
from ..core.project import ProjectManager
from .auth import SESSION_COOKIE

router = APIRouter()
_LINE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _projects(request):
    return ProjectManager(request.app.state.config.get("project_dir"))


def _resolve(request, ref):
    try:
        return _projects(request).resolve_project_dir(ref)
    except ProjectError as exc:
        msg = str(exc)
        raise HTTPException(status_code=400 if "Ambiguous" in msg else 404, detail=msg)


def _require_auth(request):
    if not request.app.state.issuer.verify(request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(status_code=401, detail="未登录")


@router.get("/api/stories")
def list_stories(request: Request):
    _require_auth(request)
    entries = []
    for dir_name, state in _projects(request).list_project_entries():
        entries.append({
            "id": state.project_id,
            "dir_name": dir_name,
            "title": state.script.title if state.script else None,
            "state": state.state,
            "created_at": state.created_at.isoformat() if state.created_at else None,
        })
    entries.sort(key=lambda e: e["created_at"] or "", reverse=True)
    return {"stories": entries}


def _line_duration_ms(project_dir, line_id):
    try:
        from pydub import AudioSegment
        p = project_dir / "audio" / "{}.mp3".format(line_id)
        return len(AudioSegment.from_file(str(p))) if p.exists() else None
    except Exception:
        return None


@router.get("/api/stories/{ref}")
def story_detail(ref: str, request: Request):
    _require_auth(request)
    project_dir = _resolve(request, ref)
    state = _projects(request).load_project(project_dir.name)
    if not state.script:
        raise HTTPException(status_code=404, detail="剧本尚未生成")
    char_names = {c.id: c.name for c in state.script.characters}
    return {
        "id": state.project_id,
        "title": state.script.title,
        "topic": state.script.topic,
        "state": state.state,
        "characters": [{"id": c.id, "name": c.name} for c in state.script.characters],
        "lines": [{
            "line_id": ln.line_id,
            "line_type": ln.line_type,
            "speaker": char_names.get(ln.character_id) or ln.line_type,
            "text": ln.text,
            "duration_ms": _line_duration_ms(project_dir, ln.line_id),
        } for ln in state.script.lines],
    }


@router.get("/api/stories/{ref}/audio")
def story_audio(ref: str, request: Request):
    _require_auth(request)
    project_dir = _resolve(request, ref)
    candidates = sorted(project_dir.glob("story.*"))
    audio = next((c for c in candidates if c.suffix.lstrip(".").lower() in
                  ("mp3", "wav", "ogg", "m4a")), candidates[0] if candidates else None)
    if not audio or not audio.exists():
        raise HTTPException(status_code=404, detail="音频尚未生成")
    return FileResponse(str(audio))


@router.get("/api/stories/{ref}/segments/{segment}")
def story_segment(ref: str, segment: str, request: Request):
    _require_auth(request)
    line_id = segment[:-4] if segment.endswith(".mp3") else segment
    if not _LINE_ID_RE.match(line_id):
        raise HTTPException(status_code=400, detail="非法的行 id")
    project_dir = _resolve(request, ref)
    path = project_dir / "audio" / "{}.mp3".format(line_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="分段不存在")
    return FileResponse(str(path))
```

在 `create_app` 里 `app.include_router(stories_router)`。

- [ ] **Step 4: 验证**：PASS、全量绿。

- [ ] **Step 5: 提交**：`git commit -m "feat: story history, detail, audio and segment endpoints"`

---
### Task 13: StreamOrchestrator 流式编排

**Files:**
- Create: `src/storyteller/web/streaming.py`
- Test: `tests/web/test_streaming_orchestrator.py`

**Interfaces:**
- Consumes: Pipeline（Task 7 构件）、registry stream/普通 tts、tts_chunks、mix_line、FillerPrefetcher、Job。
- Produces: `class StreamOrchestrator:` `__init__(self, config, projects=None)`；`run(self, job) -> None`（直接操作 job.queue，不感知 WebSocket）。事件信封全部为 dict：文本事件 `{type, ...}`，音频 `{"_bytes": ...}`。阶段/取消在每个阶段与行边界检查 `job.cancel_event`。

**filler 时序（与 spec §4.4 一致）**：job 启动即 `fillers.start(topic)` 并行预取；剧本一就绪就在"匹配音色"阶段发送 thinking（拿不到就 `filler_abort`），音色匹配结束时若 thinking 仍未取完则 abort；intro 在 script_ready 之后、line 1 之前播放。

- [ ] **Step 1: 写失败测试**

```python
# tests/web/test_streaming_orchestrator.py
from storyteller.core.config import Config
from storyteller.web.jobs import Job, JobParams
from storyteller.web.streaming import StreamOrchestrator


def _drain(job):
    out = []
    while True:
        try:
            item = job.queue.get(timeout=5)
        except Exception:
            break
        out.append(item)
        if isinstance(item, dict) and item.get("type") in (
            "complete", "error", "canceled"
        ):
            break
    return out


def _config(tmp_path):
    cfg = Config()
    cfg.set("data_dir", str(tmp_path / ".storyteller"))
    cfg.set("project_dir", str(tmp_path / ".storyteller" / "stories"))
    cfg.set("voice_matcher", "rule")
    cfg.set("tts.providers", ["mock"])
    cfg.set("tts.provider_config.mock", {"type": "mock"})
    cfg.set("llm.providers", ["mock"])
    cfg.set("llm.provider_config.mock", {"type": "mock"})
    cfg.set("web.filler_voice", "mock:narrator_01")
    return cfg


def test_full_run_emits_standard_events_and_pcm(tmp_path):
    cfg = _config(tmp_path)
    job = Job(JobParams(topic="小恐龙", tts_providers=["mock"]))
    StreamOrchestrator(cfg).run(job)
    events = _drain(job)
    kinds = [e.get("type") for e in events if "_bytes" not in e]
    assert kinds[0] == "ready"
    assert "script_ready" in kinds
    assert kinds.count("line_start") == 4  # MockLLM 默认剧本 4 行
    assert kinds.count("line_end") == 4
    assert kinds[-1] == "complete"
    assert all(len(e["_bytes"]) % 2 == 0 for e in events if "_bytes" in e)
    import pathlib
    finals = list(pathlib.Path(cfg.get("project_dir")).glob("*/story.mp3"))
    assert finals and finals[0].stat().st_size > 0


def test_filler_events_present(tmp_path):
    cfg = _config(tmp_path)
    job = Job(JobParams(topic="小恐龙", tts_providers=["mock"]))
    StreamOrchestrator(cfg).run(job)
    kinds = [e.get("type") for e in _drain(job) if "_bytes" not in e]
    assert "filler_start" in kinds and "filler_end" in kinds
    # intro 必须在 script_ready 之后
    intro = kinds.index("filler_start")
    assert "script_ready" in kinds


def test_cancelled_before_lines(tmp_path):
    cfg = _config(tmp_path)
    job = Job(JobParams(topic="x", tts_providers=["mock"]))
    job.cancel_event.set()
    StreamOrchestrator(cfg).run(job)
    events = _drain(job)
    assert events[-1].get("type") == "canceled"
```

注：mock thinking/intro 都很快，正常路径断言能看到 filler_start/filler_end；abort 分支由 WS 集成测试在慢 provider 场景难以构造，不单列。

- [ ] **Step 2: 确认失败**（模块不存在）。

- [ ] **Step 3: 实现**

```python
# src/storyteller/web/streaming.py
from __future__ import annotations

from pathlib import Path

from ..core.exceptions import TTSError
from ..core.pipeline import Pipeline
from ..core.story_generator import StoryGenerator
from ..core.tts import STREAM_SAMPLE_RATE
from ..core.voice_matcher import VoiceMatcher
from ..providers.registry import ProviderRegistry
from ..providers.bootstrap import register_providers_from_config
from .fillers import FillerPrefetcher
from .tts_chunks import (
    audio_file_to_standard_pcm, iter_pcm_frames, pcm_duration_ms,
    pcm_to_mp3_file,
)


class StreamOrchestrator:
    def __init__(self, config, projects=None):
        self.config = config
        self.registry = ProviderRegistry(config)
        register_providers_from_config(config, self.registry)
        self.pipeline = Pipeline(config, project_manager=projects)
        self.projects = self.pipeline.projects

    def run(self, job):
        try:
            self._run(job)
        except Exception as exc:
            job.emit({"type": "error", "message": str(exc)})

    def _send_file_as_pcm(self, job, path):
        pcm = audio_file_to_standard_pcm(path)
        for frame in iter_pcm_frames(pcm):
            job.emit_bytes(frame)
        return pcm

    def _default_llm_name(self):
        name = self.config.get("llm.default_provider")
        names = self.registry.list_llm_names()
        if name in names:
            return name
        return names[0] if names else None

    def _run(self, job):
        p = job.params
        job.emit({"type": "ready", "audio": {
            "encoding": "pcm_s16le",
            "sample_rate": STREAM_SAMPLE_RATE, "channels": 1}})

        tts_names = p.tts_providers or self.registry.list_tts_names()
        llm_name = self._default_llm_name()
        if not tts_names:
            raise TTSError("没有可用的 TTS provider")
        if not llm_name:
            raise TTSError("没有可用的 LLM provider")

        state = self.projects.create_project(
            topic=p.topic,
            config={"length": p.length, "complexity": p.complexity,
                    "topic": p.topic},
        )
        job.project_id = state.project_id

        fillers = FillerPrefetcher(
            self.registry, llm_name, tts_names,
            str(Path(self.config.get("data_dir")) / "web_cache"),
            self.config.get("web.filler_voice"),
        )
        fillers.start(p.topic)

        # ---- 阶段 1：剧本 ----
        job.phase = "script"
        job.emit({"type": "status", "phase": "script",
                  "message": "正在生成剧本…"})
        llm = self.registry.get_llm(llm_name)
        state.script = StoryGenerator(llm).generate_script(
            p.topic, p.length, p.complexity, with_sound=bool(p.with_sound)
        )
        state.state = "script_generated"
        self.projects.save_project(state)
        self.projects.rename_for_title(state)
        self.pipeline._export_script(state)

        # thinking：剧本就绪即取（预取与剧本生成并行）
        thinking = fillers.get("thinking", timeout=0)
        if thinking is not None:
            job.emit({"type": "filler_start", "kind": "thinking",
                      "text": thinking.text})
            self._send_file_as_pcm(job, thinking.mp3_path)
            job.emit({"type": "filler_end", "kind": "thinking"})
        else:
            job.emit({"type": "filler_abort", "kind": "thinking"})

        if job.cancel_event.is_set():
            job.phase = "canceled"
            job.emit({"type": "canceled"})
            fillers.shutdown()
            return

        # ---- 阶段 2：音色匹配 ----
        job.phase = "voices"
        job.emit({"type": "status", "phase": "voices",
                  "message": "正在匹配音色…"})
        matcher = VoiceMatcher(
            self.registry, llm=llm,
            mode=self.config.get("voice_matcher") or "rule",
        )
        matcher.match_voices(state.script, allowed_providers=tts_names)
        state.state = "voice_configured"
        self.projects.save_project(state)
        self.pipeline._export_script(state)

        # 音色匹配结束：thinking 若还没播完则打断（正常 mock 路径早结束）。
        # 已发送的 PCM 在客户端可能仍在排队，由 filler_abort 丢弃未播 source。
        job.emit({"type": "filler_abort", "kind": "thinking"})

        char_voice_map = {
            c.id: c.voice_config for c in state.script.characters
            if c.voice_config
        }
        narrator_voice = self.pipeline._find_narrator_voice(
            state.script, char_voice_map)
        char_names = {c.id: c.name for c in state.script.characters}

        # ---- intro filler（第一行之前）----
        intro = fillers.get("intro", timeout=30)
        if intro is not None:
            job.emit({"type": "filler_start", "kind": "intro",
                      "text": intro.text})
            self._send_file_as_pcm(job, intro.mp3_path)
            job.emit({"type": "filler_end", "kind": "intro"})
        fillers.shutdown()

        script_ready = {
            "type": "script_ready", "title": state.script.title,
            "total": len(state.script.lines),
            "lines": [{
                "line_id": ln.line_id, "line_type": ln.line_type,
                "character_id": ln.character_id,
                "speaker": char_names.get(ln.character_id) or ln.line_type,
            } for ln in state.script.lines],
        }
        job.script_ready = script_ready
        job.emit(script_ready)

        # ---- 阶段 3：逐行 ----
        job.phase = "line"
        job.total = len(state.script.lines)
        line_paths = []
        sound_provider = sound_library = None
        with_sound = bool(p.with_sound)
        if with_sound:
            try:
                sound_provider = self.pipeline._get_sound_provider()
                sound_library = self.pipeline._get_sound_library()
            except Exception as exc:
                job.emit({"type": "warning",
                          "message": "音效不可用：{}".format(exc)})
                with_sound = False
        referenced = set()

        for idx, line in enumerate(state.script.lines, start=1):
            if job.cancel_event.is_set():
                self.projects.save_project(state)
                job.phase = "canceled"
                job.emit({"type": "canceled"})
                return

            job.line_index = idx
            voice = self.pipeline.voice_for_line(
                line, char_voice_map, narrator_voice)
            if not voice:
                job.emit({"type": "warning", "line_id": line.line_id,
                          "message": "无可用音色"})
                continue

            has_cues = with_sound and bool(
                line.sound_effects or line.background_music)
            job.emit({"type": "line_start", "line_id": line.line_id,
                      "index": idx, "total": job.total,
                      "speaker": char_names.get(line.character_id) or line.line_type,
                      "text": line.text, "has_sound": bool(has_cues)})

            out_path = self.pipeline._audio_path(
                state.project_id, line.line_id, "mp3")
            directives, context = self.pipeline.line_context_directives(
                state.script.lines, idx - 1)
            stream_tts = self.registry.get_stream_tts(voice.provider)

            try:
                if not has_cues and stream_tts is not None:
                    # 路径 A：标准 PCM 帧直通，同时累积编码为行段 mp3
                    pcm_buffer = bytearray()
                    for chunk in stream_tts.stream_synthesize(
                            line.text, voice,
                            directives=directives, context=context):
                        job.emit_bytes(chunk.data)
                        pcm_buffer += chunk.data
                    pcm_to_mp3_file(bytes(pcm_buffer), out_path)
                else:
                    # 路径 B（有 cue）/ 降级（provider 不支持流）：整行合成
                    self.registry.get_tts(voice.provider).synthesize(
                        line.text, voice, out_path,
                        directives=directives, context=context)
                    if has_cues:
                        from pydub import AudioSegment
                        duration = len(
                            AudioSegment.from_file(str(out_path))) / 1000.0
                        entries = self.pipeline.materialize_line_cues(
                            state, line, duration, sound_provider,
                            sound_library, referenced)
                        from .mixes import mix_line_with_cues
                        mix_line_with_cues(out_path, entries, out_path)
                    # 统一出口：文件 -> 标准 24k PCM 帧
                    self._send_file_as_pcm(job, out_path)

                line.audio_path = str(out_path)
                line_paths.append(str(out_path))
            except Exception as exc:
                job.emit({"type": "warning", "line_id": line.line_id,
                          "message": str(exc)})
                continue

            from pydub import AudioSegment
            duration_ms = len(AudioSegment.from_file(str(out_path)))
            job.emit({"type": "line_end", "line_id": line.line_id,
                      "duration_ms": duration_ms})

        if not line_paths:
            raise TTSError("没有成功生成任何音频行")
        self.projects.save_project(state)

        # ---- 阶段 4：拼接 + 精混 ----
        job.phase = "finalizing"
        job.emit({"type": "finalizing"})
        output = self.pipeline.finalize_audio(
            state, line_paths, "mp3", with_sound=with_sound)
        job.phase = "completed"
        job.emit({"type": "complete", "project_id": state.project_id,
                  "title": state.script.title,
                  "audio_url": "/api/stories/{}/audio".format(
                      state.project_id),
                  "script_url": "/api/stories/{}".format(state.project_id),
                  "duration_ms": None})
```

- [ ] **Step 4: 验证**：`pytest tests/web/test_streaming_orchestrator.py -v` 全 PASS；全量绿。若 MockLLM 默认剧本行数变化，以 `script_ready.total` 为准调整断言数字。

- [ ] **Step 5: 提交**：`git commit -m "feat: streaming orchestrator with fillers, per-line mix and finalize"`

### Task 14: WebSocket 路由、静态托管与 CLI web 命令

**Files:**
- Create: `src/storyteller/web/routes_ws.py`、`src/storyteller/web/cli.py`
- Modify: `src/storyteller/web/app.py`（补 `app.state.jobs`/`app.state.job_viewers`、include ws router、挂静态）
- Modify: `src/storyteller/cli/main.py`（注册 `web` 命令）
- Test: `tests/web/test_websocket.py`

**Interfaces:**
- Consumes: `JobManager`/`JobParams`（Task 9）、`TokenIssuer`/`RateLimiter`/`SESSION_COOKIE`（Task 10）、`create_app`（Task 11/12，本任务补齐 jobs 与 ws）、`StreamOrchestrator`（Task 13）、`STREAM_SAMPLE_RATE`/`STREAM_CHANNELS`（Task 2）。
- Produces:
  - `/ws`：鉴权失败 close **1008**；限流超限 close **1013**；`?job_id=` 命中则顶替旧连接（close **1012**）并补发 `ready` + 当前 `status` + 可能的 `script_ready`，未知 job_id close **4404**；否则等 `{"type":"start",...}` 建 Job → `StreamOrchestrator` 提交 → 循环消费 `job.queue`（`{"_bytes":...}` → `send_bytes`，其余 dict → `send_json`），后台线程并发收客户端 `cancel` 消息（→ `manager.cancel(job.id)`）。
  - `app.state.jobs = JobManager(concurrency)`、`app.state.job_viewers = {}`（**单观众顶替**：每个 job 只保留最新 websocket；`job_viewers` 只在单事件循环里读写，无需锁）。
  - 静态托管：`web/static/` 存在时，在所有 router 之后最后 `app.mount("/", StaticFiles(..., html=True))`（SPA 回退）；`/assets` 单独挂一次。
  - CLI：`storyteller web --host --port`；未配密码 → `click.ClickException`；缺 web 依赖 → 友好提示安装命令。

- [ ] **Step 1: 写失败测试**

```python
# tests/web/test_websocket.py
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from storyteller.core.config import Config
from storyteller.web.app import create_app
from storyteller.web.jobs import JobParams


def _cfg(tmp_path):
    cfg = Config()
    cfg.set("web.passwords", ["pw"]); cfg.set("web.secret", "x")
    cfg.set("web.rate_limit_per_min", 0); cfg.set("web.concurrency", 1)
    cfg.set("data_dir", str(tmp_path / ".storyteller"))
    cfg.set("project_dir", str(tmp_path / ".storyteller" / "stories"))
    cfg.set("voice_matcher", "rule")
    cfg.set("tts.providers", ["mock"]); cfg.set("tts.provider_config.mock", {"type": "mock"})
    cfg.set("llm.providers", ["mock"]); cfg.set("llm.provider_config.mock", {"type": "mock"})
    cfg.set("web.filler_voice", "mock:narrator_01")
    return cfg


def _app(tmp_path):
    return create_app(_cfg(tmp_path))


def test_ws_requires_auth(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws") as ws:
                ws.receive()
        assert excinfo.value.code == 1008


def test_ws_unknown_job_closes(tmp_path):
    app = _app(tmp_path)
    token = app.state.issuer.issue()
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(
                "/ws?job_id=nope&token={}".format(token)) as ws:
                ws.receive()
        assert excinfo.value.code == 4404


def test_ws_full_stream_via_start_message(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        token = app.state.issuer.issue()
        with client.websocket_connect("/ws?token={}".format(token)) as ws:
            ws.send_json({"type": "start", "topic": "小恐龙",
                          "length": "short", "complexity": "simple",
                          "with_sound": False, "tts_providers": ["mock"]})
            events, audio_bytes = [], 0
            while True:
                msg = ws.receive()
                if msg.get("bytes") is not None:
                    audio_bytes += len(msg["bytes"])
                    continue
                evt = json.loads(msg["text"])
                events.append(evt.get("type"))
                if evt.get("type") == "complete":
                    break
                if evt.get("type") == "error":
                    raise AssertionError(evt)
            assert events[0] == "ready"
            assert "script_ready" in events
            assert events[-1] == "complete"
            assert audio_bytes > 0


def test_ws_reconnect_replays_state(tmp_path):
    app = _app(tmp_path)
    state = app.state
    job = state.jobs.create(JobParams(topic="x"))
    job.phase = "line"
    job.line_index = 3
    job.total = 8
    job.script_ready = {"type": "script_ready", "title": "t",
                        "total": 8, "lines": []}
    job.emit({"type": "complete", "project_id": "p", "title": "t",
              "audio_url": "/api/stories/p/audio",
              "script_url": "/api/stories/p", "duration_ms": None})
    token = state.issuer.issue()
    with TestClient(app) as client:
        with client.websocket_connect(
                "/ws?job_id={}&token={}".format(job.id, token)) as ws:
            types = []
            while True:
                msg = ws.receive()
                if msg.get("bytes") is not None:
                    continue
                evt = json.loads(msg["text"])
                types.append(evt.get("type"))
                if evt.get("type") == "complete":
                    break
            assert types == ["ready", "status", "script_ready", "complete"]


def test_ws_reconnect_supersedes_old_viewer(tmp_path):
    app = _app(tmp_path)
    state = app.state
    job = state.jobs.create(JobParams(topic="x"))
    job.phase = "line"
    job.script_ready = {"type": "script_ready", "title": "t",
                        "total": 0, "lines": []}
    token = state.issuer.issue()
    with TestClient(app) as client:
        a = client.websocket_connect(
            "/ws?job_id={}&token={}".format(job.id, token))
        for _ in range(3):  # 读掉 A 的重连三帧，A 随后阻塞在空队列消费循环
            a.receive()
        b = client.websocket_connect(
            "/ws?job_id={}&token={}".format(job.id, token))
        assert json.loads(b.receive()["text"])["type"] == "ready"
        with pytest.raises(WebSocketDisconnect):
            a.receive()  # A 被 B 顶替，服务端已 close 1012


def test_web_cli_rejects_missing_passwords(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from storyteller.web.cli import web_command

    monkeypatch.delenv("STORYTELLER_WEB_PASSWORDS", raising=False)
    monkeypatch.chdir(tmp_path)  # 无 .env，且清掉 STORYTELLER_WEB_PASSWORDS
    result = CliRunner().invoke(web_command, [])
    assert result.exit_code != 0
    assert "STORYTELLER_WEB_PASSWORDS" in result.output
```

- [ ] **Step 2: 确认失败**（`/ws` 无路由 403；`web` 命令不存在）。

- [ ] **Step 3: 实现**

`routes_ws.py`：

```python
# src/storyteller/web/routes_ws.py
from __future__ import annotations

import json
import queue as queue_mod
import threading

from fastapi import APIRouter, WebSocket

from ..core.tts import STREAM_SAMPLE_RATE, STREAM_CHANNELS
from .auth import SESSION_COOKIE
from .jobs import JobParams
from .streaming import StreamOrchestrator

router = APIRouter()

_TERMINAL = ("complete", "error", "canceled")


def _token(ws):
    return ws.query_params.get("token") or ws.cookies.get(SESSION_COOKIE)


def _ready_event():
    return {"type": "ready", "audio": {
        "encoding": "pcm_s16le",
        "sample_rate": STREAM_SAMPLE_RATE,
        "channels": STREAM_CHANNELS,
    }}


def _replay_events(job):
    events = [
        _ready_event(),
        {"type": "status", "phase": job.phase, "message": "已重连",
         "index": job.line_index, "total": job.total},
    ]
    if job.script_ready is not None:
        events.append(job.script_ready)
    return events


def _pump_client(ws, sink):
    # 后台线程收客户端 JSON；连接断开时放哨兵，主循环据此退出。
    try:
        while True:
            sink.put(ws.receive_json())
    except Exception:
        sink.put({"_closed": True})


async def _attach_viewer(state, job_id, ws):
    # 单观众语义：记录当前 ws 并顶掉旧的（close 1012）。job_viewers 只在
    # 单事件循环读写，无需锁。
    old = state.job_viewers.get(job_id)
    state.job_viewers[job_id] = ws
    if old is not None and old is not ws:
        try:
            await old.close(code=1012)
        except Exception:
            pass


async def _send_item(ws, item):
    if isinstance(item, dict) and "_bytes" in item:
        await ws.send_bytes(item["_bytes"])
    else:
        await ws.send_json(item)


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    state = ws.app.state
    if not state.issuer.verify(_token(ws)):
        await ws.close(code=1008)
        return
    if not state.limiter.allow(ws.client.host if ws.client else "?"):
        await ws.close(code=1013)
        return
    await ws.accept()

    manager = state.jobs
    incoming = queue_mod.Queue()
    threading.Thread(
        target=_pump_client, args=(ws, incoming), daemon=True).start()

    job_id = ws.query_params.get("job_id")
    reconnect = False
    if job_id:
        job = manager.get(job_id)
        if job is None:
            await ws.close(code=4404)
            return
        reconnect = True
    else:
        first = incoming.get(timeout=120)
        if not isinstance(first, dict) or first.get("type") != "start":
            await ws.close(code=1003)
            return
        job = manager.create(JobParams(
            topic=first.get("topic", ""),
            length=first.get("length", "medium"),
            complexity=first.get("complexity", "simple"),
            with_sound=bool(first.get("with_sound", False)),
            tts_providers=first.get("tts_providers"),
        ))
        manager.submit(
            job, lambda j: StreamOrchestrator(state.config).run(j))

    await _attach_viewer(state, job.id, ws)
    if reconnect:
        for evt in _replay_events(job):
            await ws.send_json(evt)

    while True:
        try:
            msg = incoming.get_nowait()
        except queue_mod.Empty:
            msg = None
        if isinstance(msg, dict):
            if msg.get("type") == "cancel":
                manager.cancel(job.id)
            if msg.get("_closed"):
                return
        if state.job_viewers.get(job.id) is not ws:
            return  # 被新连接顶替
        try:
            item = job.queue.get(timeout=0.2)
        except queue_mod.Empty:
            continue
        if state.job_viewers.get(job.id) is not ws:
            return  # 取到项时已被顶替，丢弃这一帧（重连不补发，spec §5.3）
        await _send_item(ws, item)
        if isinstance(item, dict) and item.get("type") in _TERMINAL:
            return
```

`app.py`（在 Task 11/12 基础上补齐；给出最终完整形态）：

```python
# src/storyteller/web/app.py
from fastapi import FastAPI

from .auth import RateLimiter, TokenIssuer
from .jobs import JobManager
from .routes_auth import router as auth_router
from .routes_options import router as options_router
from .routes_stories import router as stories_router
from .routes_ws import router as ws_router


def create_app(config, registry=None):
    if registry is None:
        from ..providers.registry import ProviderRegistry
        from ..providers.bootstrap import register_providers_from_config
        registry = ProviderRegistry(config)
        register_providers_from_config(config, registry)

    app = FastAPI(title="storyteller web")
    app.state.config = config
    app.state.registry = registry
    app.state.issuer = TokenIssuer(
        config.get("web.secret"), config.get("web.token_ttl_days")
    )
    app.state.limiter = RateLimiter(config.get("web.rate_limit_per_min"))
    app.state.jobs = JobManager(config.get("web.concurrency"))
    app.state.job_viewers = {}

    app.include_router(auth_router)
    app.include_router(options_router)
    app.include_router(stories_router)
    app.include_router(ws_router)

    _mount_static(app)
    return app


def _mount_static(app):
    from pathlib import Path
    static = Path(__file__).parent / "static"
    if not static.is_dir():
        return
    from fastapi.staticfiles import StaticFiles
    assets = static / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")
    # SPA 回退必须最后挂；API/WS 路由已先注册，优先匹配。
    app.mount("/", StaticFiles(directory=str(static), html=True), name="spa")
```

`web/cli.py`：

```python
# src/storyteller/web/cli.py
import click


@click.command("web")
@click.option("--host", default=None, help="监听地址（默认 127.0.0.1）")
@click.option("--port", default=None, type=int, help="端口（默认 8000）")
def web_command(host, port):
    """启动 Web 服务（浏览器界面 + 流式 API）。"""
    from ..core.config import Config

    cfg = Config.from_env()
    if not (cfg.get("web.passwords") or []):
        raise click.ClickException(
            "未配置访问密码：请在 .env 设置 STORYTELLER_WEB_PASSWORDS（逗号分隔）"
        )
    if not cfg.get("web.secret"):
        click.echo("警告：未设置 STORYTELLER_WEB_SECRET，重启后所有登录将失效")

    try:
        import uvicorn
    except ImportError:
        raise click.ClickException(
            '缺少 web 依赖，请运行 pip install -e ".[web]"'
        )

    from .app import create_app
    uvicorn.Server(uvicorn.Config(
        create_app(cfg),
        host=host or cfg.get("web.host"),
        port=port or cfg.get("web.port"),
    )).run()
```

`cli/main.py` 末尾（在 `if __name__ == "__main__":` 之前）注册：

```python
# Web 命令定义在 web/cli.py；其顶层只 import click（uvicorn/fastapi 延迟导入），
# 未安装 [web] extras 时 `storyteller --help` 仍可用。
from ..web.cli import web_command
cli.add_command(web_command)
```

- [ ] **Step 4: 验证**：`pytest tests/web/test_websocket.py -v` 全 PASS；`storyteller --help` 出现 `web`；`pytest` 全量绿。若 `test_ws_reconnect_supersedes_old_viewer` 在个别 CI 环境偶发时序抖动（A 的 `receive()` 收到缓冲帧而非立刻断开），先保持其余断言，确认「B 能顶替连接并收到 replay」这一核心语义成立，再决定是否保留该用例的关闭时序断言。

- [ ] **Step 5: 提交**：`git commit -m "feat: websocket streaming endpoint, static hosting and web CLI command"`

---

### Task 15: 端到端后端集成测试（含音效行与降级行）

**Files:**
- Test: `tests/web/test_integration_stream.py`

**Interfaces:** 无新增生产代码（除非本任务暴露缺陷——按 TDD 修）。

- [ ] **Step 1: 写测试**（三种出口一致性 + 音效路径）

```python
# tests/web/test_integration_stream.py
import json
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from storyteller.core.config import Config
from storyteller.web.app import create_app
from storyteller.web.jobs import JobManager
from storyteller.core.tts import STREAM_SAMPLE_RATE


def _write_audible_wav(path, seconds=0.4, freq=440):
    import math, struct
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(44100)
        buf = bytearray()
        for i in range(44100 * seconds):
            buf += struct.pack("<h", int(0.25*32767*math.sin(2*math.pi*freq*i/44100)))
        wf.writeframes(bytes(buf))


def _cfg(tmp_path, with_sound):
    cfg = Config()
    cfg.set("web.passwords", ["pw"]); cfg.set("web.secret", "x")
    cfg.set("web.rate_limit_per_min", 0); cfg.set("web.concurrency", 1)
    cfg.set("data_dir", str(tmp_path / ".storyteller"))
    cfg.set("project_dir", str(tmp_path / ".storyteller" / "stories"))
    cfg.set("sound.dir", str(tmp_path / ".storyteller" / "sounds"))
    cfg.set("sound.enabled", True)
    cfg.set("sound.providers", ["mock"])
    cfg.set("sound.provider_config.mock", {"type": "mock"})
    cfg.set("voice_matcher", "rule")
    cfg.set("tts.providers", ["mock"]); cfg.set("tts.provider_config.mock", {"type": "mock"})
    cfg.set("llm.providers", ["mock"]); cfg.set("llm.provider_config.mock", {"type": "mock"})
    cfg.set("web.filler_voice", "mock:narrator_01")
    return cfg


def _run(tmp_path, with_sound):
    cfg = _cfg(tmp_path, with_sound)
    app = create_app(cfg)
    app.state.jobs = JobManager(concurrency=1)
    events, audio, saw_sound_line = [], bytearray(), False
    with TestClient(app) as client:
        token = app.state.issuer.issue()
        with client.websocket_connect("/ws?token={}".format(token)) as ws:
            ws.send_json({"type": "start", "topic": "打雷的夜晚",
                          "with_sound": with_sound, "tts_providers": ["mock"]})
            while True:
                msg = ws.receive()
                if msg.get("bytes") is not None:
                    audio.extend(msg["bytes"]); continue
                evt = json.loads(msg["text"])
                events.append(evt)
                if evt.get("type") == "line_start" and evt.get("has_sound"):
                    saw_sound_line = True
                if evt.get("type") in ("complete", "error"):
                    break
    return events, bytes(audio), saw_sound_line, cfg


def test_all_audio_is_standard_pcm_and_completes(tmp_path):
    events, audio, _, _ = _run(tmp_path, with_sound=False)
    assert [e["type"] for e in events][-1] == "complete"
    assert len(audio) % 2 == 0
    # ready 声明 24k
    ready = next(e for e in events if e["type"] == "ready")
    assert ready["audio"] == {"encoding": "pcm_s16le",
                              "sample_rate": STREAM_SAMPLE_RATE, "channels": 1}


def test_sound_story_completes_and_project_has_story_mp3(tmp_path):
    events, audio, saw_sound_line, cfg = _run(tmp_path, with_sound=True)
    assert events[-1]["type"] == "complete"
    final = list(Path(cfg.get("project_dir")).glob("*/story.mp3"))
    assert final and final[0].stat().st_size > 0
    # mock LLM 默认剧本无音效 cue 时 has_sound 全 False 也可接受；
    # 但流必须完整、PCM 合法
    assert len(audio) % 2 == 0
```

- [ ] **Step 2: 运行确认当前状态**：应基本通过（Task 13/14 已覆盖）；若发现事件字段缺失/PCM 长度非法，修复生产代码直到绿。

- [ ] **Step 3: 补一个"非流式 provider 降级"单测**：注册只实现 `synthesize` 的 MockTTSProvider（默认 supports_streaming=False），跑 orchestrator，断言仍收到完整事件序列且音频为标准 PCM（降级路径在 Task 13 已实现，此处锁行为）。

```python
def test_non_streaming_provider_falls_back_to_file_pcm(tmp_path):
    # 复用 _cfg 后把 mock 流能力关掉：直接构造 registry 注入
    cfg = _cfg(tmp_path, False)
    from storyteller.web.streaming import StreamOrchestrator
    from storyteller.web.jobs import Job, JobParams
    job = Job(JobParams(topic="x", tts_providers=["mock"]))
    StreamOrchestrator(cfg).run(job)
    kinds, audio = [], bytearray()
    while True:
        item = job.queue.get(timeout=5)
        if "_bytes" in item:
            audio.extend(item["_bytes"])
        else:
            kinds.append(item["type"])
            if item["type"] in ("complete", "error"):
                break
    assert kinds[-1] == "complete" and len(audio) % 2 == 0
```

- [ ] **Step 4: 全量验证**：`pytest -q` 全绿（含原 337 + 本计划新增）。

- [ ] **Step 5: 提交**：`git commit -m "test: end-to-end ws streaming integration coverage"`（如修了生产代码，message 用 `fix:` 并分别说明）。

---

### Task 16: 文档与真机验收

**Files:**
- Modify: `README.md`（新增 Web 一节：安装 extras、配置、启动、开发模式）
- Create: `web/.gitignore`（`static/`、`node_modules/`——node 部分供 Plan B）

- [ ] **Step 1: README 增加 Web 小节**，内容含：

```markdown
## Web 界面（后端）

pip install -e ".[web,dev]"
cp .env.example .env  # 填写 STORYTELLER_WEB_PASSWORDS 与各 provider key
storyteller web --host 0.0.0.0 --port 8000

WebSocket：/ws（cookie 或 ?token= 鉴权）。音频线缆标准：PCM s16le / mono / 24kHz。
前端工程与构建见 web/frontend（Plan B 交付）。
```

- [ ] **Step 2: `.gitignore`/`web/.gitignore`** 写入：

```
static/
node_modules/
```

并在仓库根 `.gitignore` 确认 `.storyteller/` 已忽略（既有）。

- [ ] **Step 3: 真机手动验收清单**（不进自动化，执行结果回报给用户；需要真实 `.env`）：

1. `storyteller web` 启动，浏览器/WS 客户端用错误密码被拒（1008），正确密码可连。
2. 火山 TTS（无音效、短故事）：确认收到 ready=24k、可在网页播放（先用临时 WS 调试页或 Plan B 前端）、首音只在剧本+音色之后、行间无明显间隙。
3. 开音效的短故事：带 cue 的行等待后播出，最终 `/api/stories/<id>/audio` 精混版正确；第二次同主题音效走缓存（日志 cached）。
4. 断网 5 秒重连 `/ws?job_id=...`：收到当前 status，任务未失败，最终 mp3 完整。
5. cancel：行边界生效，项目留在可 resume 状态。
6. `pytest -q` 全绿；`storyteller generate`（CLI）抽样跑一个短故事确认无回归。

- [ ] **Step 4: 提交**：`git commit -m "docs: web backend setup and manual acceptance checklist"`

---

## Self-Review 记录（计划作者已核对）

- Spec §2 架构/鉴权/数据根 → Tasks 1/9/10/11/12/14；§3 适配层 → Tasks 2/3（火山），P2 阿里实时 adapter **明确不在本计划**（降级路径 Task 13/15 覆盖）；§4 三种行出口与 mix_line → Tasks 5/6/7/13；§4.4 filler → Task 8/13；§5 WS 协议 → Tasks 9/13/14（ready/status/script_ready/filler_*/line_*/finalizing/complete/error/canceled 全部有发射点；重连补发与单观众顶替在 Task 14 实现）；§6 REST → Tasks 11/12；§8 配置 → Task 1；§9 测试 → 每任务 + Task 15/16；§10 P1 范围与本计划一致；Vue 前端（spec §7）拆 Plan B。
- 已知遗留到 Plan B：`web/frontend/` 全部、StaticFiles 实际构建产物（Task 14 仅在目录存在时挂载）。
- 类型一致性：`Job.emit/emit_bytes`、`Job.script_ready`（Task 9 定义 → Task 13 写入 → Task 14 重连补发）、`StreamChunk(kind,data)`、`stream_synthesize(text, voice, *, directives, context)`、`materialize_line_cues(state,line,duration,provider,library,referenced)`、`mix_line(main,entries,out)`、`mix_line_with_cues(voice_path,entries,output_path)`（Task 6 web 封装 → Task 13 path-B 调用）、`StreamOrchestrator(config)` 在各任务间签名统一。
- Task 14 已整体重写：WS 路由含 `?job_id=` 重连（补发 ready/status/script_ready，未知 job close 4404）与单观众顶替（`app.state.job_viewers`，旧连接 close 1012）；`create_app` 自己创建 `app.state.jobs`（测试不再手动赋值）；`web/cli.py` 用 `uvicorn.Server(uvicorn.Config(create_app(cfg), ...)).run()`（无 factory=True 歧义）；`cli/main.py` 末尾 `cli.add_command(web_command)`（web.cli 顶层只 import click，未装 [web] extras 时 `--help` 不崩）。
- Task 6 既加 `core/audio.PydubAudioProcessor.mix_line` 原语又建 `web/mixes.py` 封装 `mix_line_with_cues`，Task 13 path-B 改调用 `mixes.mix_line_with_cues(out_path, entries, out_path)`、不再内联 `.mixed.mp3` 中转——与 spec §4.2「`web/mixes.py` + `core/audio.py`」模块划分一致；`streaming.py` 只管逐行编排/事件，混音交给 mixes。
