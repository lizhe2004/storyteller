"""One-off: retrofit anchors + improved prompts onto proj_a028ae019e87,
regenerate the changed cues (real seed-audio calls), remix to story_v4.mp3.

Run from repo root with the venv. Safe to re-run: prompts unchanged since the
last run hit the cache.
"""
import json
from pathlib import Path

from storyteller.core.config import Config
from storyteller.core.models import SoundEffect
from storyteller.core.sound_library import SoundLibrary
from storyteller.core.audio import PydubAudioProcessor
from storyteller.providers.volcengine.sfx import VolcengineSoundProvider
from pydub import AudioSegment

D = Path(".storyteller/stories/proj_a028ae019e87")
KIND = {"effect": "sfx", "ambient": "ambient", "music": "music"}

# (line_id, cue name) -> (new prompt or None to keep, anchor or None)
EDITS = {
    ("1", "床板吱呀"): (None, "从床上爬起来"),
    ("3", "炉火点燃"): (
        "木炭在炉膛里被点燃，噼啪爆裂声由小变大，持续两三秒，近景，无人声",
        "开始生炉火",
    ),
    ("3", "铁钳夹木炭"): (
        "铁钳子夹起木炭的轻微碰撞摩擦声，一两声，近景，无人声",
        "夹起木炭",
    ),
    ("5", "脚步走近"): (
        "沉稳的成年男人布鞋脚步声，踩在泥地上由远及近，一步一步，五六步，无人声",
        "铁爷爷走了进来",
    ),
    ("11", "肚子咕噜"): (
        "人肚子饿时咕咕叫的声音，低沉的咕噜冒泡声，两三声，很近，无人声",
        "肚子咕咕叫了起来",
    ),
    ("20", "溪水流动"): (
        "清澈溪水流淌过石头的潺潺声，持续舒缓，户外环境，无人声",
        None,
    ),
    ("20", "水桶入水"): (
        "木桶探入溪水灌水再提起的泼溅水声，两三次，近景，无人声",
        "舀满水",
    ),
    ("20", "脚步声"): (
        "轻快的少年脚步声，提着水桶走在小路上，一步一步，五六步，渐渐走远，无人声",
        "提着水桶往回走",
    ),
    ("16", "松鼠落地"): (None, "跳了下来"),
    ("21", "卷帘门拉动"): (
        "金属卷帘门被拉下来的哗啦声，持续两三秒后哐当一声落到底，无人声",
        "拉下卷帘门",
    ),
    ("21", "锁门咔嗒"): (None, "咔嗒一声锁好"),
}


def apply(script):
    changed = []
    by_line = {ln["line_id"]: ln for ln in script["lines"]}
    for (lid, name), (new_prompt, anchor) in EDITS.items():
        for cue in by_line[lid].get("sound_effects", []):
            if cue["name"] != name:
                continue
            cue["anchor"] = anchor
            if new_prompt is not None and cue.get("prompt") != new_prompt:
                cue["prompt"] = new_prompt
                # Force regeneration through the library on next pass.
                cue["source_path"] = None
                cue["source_type"] = "builtin"
                changed.append((lid, name))
    return changed


def to_obj(raw):
    return SoundEffect(
        effect_id=raw["effect_id"], name=raw["name"], type=raw["type"],
        source_path=raw.get("source_path"),
        source_type=raw.get("source_type", "local"),
        volume=raw.get("volume", 1.0), start_time=raw.get("start_time", 0.0),
        duration=raw.get("duration"), fade_in=raw.get("fade_in", 0.0),
        fade_out=raw.get("fade_out", 0.0), prompt=raw.get("prompt"),
        description=raw.get("description"), tags=raw.get("tags", []) or [],
        anchor=raw.get("anchor"),
    )


def main():
    script_path = D / "story.script.json"
    project_path = D / "project.json"
    script = json.loads(script_path.read_text(encoding="utf-8"))
    changed = apply(script)
    script_path.write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Keep the embedded project snapshot in sync.
    proj = json.loads(project_path.read_text(encoding="utf-8"))
    apply(proj["script"])
    project_path.write_text(
        json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("prompts changed (will regenerate):", changed)

    config = Config.from_env()
    provider = VolcengineSoundProvider(config)
    library = SoundLibrary(config.get("sound.dir"))

    # Materialize every pending cue. Skip per-cue failures (e.g. seed-audio
    # returning a near-silent clip that the library discards) so one bad
    # generation doesn't abort the whole remix; the cue just drops out.
    from storyteller.core.exceptions import SoundGenerationError
    pending = []
    for ln in script["lines"]:
        for raw in ln.get("sound_effects", []):
            if raw.get("prompt") and not raw.get("source_path"):
                pending.append((ln, raw))
    for ln, raw in pending:
        try:
            path, record, created = library.get_or_create(
                provider, prompt=raw["prompt"], name=raw["name"],
                kind=KIND.get(raw["type"], "sfx"),
                description=raw.get("description") or "",
                tags=raw.get("tags") or [], audio_format="mp3",
            )
        except SoundGenerationError as exc:
            print("  %-8s %s -> SKIP (discarded: %s)" % (
                ln["line_id"], raw["name"], str(exc)[:80]), flush=True)
            continue
        except Exception as exc:  # noqa: BLE001 - don't abort remix on one cue
            print("  %-8s %s -> SKIP (%s: %s)" % (
                ln["line_id"], raw["name"], type(exc).__name__, str(exc)[:80]),
                flush=True)
            continue
        raw["source_path"] = str(path)
        raw["source_type"] = "local"
        raw["duration"] = record.get("duration")
        print("  %-8s %s -> %s (%.1fs, created=%s)" % (
            ln["line_id"], raw["name"], Path(path).name,
            record.get("duration") or 0, created), flush=True)
    script_path.write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Rebuild voice backbone and per-line timing.
    segs, elapsed, timing = [], 0, {}
    for ln in script["lines"]:
        p = D / "audio" / (ln["line_id"] + ".mp3")
        dur = len(AudioSegment.from_file(p)) / 1000 if p.exists() else 0
        timing[ln["line_id"]] = (elapsed, dur)
        if p.exists():
            segs.append(AudioSegment.from_file(p))
            elapsed += dur
    backbone = segs[0]
    for s in segs[1:]:
        backbone += s
    tmp = D / "_backbone.mp3"
    backbone.export(str(tmp), format="mp3")

    groups = []
    for ln in script["lines"]:
        cues = [to_obj(r) for r in ln.get("sound_effects", []) if r.get("source_path")]
        if not cues:
            continue
        start, duration = timing[ln["line_id"]]
        entries = []
        for c in cues:
            off = Pipeline_anchor(ln, c, duration)
            entries.append((c, off))
        groups.append((start, duration, entries))

    out = D / "story_v4.mp3"
    PydubAudioProcessor().add_effect_groups(tmp, groups, out)
    tmp.unlink()
    final = AudioSegment.from_file(out)
    print("story_v4.mp3 %.1fs %.1f dBFS" % (len(final) / 1000, final.dBFS))


def Pipeline_anchor(ln, cue, duration):
    # Mirror of Pipeline._anchor_offset without needing registry setup.
    import re
    if not duration or cue.type != "effect" or not cue.anchor:
        return 0.0
    text = ln["text"] or ""
    idx = text.find(cue.anchor)
    if idx < 0:
        return 0.0
    punct = re.compile(r"[\s，。！？；：、,…,.\!?;:\-—“”\"'（）()…]")
    before = len(punct.sub("", text[:idx]))
    total = len(punct.sub("", text))
    return min(duration, duration * before / total) if total else 0.0


if __name__ == "__main__":
    main()
