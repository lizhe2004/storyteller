# 阿里云 TTS Provider 收尾验证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对已实现的阿里云百炼 Qwen-Audio-TTS provider 做真机验证，修复发现的集成问题（如有），然后提交。

**Architecture:** v1 代码已存在于工作区（未提交）：`providers/aliyun/` 走非流式 SpeechSynthesizer HTTP 接口，POST 合成后立即下载 24 小时有效的音频 URL；音色目录 11 个系统音色，每条记录自带模型归属。本计划只做「真实 API 验证 → （条件性）TDD 修复 → 打包校验 → 提交」，不重写已有实现。

**Tech Stack:** Python ≥3.8、requests（不引入 dashscope SDK）、pytest、ffprobe（已安装于 /opt/homebrew/bin）、pydub。

**Spec:** 无独立 spec 文件——bounded 路径，设计于 2026-09-11 在对话中批准。关键决策记录在本计划的 Global Constraints 与 `src/storyteller/providers/aliyun/tts.py` 模块 docstring。

## Global Constraints

- 运行测试统一用仓库 venv：`.venv/bin/python -m pytest`
- 密钥只从环境变量读：provider 经配置读 `STORYTELLER_TTS_ALIYUN_API_KEY`（`AliyunTTS` 自身不读 `DASHSCOPE_API_KEY`，仅 Task 1 的手动冒烟脚本做该回退）；**禁止**把 key 写进任何入库文件，`.env` 已被 gitignore
- 需要**华北2（北京）地域**的百炼 API Key；plus 与 flash 模型均仅北京地域可用
- 端点路径固定 `/api/v1/services/audio/tts/SpeechSynthesizer`，通用域名 `https://dashscope.aliyuncs.com` 与 `{WorkspaceId}.cn-beijing.maas.aliyuncs.com` 都要支持
- 非流式响应取 `output.audio.url`，必须立即 GET 下载落盘（URL 24h 过期）；超时 POST 120s / GET 60s
- 音量映射：VoiceConfig 倍率 → 阿里云 0–100（中值 50），`round((volume-1)*50)+50`；rate/pitch 原生 0.5–2.0 倍率直接透传；默认值（1.0/1.0/1.0）不出现在请求体
- 演法指令 directives → 单个 `instruction`（去 `#` 前缀、中文逗号拼接）；引用上文 context 丢弃
- 目录只含 11 个中文/双语系统音色，**不含** 3 个纯英文音色（匹配器不按语言过滤候选池）
- 任何代码修复必须先写失败的单测（FakeSession 风格，见 `tests/unit/test_aliyun_tts.py`），严禁无测试改生产代码
- 真机脚本是手动验证工具，不加入自动化测试套件

---

### Task 1: 编写真机冒烟脚本（不触网即可入库）

**Files:**
- Create: `scripts/aliyun_tts_smoke.py`

**Interfaces:**
- Consumes: `AliyunTTS(config)`（`src/storyteller/providers/aliyun/tts.py`），构造读取 `tts.provider_config.aliyun.{api_key,endpoint,model}`；`synthesize(text, VoiceConfig, Path, directives=[...]) -> Path`
- Produces: 命令行脚本；3 个 mp3 产物写到 `.storyteller/smoke/`（该目录已被 .gitignore 覆盖）

- [ ] **Step 1: 创建脚本**

写入 `scripts/aliyun_tts_smoke.py`：

```python
"""Manual real-API smoke for the Aliyun Qwen-Audio-TTS provider.

Usage:
    STORYTELLER_TTS_ALIYUN_API_KEY=sk-xxx \\
        .venv/bin/python scripts/aliyun_tts_smoke.py

Not part of the automated suite. Requires a Beijing-region Bailian key.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from pathlib import Path

from storyteller.core.config import Config
from storyteller.core.models import VoiceConfig
from storyteller.providers.aliyun.tts import AliyunTTS

# (voice_id, output stem, text, directives) — covers flash female,
# flash child, and a plus-only flagship voice (model routing by catalog).
CASES = [
    (
        "longanhuan_v3.6",
        "aliyun_flash_female",
        "今天天气真不错，我们一起去森林里玩吧。",
        ["开心地说，语速轻快"],
    ),
    (
        "longjielidou_v3.6",
        "aliyun_flash_child",
        "等等我呀，我也想一起去森林里玩！",
        ["天真急切的小男孩语气"],
    ),
    (
        "longanlingxin",
        "aliyun_plus_female",
        "夜深了，把今天的烦恼都放下，好好睡一觉吧。",
        ["温柔轻声地安慰"],
    ),
]

OUT_DIR = Path(".storyteller/smoke")


def _ffprobe(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-print_format", "json",
            "-show_streams", "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError("ffprobe failed: {}".format(result.stderr))
    return json.loads(result.stdout)


def main():
    api_key = (
        os.getenv("STORYTELLER_TTS_ALIYUN_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
    )
    if not api_key:
        print(
            "SKIP: set STORYTELLER_TTS_ALIYUN_API_KEY "
            "(Beijing-region Bailian key) to run this smoke."
        )
        return 2

    config = Config()
    provider_config = {
        "api_key": api_key,
        "model": "qwen-audio-3.0-tts-flash",
    }
    endpoint = os.getenv("STORYTELLER_TTS_ALIYUN_ENDPOINT")
    if endpoint:
        provider_config["endpoint"] = endpoint
    config.set("tts.provider_config.aliyun", provider_config)

    tts = AliyunTTS(config)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    failures = 0
    for voice_id, stem, text, directives in CASES:
        out_path = OUT_DIR / "{}.mp3".format(stem)
        try:
            tts.synthesize(
                text,
                VoiceConfig(provider="aliyun", voice_id=voice_id),
                out_path,
                directives=directives,
            )
            probe = _ffprobe(out_path)
            stream = probe["streams"][0]
            duration = float(probe["format"]["duration"])
            assert out_path.stat().st_size > 1000, "file suspiciously small"
            assert stream["codec_name"] == "mp3", stream["codec_name"]
            assert int(stream["sample_rate"]) == 24000, stream["sample_rate"]
            assert duration > 0.5, duration
            print(
                "PASS {:24s} {:6.1f}s  {:>7d} bytes  {}".format(
                    voice_id, duration, out_path.stat().st_size, out_path
                )
            )
        except Exception as exc:
            failures += 1
            print("FAIL {}: {}".format(voice_id, exc))

    if failures:
        print("{} of {} cases failed".format(failures, len(CASES)))
        return 1
    print("All cases passed. Listen to the 3 files above to judge quality.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 无 key 运行，验证友好退出**

Run: `.venv/bin/python scripts/aliyun_tts_smoke.py`
Expected: 打印 `SKIP: set STORYTELLER_TTS_ALIYUN_API_KEY ...`，退出码 2，不产生任何网络请求（可用 `echo $?` 确认退出码）

- [ ] **Step 3: 确认单测仍全绿（脚本未触碰包代码）**

Run: `.venv/bin/python -m pytest tests/unit/test_aliyun_tts.py tests/unit/test_aliyun_voice_catalog.py -q`
Expected: `25 passed`

- [ ] **Step 4: Commit 脚本**

```bash
git add scripts/aliyun_tts_smoke.py
git commit -m "test: add manual real-API smoke script for aliyun TTS"
```

---

### Task 2: 真机合成三条用例并人工试听

**Files:**
- 无代码改动；产物在 `.storyteller/smoke/`（gitignored）

**Interfaces:**
- Consumes: Task 1 的脚本；真实百炼服务

- [ ] **Step 1: 运行真机冒烟**

Run:

```bash
STORYTELLER_TTS_ALIYUN_API_KEY=sk-真实key \
    .venv/bin/python scripts/aliyun_tts_smoke.py
```

Expected: 三行 `PASS`，每个文件 24kHz mp3、时长 > 0.5s。

若出现 401/403：Key 错误或非北京地域 Key——更换后重跑，不改代码。
若出现 `InvalidParameter` 且消息指向 voice/model：对照 `src/storyteller/providers/aliyun/voices.json` 里的 model 字段排查，进入 Task 3。
若出现连接/超时：先确认网络能到 `dashscope.aliyuncs.com`（`curl -I https://dashscope.aliyuncs.com`），排除代理问题后再判定代码问题。

- [ ] **Step 2: 人工试听三个文件**

依次播放 `.storyteller/smoke/aliyun_flash_female.mp3`、`aliyun_flash_child.mp3`、`aliyun_plus_female.mp3`，核对：

- 文本朗读完整、无明显漏字/重复
- `aliyun_flash_child.mp3` 确实是男童声（不是成年男声）
- 三个用例的语气能听出 directive 的差异（开心轻快 / 天真急切 / 温柔轻声）；语气偏弱记为**已知局限**，不阻塞收尾（`[excited]` 等文本标签增强是后续独立工作）

- [ ] **Step 3: （可选）WorkspaceId 专属域名验证**

Run:

```bash
STORYTELLER_TTS_ALIYUN_API_KEY=sk-真实key \
STORYTELLER_TTS_ALIYUN_ENDPOINT=https://真实WorkspaceId.cn-beijing.maas.aliyuncs.com \
    .venv/bin/python scripts/aliyun_tts_smoke.py
```

Expected: 同样 3 个 PASS。没有 WorkspaceId 就跳过本步（通用域名已在 Step 1 验证）。

---

### Task 3: 条件性 TDD 修复（仅当 Task 2 发现代码问题）

仅当真实 API 行为与单元测试的假设不符时执行。若真机全部通过，**跳过本任务**。

**Files:**
- Test first: `tests/unit/test_aliyun_tts.py`
- Modify: `src/storyteller/providers/aliyun/tts.py`（或 `voices.json`）

**Interfaces:**
- Consumes: Task 2 记录的真实请求/响应原文（先在失败用例上用 `curl` 复现并保存完整响应体）
- Produces: 修复后的 provider，新单测锁定真实契约

- [ ] **Step 1: 用 curl 固化真实响应**

对失败用例发等价 curl（替换 key 与 voice），保存完整响应：

```bash
curl -sS -X POST 'https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer' \
  -H "Authorization: Bearer $STORYTELLER_TTS_ALIYUN_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen-audio-3.0-tts-flash","input":{"text":"测试","voice":"longanhuan_v3.6","format":"mp3","sample_rate":24000}}'
```

确认分歧点（字段名、嵌套位置、错误信封结构等），记录在测试 docstring 里。

- [ ] **Step 2: 写失败单测复现真实响应**

在 `tests/unit/test_aliyun_tts.py` 追加测试，`_FakeResponse(...)` 的 payload **逐字镜像** Step 1 的真实 JSON 结构。例如若真实错误信封不是 `message` 字段：

```python
def test_synthesize_surfaces_real_error_envelope(tmp_path):
    tts = AliyunTTS(_config())
    tts._session = _FakeSession(
        _FakeResponse(400, payload={"code": "InvalidParameter",
                                    "message": "实际错误原文"}),
        _FakeResponse(200, content=b"x"),
    )
    with pytest.raises(TTSError, match="实际错误原文"):
        tts.synthesize("你好", _voice(), tmp_path / "out.mp3")
```

- [ ] **Step 3: 运行确认 RED**

Run: `.venv/bin/python -m pytest tests/unit/test_aliyun_tts.py -q`
Expected: 新测试 FAIL，且失败原因正是真机观察到的分歧

- [ ] **Step 4: 最小修复**

只改让新测试通过的最少代码（如调整 `output.audio.url` 取值路径、`_error_detail` 的字段名）。不顺手重构。

- [ ] **Step 5: 运行确认 GREEN**

Run: `.venv/bin/python -m pytest tests/unit/test_aliyun_tts.py -q`
Expected: 全部 PASS

- [ ] **Step 6: 重跑真机脚本确认修复**

Run: Task 2 Step 1 的命令
Expected: 3 个 PASS、试听正常

- [ ] **Step 7: Commit**

```bash
git add tests/unit/test_aliyun_tts.py src/storyteller/providers/aliyun/
git commit -m "fix: align aliyun TTS with real API contract (<一句话分歧>)"
```

---

### Task 4: wheel 打包校验（voices.json 必须进包）

**Files:**
- 无改动（`pyproject.toml` 的 package-data 已在工作区改好）

- [ ] **Step 1: 构建 wheel 并检查内容**

Run:

```bash
rm -rf /tmp/storyteller-wheels \
  && .venv/bin/pip wheel . --no-deps -w /tmp/storyteller-wheels >/dev/null 2>&1 \
  && unzip -l /tmp/storyteller-wheels/storyteller-*.whl | grep -E "aliyun/(tts.py|voices.json)"
```

Expected: 同时列出 `storyteller/providers/aliyun/tts.py` 和 `storyteller/providers/aliyun/voices.json` 两行。若缺 voices.json，检查 `pyproject.toml` 的 `[tool.setuptools.package-data]` 是否含 `"storyteller.providers.aliyun" = ["voices.json"]`。

- [ ] **Step 2: 全量测试**

Run: `.venv/bin/python -m pytest -q`
Expected: `260 passed`（若 Task 3 新增了测试则为 260+N passed），无 warning

---

### Task 5: 提交 v1 全部改动

**Files:**
- `src/storyteller/providers/aliyun/__init__.py`、`tts.py`、`voices.json`
- `src/storyteller/providers/bootstrap.py`
- `tests/unit/test_aliyun_tts.py`、`tests/unit/test_aliyun_voice_catalog.py`、`tests/unit/test_bootstrap.py`
- `pyproject.toml`、`.env.example`、`README.md`

- [ ] **Step 1: 检查待提交内容**

Run: `git status --short && git diff --stat`
Expected: 只含上述文件；确认 **没有** `.env`、`.storyteller/`、`/tmp` 产物

- [ ] **Step 2: 暂存并提交**

```bash
git add src/storyteller/providers/aliyun/ \
  src/storyteller/providers/bootstrap.py \
  tests/unit/test_aliyun_tts.py \
  tests/unit/test_aliyun_voice_catalog.py \
  tests/unit/test_bootstrap.py \
  pyproject.toml .env.example README.md
git commit -m "feat: add Aliyun Bailian Qwen-Audio-TTS provider"
```

- [ ] **Step 3: 验证工作区干净**

Run: `git status --short`
Expected: 无输出（Task 1 的脚本已在 Task 1 单独提交）

---

### Task 6: 更新项目记忆

**Files:**
- Modify: `/Users/lizhe/.claude/projects/-Users-lizhe-Documents-workspace-audio-story-generator/memory/storyteller-project.md`

- [ ] **Step 1: 在「已确认的设计决策」追加一条阿里云 provider 记录**

在火山 TTS 配置记录之后追加一段（事实以后以代码为准，这里只记跨会话有用的决策与坑）：

```markdown
- 阿里云百炼 TTS（2026/09/11 接入，v1=Qwen-Audio-TTS 系列）：provider 名 `aliyun`，
  `STORYTELLER_TTS_ALIYUN_TYPE=aliyun` + API_KEY/MODEL/ENDPOINT 注册；非流式
  SpeechSynthesizer 接口（POST 后取 output.audio.url 立即下载，URL 24h）。
  rate/pitch 原生 0.5–2.0 倍率直接透传，volume 换算 0–100（中值 50）；
  directives 拼成单个 instruction（去#、逗号拼接），引用上文丢弃。
  voices.json 11 个中文/双语系统音色（plus 2 + flash 9，含 3 童声），
  每条带 model 归属（plus/flash 音色不可混用）；3 个纯英文音色刻意不收
  （匹配器不按语言过滤候选池）。无「有声阅读」类，多 provider 时旁白优先落火山。
  同端点预留 CosyVoice 扩展；情感标签 [excited] 等留待真机试听后再做。
  真机验证：<填日期与结论>
```

- [ ] **Step 2: 填入真机结论**

把 `<填日期与结论>` 替换为 Task 2 的实际结果（3 个用例 PASS、童声/指令听感如何）。
