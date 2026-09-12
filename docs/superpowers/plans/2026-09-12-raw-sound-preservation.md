# 原始音效保留与项目内聚 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每个音效 cue 的原始音频（含响度不合格的废片）都以 cue 中文名保存到项目目录且永不删除；全局音效库仍只收录通过响度闸门的素材；缓存命中也复制中文名副本到项目；make-sound 废片保留在 `sounds/raw/` 并以非零退出码报告。

**Architecture:** 把 `SoundLibrary.get_or_create`（生成→闸门→入库 三合一）拆成 `find`（指纹查询）+ `admit`（对已生成文件做闸门，合格则**复制**入库，不合格抛错且不删源文件）。pipeline 先把音频生成到 `stories/<proj>/sounds/<中文名>.mp3`，再调 `admit`；make-sound 生成到 `sounds/raw/`，`admit` 成功后删暂存、失败保留。

**Tech Stack:** Python、pydub、pytest（CliRunner e2e）、纯本地 mock，无真实 API。

**Spec:** `docs/superpowers/specs/2026-09-12-raw-sound-preservation-design.md`

## Global Constraints

- 测试一律用主仓库 venv：`/Users/lizhe/Documents/workspace/audio-story-generator/.venv/bin/python -m pytest`，在 worktree 内运行（pytest ini `pythonpath=["src"]` 解析 worktree src）。
- 不允许任何真实 API 调用；音效一律用 mock（可闻 440Hz 正弦音）或本地静音 stub。
- 响度闸门阈值与判定不变：`MIN_SOUND_DBFS = -55.0`，不可解码或 ≤ -55 dBFS 即不合格。
- 全局库语义不变：`index.json` 记录结构、指纹算法 `sha256(model|归一化prompt|format)`、`snd_<id>` 文件名、跨项目缓存命中零调用。
- 关键行为变化：合格素材是**复制**入库（源文件保留在项目/raw），不是移动；任何路径都不再删除用户项目里的音频。
- 严格 TDD：先写测试看 RED，再实现看 GREEN；每个任务结束跑全量套件。
- 基线：main @ 3caaa10，286 passed。
- 提交只 add 本任务点名的文件。

---

### Task 1: SoundLibrary 拆分 find/admit 与文件名工具

**Files:**
- Modify: `src/storyteller/core/sound_library.py`
- Test: `tests/unit/test_sound_library.py`（整体改写为新 API 测试）
- Create: `tests/unit/test_sound_paths.py`

**Interfaces:**
- Consumes: provider 对象的 `.name` / `.model` 属性、`generate_id`、`_measure_dbfs`、`MIN_SOUND_DBFS`、`SoundGenerationError`（均已存在）。
- Produces:
  - `safe_sound_name(name, fallback="sound") -> str`：跨平台安全文件名词干。
  - `unique_path(directory, stem, ext) -> pathlib.Path`：不存在则返回 `directory/stem.ext`，重名追加 `-2`、`-3`…
  - `SoundLibrary.find(provider, prompt, audio_format="mp3") -> dict|None`：指纹命中**且库文件存在**返回 record，否则 None；空 prompt 抛 ValueError。
  - `SoundLibrary.admit(source_path, provider, *, prompt, name, kind="sfx", description="", tags=None, audio_format="mp3", duration=None) -> dict`：对源文件做闸门；不合格抛 `SoundGenerationError`（文案含源文件路径，**不删源文件**、不写 index）；合格则 `shutil.copy2` 入库为 `snd_<id>.<ext>`、写 index、返回 record。
  - `get_or_create` 本任务**保留不动**（仍被 pipeline/main 调用），Task 3 删除。

- [ ] **Step 1: 新建文件名工具测试**

创建 `tests/unit/test_sound_paths.py`：

```python
import pytest

from storyteller.core.sound_library import safe_sound_name, unique_path


def test_safe_sound_name_strips_illegal_characters():
    assert safe_sound_name('风吹/树叶:沙沙?') == "风吹_树叶_沙沙_"
    assert safe_sound_name('  雨声  ') == "雨声"
    assert safe_sound_name('a\\b*c') == "a_b_c"


def test_safe_sound_name_falls_back_when_empty():
    assert safe_sound_name("", fallback="sfx_abc123") == "sfx_abc123"
    assert safe_sound_name("   ", fallback="x") == "x"
    assert safe_sound_name(None) == "sound"
    assert safe_sound_name("...") == "sound"


def test_safe_sound_name_collapses_inner_whitespace():
    assert safe_sound_name("猴子  捞月\n") == "猴子 捞月"


def test_unique_path_appends_counter_on_collision(tmp_path):
    first = unique_path(tmp_path, "雨声", "mp3")
    first.write_bytes(b"a")
    second = unique_path(tmp_path, "雨声", "mp3")
    second.write_bytes(b"b")
    third = unique_path(tmp_path, "雨声", "mp3")
    assert first.name == "雨声.mp3"
    assert second.name == "雨声-2.mp3"
    assert third.name == "雨声-3.mp3"


def test_unique_path_creates_no_files(tmp_path):
    path = unique_path(tmp_path / "sounds", "雷声", "mp3")
    assert not path.exists()
    assert path.parent == tmp_path / "sounds"
```

- [ ] **Step 2: 运行确认 RED**

Run: `/Users/lizhe/Documents/workspace/audio-story-generator/.venv/bin/python -m pytest tests/unit/test_sound_paths.py -q`
Expected: FAIL（ImportError，函数不存在）。

- [ ] **Step 3: 实现文件名工具**

在 `src/storyteller/core/sound_library.py` 顶部 import 区加 `import shutil`，并在 `fingerprint_for` 之后加：

```python
_UNSAFE_NAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_sound_name(name, fallback="sound"):
    """Turn a cue name into a cross-platform filename stem (no extension)."""
    text = _UNSAFE_NAME_RE.sub("_", str(name or ""))
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or fallback


def unique_path(directory, stem, ext):
    """Return directory/<stem>.<ext>, appending -2/-3... when it exists."""
    directory = Path(directory)
    candidate = directory / "{}.{}".format(stem, ext)
    counter = 2
    while candidate.exists():
        candidate = directory / "{}-{}.{}".format(stem, counter, ext)
        counter += 1
    return candidate
```

- [ ] **Step 4: 运行确认 GREEN**

Run: `/Users/lizhe/Documents/workspace/audio-story-generator/.venv/bin/python -m pytest tests/unit/test_sound_paths.py -q`
Expected: 5 passed。

- [ ] **Step 5: 整体改写 test_sound_library.py 为 find/admit 测试**

把 `tests/unit/test_sound_library.py` 整体替换为：

```python
import json

import pytest

from storyteller.core.sound_library import (
    MIN_SOUND_DBFS,
    SoundLibrary,
    fingerprint_for,
    normalize_prompt,
)


class _StubProvider:
    """Only the identity attributes find()/admit() hash on."""

    name = "fake"
    model = "fake-model-1"


def _write_tone(path, *, gain=0, duration_ms=200, freq=440):
    from pydub.generators import Sine

    path = path if hasattr(path, "parent") else __import__("pathlib").Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Sine(freq).to_audio_segment(duration=duration_ms).apply_gain(gain).export(
        str(path), format="wav"
    )
    return path


def test_admit_copies_audible_clip_into_library_and_keeps_source(tmp_path):
    library = SoundLibrary(tmp_path / "sounds")
    raw = _write_tone(tmp_path / "project" / "sounds" / "笛声.mp3")
    provider = _StubProvider()

    record = library.admit(
        raw, provider, prompt="远处的笛声", name="笛声", kind="ambient",
        description="悠扬笛声", tags=["古风", "宁静"], duration=1.5,
    )

    assert record["name"] == "笛声"
    assert record["kind"] == "ambient"
    assert record["description"] == "悠扬笛声"
    assert record["tags"] == ["古风", "宁静"]
    assert record["model"] == "fake-model-1"
    assert record["duration"] == 1.5
    assert record["prompt"] == "远处的笛声"
    assert record["fingerprint"]
    assert record["path"].startswith("snd_")
    # Library copy exists AND the project raw clip was copied, not moved.
    assert library.path_for(record).exists()
    assert raw.exists()
    assert len(library.all()) == 1


def test_find_returns_cached_record_and_skips_missing_file(tmp_path):
    library = SoundLibrary(tmp_path / "sounds")
    raw = _write_tone(tmp_path / "雨声.mp3")
    record = library.admit(
        raw, _StubProvider(), prompt="下雨声", name="雨声", kind="ambient"
    )

    found = library.find(_StubProvider(), "下雨声")
    assert found is not None
    assert found["id"] == record["id"]
    assert library.find(_StubProvider(), "雷声") is None

    # Index entry whose file vanished is treated as a miss.
    library.path_for(record).unlink()
    assert library.find(_StubProvider(), "下雨声") is None


def test_find_normalizes_prompt_and_format_participates(tmp_path):
    library = SoundLibrary(tmp_path / "sounds")
    _write_tone(tmp_path / "a.mp3")
    library.admit(
        tmp_path / "a.mp3", _StubProvider(),
        prompt="微风  鸟鸣", name="a", kind="ambient",
    )
    assert library.find(_StubProvider(), " 微风 鸟鸣 ") is not None
    assert library.find(_StubProvider(), "微风  鸟鸣", audio_format="wav") is None
    assert fingerprint_for("m", "同一提示", "mp3") != fingerprint_for(
        "m", "同一提示", "wav"
    )
    assert normalize_prompt(" 微风  鸟鸣 ") == "微风 鸟鸣"


def test_index_persisted_and_reloaded(tmp_path):
    root = tmp_path / "sounds"
    SoundLibrary(root).admit(
        _write_tone(tmp_path / "琴.mp3"), _StubProvider(),
        prompt="琴声", name="琴", kind="music", description="古琴",
        tags=["古风"],
    )

    data = json.loads((root / "index.json").read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert len(data["sounds"]) == 1
    stored = data["sounds"][0]
    assert stored["name"] == "琴"
    assert stored["description"] == "古琴"
    assert stored["tags"] == ["古风"]

    reloaded = SoundLibrary(root)
    assert len(reloaded.all()) == 1
    assert reloaded.find(_StubProvider(), "琴声") is not None


def test_search_filters_by_keyword_and_kind(tmp_path):
    library = SoundLibrary(tmp_path / "sounds")
    library.admit(
        _write_tone(tmp_path / "1.mp3"), _StubProvider(),
        prompt="gentle rain", name="雨声", description="窗外舒缓的下雨声",
        tags=["天气"], kind="ambient",
    )
    library.admit(
        _write_tone(tmp_path / "2.mp3"), _StubProvider(),
        prompt="thunder", name="雷声", description="远处隆隆雷声",
        tags=["风暴"], kind="sfx",
    )

    assert {r["name"] for r in library.search("雨")} == {"雨声"}
    assert {r["name"] for r in library.search("rain")} == {"雨声"}
    assert {r["name"] for r in library.search("声")} == {"雨声", "雷声"}
    assert len(library.search("声", kind="sfx")) == 1
    assert library.search("雷声")[0]["kind"] == "sfx"


def test_corrupt_index_is_treated_as_empty(tmp_path):
    root = tmp_path / "sounds"
    root.mkdir()
    (root / "index.json").write_text("{ not json", encoding="utf-8")
    library = SoundLibrary(root)
    assert library.all() == []
    assert library.find(_StubProvider(), "风声") is None
    record = library.admit(
        _write_tone(tmp_path / "风声.mp3"), _StubProvider(),
        prompt="风声", name="风", kind="ambient",
    )
    assert library.path_for(record).exists()


def test_empty_prompt_and_bad_kind_rejected(tmp_path):
    library = SoundLibrary(tmp_path / "sounds")
    raw = _write_tone(tmp_path / "x.mp3")
    with pytest.raises(ValueError):
        library.find(_StubProvider(), "  ")
    with pytest.raises(ValueError):
        library.admit(
            raw, _StubProvider(), prompt="  ", name="x"
        )
    with pytest.raises(ValueError):
        library.admit(
            raw, _StubProvider(), prompt="雨声", name="雨", kind="nope"
        )


def test_admit_near_silent_raises_and_keeps_source(tmp_path):
    from storyteller.core.exceptions import SoundGenerationError

    root = tmp_path / "sounds"
    library = SoundLibrary(root)
    raw = _write_tone(
        tmp_path / "project" / "sounds" / "雨后.mp3", gain=-70
    )

    with pytest.raises(SoundGenerationError) as exc_info:
        library.admit(
            raw, _StubProvider(), prompt="雨后", name="雨后", kind="ambient"
        )

    message = str(exc_info.value)
    assert "dBFS" in message
    # The raw clip path is reported so the user can find the kept file.
    assert "雨后.mp3" in message
    # Nothing registered, no library copy, source preserved.
    assert library.all() == []
    assert list(root.glob("snd_*")) == []
    assert not (root / "index.json").exists()
    assert raw.exists()


def test_admit_unreadable_clip_raises_and_keeps_source(tmp_path):
    from storyteller.core.exceptions import SoundGenerationError

    root = tmp_path / "sounds"
    library = SoundLibrary(root)
    raw = tmp_path / "broken.mp3"
    raw.write_bytes(b"not an audio file")

    with pytest.raises(SoundGenerationError):
        library.admit(
            raw, _StubProvider(), prompt="坏文件", name="坏文件", kind="sfx"
        )
    assert library.all() == []
    assert raw.exists()


def test_failed_admit_can_be_retried(tmp_path):
    library = SoundLibrary(tmp_path / "sounds")
    silent = _write_tone(tmp_path / "雨后.mp3", gain=-70)
    with pytest.raises(Exception):
        library.admit(
            silent, _StubProvider(), prompt="雨后", name="雨后", kind="ambient"
        )
    # Replace the raw clip with an audible one and retry.
    _write_tone(silent, gain=0)
    record = library.admit(
        silent, _StubProvider(), prompt="雨后", name="雨后", kind="ambient"
    )
    assert library.path_for(record).exists()
    assert len(library.all()) == 1
```

- [ ] **Step 6: 运行确认 RED**

Run: `/Users/lizhe/Documents/workspace/audio-story-generator/.venv/bin/python -m pytest tests/unit/test_sound_library.py -q`
Expected: 新测试全部 FAIL（`find`/`admit` 不存在，AttributeError）。

- [ ] **Step 7: 实现 find 与 admit**

在 `SoundLibrary` 类中，保留现有 `get_or_create` 不动，在其**之前**插入：

```python
    def find(self, provider, prompt, audio_format="mp3"):
        """Return the cached record for model+prompt+format, or None.

        A record whose library file was deleted is treated as a miss.
        """
        prompt = normalize_prompt(prompt)
        if not prompt:
            raise ValueError("prompt must not be empty")
        fingerprint = fingerprint_for(
            getattr(provider, "model", None) or provider.name,
            prompt,
            audio_format,
        )
        record = self._find_by_fingerprint(self._load(), fingerprint)
        if record is not None and self._record_path(record).exists():
            return record
        return None

    def admit(
        self,
        source_path,
        provider,
        *,
        prompt,
        name,
        kind="sfx",
        description="",
        tags=None,
        audio_format="mp3",
        duration=None,
    ):
        """Gate an already-generated clip and COPY it into the library.

        The source file is never deleted: a near-silent or unreadable clip
        raises SoundGenerationError (message names the source path) and stays
        on disk for inspection.
        """
        if kind not in _KINDS:
            raise ValueError("kind must be one of {}".format(", ".join(_KINDS)))
        prompt = normalize_prompt(prompt)
        if not prompt:
            raise ValueError("prompt must not be empty")
        source = Path(source_path)
        ext = _EXTENSIONS.get((audio_format or "mp3").lower(), "mp3")

        dbfs = _measure_dbfs(source)
        if dbfs is None or dbfs <= MIN_SOUND_DBFS:
            level = "unreadable" if dbfs is None else "{:.0f} dBFS".format(dbfs)
            from .exceptions import SoundGenerationError

            raise SoundGenerationError(
                "Generated sound for {!r} was {} and was not admitted to "
                "the library (raw clip kept at {})".format(
                    prompt, level, source
                )
            )

        fingerprint = fingerprint_for(
            getattr(provider, "model", None) or provider.name,
            prompt,
            audio_format,
        )
        record_id = generate_id("snd_")
        dest = self.base_dir / "{}.{}".format(record_id, ext)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

        record = {
            "id": record_id,
            "name": name or prompt[:20],
            "description": description or "",
            "kind": kind,
            "tags": list(tags or []),
            "prompt": prompt,
            "fingerprint": fingerprint,
            "path": dest.name,
            "format": ext,
            "duration": duration,
            "model": getattr(provider, "model", None) or provider.name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        records = self._load()
        records.append(record)
        self._write(records)
        return record
```

- [ ] **Step 8: 运行确认 GREEN**

Run: `/Users/lizhe/Documents/workspace/audio-story-generator/.venv/bin/python -m pytest tests/unit/test_sound_library.py tests/unit/test_sound_paths.py -q`
Expected: 全部 PASS。

- [ ] **Step 9: 全量测试并提交**

Run: `/Users/lizhe/Documents/workspace/audio-story-generator/.venv/bin/python -m pytest -q`
Expected: 286 基线 + 本任务新增（15 左右）全绿；旧 get_or_create 仍被 pipeline/main 使用，相关集成/e2e 测试不受影响。

```bash
git add src/storyteller/core/sound_library.py tests/unit/test_sound_library.py tests/unit/test_sound_paths.py
git commit -m "feat: SoundLibrary find/admit split and safe sound filenames"
```

---

### Task 2: pipeline 音效先生成到项目目录，合格再入库

**Files:**
- Modify: `src/storyteller/core/pipeline.py`（`_apply_soundtrack` 的 pending 循环 405-427；新增两个辅助方法）
- Test: `tests/e2e/test_pipeline.py`

**Interfaces:**
- Consumes: Task 1 的 `library.find/admit/path_for`、`safe_sound_name`、`unique_path`；`provider.generate(prompt, path, audio_format=...) -> (path, duration)`；`self._project_dir(project_id)`（已存在，pipeline.py:320）。
- Produces: 每个 cue 的 `source_path` 指向**项目内** `stories/<proj>/sounds/<安全名>.mp3`；废片文件保留且 cue 不参与混音。

- [ ] **Step 1: 更新/新增 e2e 测试**

在 `tests/e2e/test_pipeline.py` 中：

(a) 把 `test_run_with_sound_mixes_and_backfills_paths` 中结尾断言段（`data = _json.loads(...)` 起到函数末尾）替换为：

```python
    data = _json.loads(
        (result_path.parent / "story.script.json").read_text(encoding="utf-8")
    )
    assert data["background_music"]["source_path"]
    assert data["lines"][0]["sound_effects"][0]["source_path"]

    # Every cue has a Chinese-named raw clip INSIDE the project dir...
    project_sounds = result_path.parent / "sounds"
    raw_names = sorted(p.name for p in project_sounds.glob("*.mp3"))
    assert raw_names == ["宁静夜曲.mp3", "雨声.mp3"]
    bgm_path = Path(data["background_music"]["source_path"])
    cue_path = Path(data["lines"][0]["sound_effects"][0]["source_path"])
    assert bgm_path.parent == project_sounds
    assert cue_path.parent == project_sounds
    # ...and an admitted snd_ copy in the global library.
    assert len(list((tmp_path / "sounds").glob("snd_*.mp3"))) == 2

    # No stray temp bed left behind.
    assert list(result_path.parent.glob("*.bgm.mp3")) == []
```

(b) 在 `test_run_with_sound_reuses_cache_on_second_story` 末尾（最后的 provider.calls 断言之后）追加：

```python
    # Both projects are self-contained: cache hits are COPIED into each
    # project dir under the cue name, never regenerated.
    project_dirs = sorted(
        p.parent for p in tmp_path.rglob("story.mp3")
    )
    assert len(project_dirs) == 2
    for project_dir in project_dirs:
        names = sorted(p.name for p in (project_dir / "sounds").glob("*.mp3"))
        assert names == ["宁静夜曲.mp3", "雨声.mp3"]
```

(c) 在 `test_sound_disabled_by_default_ignores_cues` 之后追加废片保留测试与 stub provider：

```python
class _NearSilentSoundProvider:
    """Sound stub that writes an effectively silent clip (~-70 dBFS)."""

    name = "mock"
    model = "mock-sound"

    def generate(self, prompt, output_path, *, audio_format="mp3", **kwargs):
        from pydub.generators import Sine

        output_path.parent.mkdir(parents=True, exist_ok=True)
        Sine(440).to_audio_segment(duration=300).apply_gain(-70).export(
            str(output_path), format="wav"
        )
        return output_path, 0.3


def test_failed_sound_clip_is_kept_in_project_but_not_mixed(tmp_path):
    from storyteller.core.sound_library import SoundLibrary

    config = Config()
    config.set("data_dir", str(tmp_path / ".storyteller"))
    config.resolve_paths()
    config.set("sound.enabled", True)
    config.set("sound.dir", str(tmp_path / "sounds"))
    config.set("llm.default_provider", "mock")
    config.set("tts.default_provider", "mock")

    llm = MockLLMProvider(config)
    llm.set_response(_sound_script())
    library = SoundLibrary(tmp_path / "sounds")
    pipeline = Pipeline(
        config,
        sound_provider=_NearSilentSoundProvider(),
        sound_library=library,
    )
    pipeline.registry.register_llm("mock", lambda c: llm)
    pipeline.registry.register_tts("mock", MockTTSProvider)

    result_path = Path(pipeline.run("雨夜"))
    assert result_path.exists()

    # Both clips failed the gate: raw files kept with cue names...
    project_sounds = result_path.parent / "sounds"
    assert sorted(p.name for p in project_sounds.glob("*.mp3")) == [
        "宁静夜曲.mp3",
        "雨声.mp3",
    ]
    # ...nothing admitted to the global library...
    assert library.all() == []
    assert list((tmp_path / "sounds").glob("snd_*.mp3")) == []
    # ...and the failed cues carry no source_path, so nothing is mixed.
    import json as _json

    data = _json.loads(
        (result_path.parent / "story.script.json").read_text(encoding="utf-8")
    )
    assert data["background_music"]["source_path"] is None
    assert data["lines"][0]["sound_effects"][0]["source_path"] is None
```

- [ ] **Step 2: 运行确认 RED**

Run: `/Users/lizhe/Documents/workspace/audio-story-generator/.venv/bin/python -m pytest tests/e2e/test_pipeline.py -q`
Expected: 三个音效相关测试 FAIL（项目目录无 sounds/ 文件夹；source_path 仍指向全局库；废片被删除）。

- [ ] **Step 3: 实现项目内生成/复制流程**

在 `pipeline.py` 顶部 import 区（`import re` 之后）加 `import shutil`（当前文件没有此导入；`from pathlib import Path` 已存在）。

把 `_apply_soundtrack` 中的 pending 循环：

```python
        provider = self._get_sound_provider()
        library = self._get_sound_library()
        for cue in pending:
            try:
                path, record, created = library.get_or_create(
                    provider,
                    prompt=cue.prompt,
                    name=cue.name,
                    kind=_KIND_FOR_TYPE.get(cue.type, "sfx"),
                    description=cue.description or "",
                    tags=cue.tags or [],
                    audio_format="mp3",
                )
            except Exception as exc:
                self._log_error(cue.effect_id, exc)
                continue
            cue.source_path = str(path)
            cue.source_type = "local"
            if cue.duration is None:
                cue.duration = record.get("duration")
            self._log_detail(
                "  sound %s -> %s (%.1fs%s)" % (
                    cue.name, Path(path).name, record.get("duration") or 0,
                    "" if created else ", cached"
                )
            )
```

替换为：

```python
        provider = self._get_sound_provider()
        library = self._get_sound_library()
        for cue in pending:
            created = False
            try:
                raw_path = self._project_sound_path(state.project_id, cue)
                record = library.find(provider, cue.prompt, audio_format="mp3")
                if record is not None:
                    shutil.copy2(library.path_for(record), raw_path)
                else:
                    _, gen_duration = provider.generate(
                        cue.prompt, raw_path, audio_format="mp3"
                    )
                    record = library.admit(
                        raw_path,
                        provider,
                        prompt=cue.prompt,
                        name=cue.name,
                        kind=_KIND_FOR_TYPE.get(cue.type, "sfx"),
                        description=cue.description or "",
                        tags=cue.tags or [],
                        audio_format="mp3",
                        duration=gen_duration,
                    )
                    created = True
            except Exception as exc:
                # The raw clip (if any) stays in the project's sounds/ dir
                # for inspection; the cue is simply left out of the mix.
                self._log_error(cue.effect_id, exc)
                continue
            cue.source_path = str(raw_path)
            cue.source_type = "local"
            if cue.duration is None:
                cue.duration = record.get("duration")
            self._log_detail(
                "  sound %s -> %s (%.1fs%s)" % (
                    cue.name, raw_path.name, record.get("duration") or 0,
                    "" if created else ", cached"
                )
            )
```

在 `_project_dir` 方法之后新增：

```python
    def _project_sound_path(self, project_id, cue):
        """Chinese-named raw clip path inside the project's sounds/ dir."""
        from .sound_library import safe_sound_name, unique_path

        sounds_dir = self._project_dir(project_id) / "sounds"
        sounds_dir.mkdir(parents=True, exist_ok=True)
        fallback = "sfx_" + str(cue.effect_id)[-6:]
        stem = safe_sound_name(cue.name or (cue.prompt or "")[:12], fallback)
        return unique_path(sounds_dir, stem, "mp3")
```

- [ ] **Step 4: 运行确认 GREEN**

Run: `/Users/lizhe/Documents/workspace/audio-story-generator/.venv/bin/python -m pytest tests/e2e/test_pipeline.py -q`
Expected: 全部 PASS。

- [ ] **Step 5: 全量测试并提交**

Run: `/Users/lizhe/Documents/workspace/audio-story-generator/.venv/bin/python -m pytest -q`
Expected: 全绿（数量 = Task 1 后数量，本任务净增 1 个测试）。

```bash
git add src/storyteller/core/pipeline.py tests/e2e/test_pipeline.py
git commit -m "feat: keep every generated cue as a named clip in the project dir"
```

---

### Task 3: make-sound 经 raw/ 暂存，废片保留并非零退出；删除 get_or_create

**Files:**
- Modify: `src/storyteller/cli/main.py`（`make_sound` 441-489）
- Modify: `src/storyteller/core/sound_library.py`（删除 `get_or_create`）
- Test: `tests/e2e/test_cli.py`

**Interfaces:**
- Consumes: `library.find/path_for/admit`、`safe_sound_name`、`unique_path`；config `sound.dir`。
- Produces: make-sound 成功 → `Generated: <库路径>`、raw 暂存删除；缓存命中 → `Cache hit (no API call): <库路径>`、不产生 raw；闸门失败 → ClickException（exit 1，文案含 raw 路径），raw 文件保留在 `<sound.dir>/raw/<name>.<ext>`。

- [ ] **Step 1: 新增 CLI 测试**

在 `tests/e2e/test_cli.py` 末尾追加：

```python
def test_make_sound_removes_raw_staging_on_success():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["make-sound", "舒缓的雨声", "--sound-provider", "mock"],
            env=_MOCK_ENV,
        )
        assert result.exit_code == 0, result.output
        assert "Generated" in result.output
        # The raw staging clip is removed once admitted to the library.
        assert not (Path(".storyteller/sounds/raw")).exists() or \
            list(Path(".storyteller/sounds/raw").glob("*")) == []


def test_make_sound_keeps_raw_clip_when_gate_fails(monkeypatch):
    from pydub.generators import Sine
    from storyteller.providers.mock import sfx as mock_sfx

    def silent_generate(self, prompt, output_path, *, audio_format="mp3",
                        **kwargs):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Sine(440).to_audio_segment(duration=300).apply_gain(-70).export(
            str(output_path), format="wav"
        )
        return output_path, 0.3

    monkeypatch.setattr(mock_sfx.MockSoundProvider, "generate", silent_generate)

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["make-sound", "细微的落叶声", "--sound-provider", "mock"],
            env=_MOCK_ENV,
        )
        assert result.exit_code != 0
        # Failed clip is kept under sounds/raw and its path is reported.
        raw_files = list(Path(".storyteller/sounds/raw").glob("*.mp3"))
        assert len(raw_files) == 1
        assert raw_files[0].name == "细微的落叶声.mp3"
        assert "raw" in result.output
```

确认 `tests/e2e/test_cli.py` 顶部已有 `from pathlib import Path`（没有则加）。

- [ ] **Step 2: 运行确认 RED**

Run: `/Users/lizhe/Documents/workspace/audio-story-generator/.venv/bin/python -m pytest tests/e2e/test_cli.py -q`
Expected: 两个新测试 FAIL（旧实现没有 raw/ 目录；废片路径报缺 key/删除，exit 行为不符）。

- [ ] **Step 3: 重写 make_sound 主体**

在 `main.py` 顶部 import 区加 `from pathlib import Path`（当前文件未导入）；`tests/e2e/test_cli.py` 顶部同样加 `from pathlib import Path`（当前未导入）。

把 `make_sound` 中从 `library = SoundLibrary(...)` 到函数结尾（两个 click.echo 输出行）整体替换为：

```python
    sound_root = config.get("sound.dir") or "./.storyteller/sounds"
    library = SoundLibrary(sound_root)
    raw_path = None
    try:
        provider = registry.get_sound(chosen)
        record = library.find(provider, prompt, audio_format)
        if record is not None:
            cached_path = library.path_for(record)
            click.echo("Cache hit (no API call): {}".format(cached_path))
            click.echo(
                "Name: {}  kind: {}".format(record["name"], record["kind"])
            )
            return

        from ..core.sound_library import safe_sound_name, unique_path

        ext = "wav" if audio_format == "wav" else "mp3"
        stem = safe_sound_name(name or prompt[:12], fallback="sound")
        raw_path = unique_path(Path(sound_root) / "raw", stem, ext)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        _, gen_duration = provider.generate(
            prompt, raw_path, audio_format=audio_format
        )
        record = library.admit(
            raw_path,
            provider,
            prompt=prompt,
            name=name or prompt[:12],
            kind=kind,
            description=description,
            tags=[t.strip() for t in tags.split(",") if t.strip()],
            audio_format=audio_format,
            duration=gen_duration,
        )
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(str(exc))

    # Admitted to the curated library: drop the staging copy. On failure
    # the exception above has already returned non-zero with the raw path.
    try:
        raw_path.unlink()
    except OSError:
        pass
    click.echo("Generated: {}".format(library.path_for(record)))
    click.echo("Name: {}  kind: {}".format(record["name"], record["kind"]))
```

- [ ] **Step 4: 删除 get_or_create**

在 `src/storyteller/core/sound_library.py` 中删除整个 `get_or_create` 方法（从 `def get_or_create(` 到其 `return path, record, True`，含 docstring）。全仓确认无残留引用：

Run: `grep -rn "get_or_create" src/ tests/`
Expected: 无输出。

- [ ] **Step 5: 运行确认 GREEN**

Run: `/Users/lizhe/Documents/workspace/audio-story-generator/.venv/bin/python -m pytest tests/e2e/test_cli.py tests/unit/test_sound_library.py -q`
Expected: 全部 PASS。

- [ ] **Step 6: 全量测试并提交**

Run: `/Users/lizhe/Documents/workspace/audio-story-generator/.venv/bin/python -m pytest -q`
Expected: 全绿。

```bash
git add src/storyteller/cli/main.py src/storyteller/core/sound_library.py tests/e2e/test_cli.py
git commit -m "feat: make-sound stages to sounds/raw and preserves failed clips"
```

---

### Task 4: README 文档更新与全量验证

**Files:**
- Modify: `README.md`（「音效与背景音乐」段）

- [ ] **Step 1: 更新 README 音效段**

在 `README.md`「## 音效与背景音乐」段中，已有的 provider 迁移 blockquote（`> 音效是与 LLM/TTS 同构的独立 provider 分组…`）之后，新增一段：

```markdown
> 生成的每条音效（含未通过响度闸门、被跳过混音的废片）都会以 cue 的中文名保存在项目目录 `stories/<项目>/sounds/` 下，永不自动删除，方便事后收听排查；通过闸门的素材另存一份到全局音效库（`snd_<id>.mp3`，供跨项目缓存复用）。`make-sound` 的新素材先暂存于 `sounds/raw/`，合格入库后清理，不合格则保留并以非零退出码报告路径。
```

- [ ] **Step 2: 全量验证**

Run: `/Users/lizhe/Documents/workspace/audio-story-generator/.venv/bin/python -m pytest -q`
Expected: 全部 PASS 无 warning。

Run: `grep -rn "get_or_create" src/ tests/ || echo "clean"`
Expected: `clean`。

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs: explain project-local raw sound clips and raw staging dir"
```

- [ ] **Step 4: 收尾**

交由 controller：最终全分支审查 → finishing-a-development-branch；记忆更新（storyteller-project.md 音效段：项目 `sounds/` 保留全部原始素材、find/admit 接口、raw 暂存与废片保留行为）。

---

## Self-Review

**Spec coverage:**
- 项目目录中文名保存全部 cue（含废片）、永不删除 → Task 2（`_project_sound_path` + 异常时不删）。
- 合格复制入库、指纹缓存语义不变 → Task 1 `admit`（copy2 + 同 record 结构/指纹）。
- 缓存命中也复制中文名副本到项目 → Task 2 find 命中分支 copy2。
- make-sound 废片保留 raw/、非零退出、报告路径 → Task 3；成功清理暂存 → Task 3。
- 响度闸门不变、错误文案含路径 → Task 1 测试锁定。
- 文档与记忆 → Task 4。

**Type/name 一致性:** `find(provider, prompt, audio_format)`、`admit(source_path, provider, *, prompt, name, kind, description, tags, audio_format, duration)` 在三个任务中签名一致；`safe_sound_name(name, fallback)`、`unique_path(directory, stem, ext)` 一致；`SoundGenerationError` 已存在于 `core/exceptions.py`。

**已知边界:** resume 时旧废片 cue 因 source_path 为空会重试，生成 `名字-2.mp3`（旧片保留），符合"永不删除"；BGM 混音当前在 pipeline 中被注释关闭（既有状态，本计划不动），但 BGM cue 仍走同一保存/入库路径。
