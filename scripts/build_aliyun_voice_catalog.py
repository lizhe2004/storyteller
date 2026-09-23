"""Build the packaged Aliyun voice catalog from the Qwen voice lists."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src/storyteller/providers/aliyun/voices.json"
SOURCES = (
    ("qwen-audio-3.0-tts-flash", ROOT / "qwen-audio-3.0-tts-flash基础音色.md"),
    ("qwen-audio-3.0-tts-plus", ROOT / "qwen-audio-3.0-tts-plus基础音色.md"),
)
VOICE_LIST_DOC = ROOT / "docs/reference/tts/Qwen-Audio-TTS音色列表.md"
MODEL_31 = "qwen-audio-3.1-tts-flash"
ROW = re.compile(
    r"^\|\s*\d+\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*"
    r"(.*?)\s*\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*"
    r"(.*?)\s*\|"
)
AGE_BANDS = ((12, "child"), (17, "teen"), (45, "young_adult"),
             (59, "middle_aged"))

_VERSION_SUFFIX = re.compile(r"_v3\.\d+$")
_MULTILINGUAL_NOTE = (
    "多语种：支持上海话、广东话、东北话、重庆话、陕西话、云南话、宁波话、"
    "甘肃话及日语、韩语、法语、德语、葡萄牙语、意大利语、越南语、印尼语"
)

# Keyword groups are checked in priority order (narration first), mirroring
# the categories used by the 3.0 records.
_SCENE_CATEGORY = (
    (("儿童故事", "儿童陪伴", "儿童有声书", "童声"), "儿童陪伴"),
    (("诗词朗诵",), "古风有声书"),
    (("有声书", "旁白", "配音讲解"), "有声阅读"),
    (("新闻播报",), "新闻播报"),
    (("音乐电台",), "深夜电台"),
    (("客服",), "智能客服"),
    (("语音助手",), "智能助手"),
    (("社交陪伴",), "社交陪伴"),
    (("角色音",), "角色扮演"),
    (("广告营销", "广播", "直播带货"), "电商直播"),
)

# Ages the doc does not state; inferred from the persona description.
_AGE_OVERRIDES = {
    "longjielidou_v3.1": "child",
    "longhuohuo_v3.1": "child",
    "longpaopao_v3.1": "child",
    "longling_v3.1": "child",
    "longniuniu_v3.1": "child",
    "longshanshan_v3.1": "child",
    "longanzhi_v3.1": "middle_aged",
    "longsanshu_v3.1": "middle_aged",
    "xuyuyuan_v3.1": "middle_aged",
    "wenhuaizhi_v3.1": "middle_aged",
    "guyunshu_v3.1": "middle_aged",
    "xuyanchu_v3.1": "middle_aged",
}


def _base_id(voice_id: str) -> str:
    return _VERSION_SUFFIX.sub("", voice_id)


def _category_for(scene: str) -> str:
    for keywords, category in _SCENE_CATEGORY:
        if any(keyword in scene for keyword in keywords):
            return category
    return "日常对话"


def _doc_cells(row: str) -> list[str]:
    cells = []
    for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S):
        text = re.sub(r"<[^>]+>", " ", cell)
        text = text.replace("\\_", "_")
        cells.append(re.sub(r"\s+", " ", text).strip())
    return cells


def _parse_voice_list_doc(doc: str) -> dict[str, list[list[str]]]:
    """Extract the qwen-audio-3.1 tables, keyed by section title."""
    start = doc.index("## {}".format(MODEL_31))
    end = doc.index("## qwen-audio-3.0-tts-plus")
    sections: dict[str, list[list[str]]] = {}
    for part in re.split(r"\n### ", doc[start:end])[1:]:
        title = part.split("\n", 1)[0].split(" <span")[0]
        rows = []
        for row in re.findall(r"<tr>(.*?)</tr>", part, re.S):
            if "<th" in row:
                continue
            cells = _doc_cells(row)
            if len(cells) >= 3:
                rows.append(cells)
        sections[title] = rows
    return sections


def _build_31_voices(existing: list[dict]) -> list[dict]:
    """Build catalog records for qwen-audio-3.1-tts-flash.

    English-only voices are skipped like their 3.0 counterparts: the matcher
    does not filter candidates by language. Persona metadata (age/category)
    is inherited from same-name catalog voices when available.
    """
    doc = VOICE_LIST_DOC.read_text(encoding="utf-8")
    sections = _parse_voice_list_doc(doc)
    twins = {_base_id(voice["voice_id"]): voice for voice in existing}

    def record(name, voice_id, gender, trait, scene, *, tags, section):
        twin = twins.get(_base_id(voice_id))
        age = _AGE_OVERRIDES.get(voice_id) or (twin or {}).get("age") \
            or "young_adult"
        fallback = "社交陪伴" if section == "multilingual" else "日常对话"
        category = (twin or {}).get("category") or (
            _category_for(scene) if scene else fallback
        )
        if section == "multilingual":
            base = (twin or {}).get("description") or trait
            description = "{}；{}".format(base, _MULTILINGUAL_NOTE) \
                if base else _MULTILINGUAL_NOTE
            tags = list(dict.fromkeys((twin or {}).get("tags", []) + tags))
        else:
            description = "{}，适用{}".format(trait, scene) if scene else trait
        return {
            "voice_id": voice_id,
            "name": _VERSION_SUFFIX.sub("", name),
            "model": MODEL_31,
            "gender": "female" if gender == "女" else "male",
            "age": age,
            "category": category,
            "description": description,
            "tags": tags,
            "language": "zh-CN",
            "bilingual": False,
        }

    voices = []
    for name, voice_id, gender, *_rest in sections.get("多语种与方言音色", []):
        voices.append(record(name, voice_id, gender, "", "",
                             tags=["多语种", "方言"], section="multilingual"))
    for cells in sections.get("精品中文音色", []):
        name, voice_id, gender, trait, scene = cells[:5]
        voices.append(record(name, voice_id, gender, trait, scene,
                             tags=["精品音色"], section="chinese"))
    # 精品英文音色 is intentionally skipped (English-only).
    for cells in sections.get("其他系统音色", []):
        name, voice_id, gender, trait, scene = cells[:5]
        voices.append(record(name, voice_id, gender, trait, scene,
                             tags=[], section="other"))
    return voices


def _age_band(years: int) -> str:
    for maximum, band in AGE_BANDS:
        if years <= maximum:
            return band
    return "senior"


def _parse_source(model: str, path: Path) -> list[dict]:
    voices = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if not match:
            continue
        name, voice_id, gender, years, trait, category, language = match.groups()
        if language != "中文":
            continue
        voices.append({
            "voice_id": voice_id,
            "name": name,
            "model": model,
            "gender": "female" if gender == "女" else "male",
            "age": _age_band(int(years)),
            "category": category,
            "description": f"{years}岁，{trait}",
            "tags": [],
            "language": "zh-CN",
            "bilingual": False,
        })
    return voices


def build_catalog() -> dict:
    existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
    # 3.1 records are fully regenerated from the voice-list doc, so stale
    # entries from earlier runs are replaced rather than kept.
    voices = [v for v in existing["voices"] if v.get("model") != MODEL_31]
    known_ids = {voice["voice_id"] for voice in voices}
    for model, source in SOURCES:
        for voice in _parse_source(model, source):
            if voice["voice_id"] not in known_ids:
                voices.append(voice)
                known_ids.add(voice["voice_id"])
    for voice in _build_31_voices(voices):
        if voice["voice_id"] not in known_ids:
            voices.append(voice)
            known_ids.add(voice["voice_id"])
    return {"voices": voices}


def main() -> None:
    OUTPUT.write_text(
        json.dumps(build_catalog(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
