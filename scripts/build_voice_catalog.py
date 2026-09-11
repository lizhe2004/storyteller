"""Build the packaged Volcengine voice catalog from the raw API exports.

Inputs:
    data/volcengine-zh-voices.raw.json      (Chinese-only ListSpeakers)
    data/volcengine-zh-en-voices.raw.json   (Chinese/English bilingual)

Output:
    src/storyteller/providers/volcengine/voices.json

Each speaker carries its X-Api-Resource-Id. Only seed-tts-2.0 voices are
shipped: the v3 unidirectional API documents seed-tts-2.0 (and seed-icl-2.0
for clones), so the older seed-tts-1.0 speakers are filtered out.
Customer-service / chat / livestream personas and regional-accent voices
are dropped as unsuitable for audio stories.

Usage:
    python scripts/build_voice_catalog.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_FILES = [
    ROOT / "data" / "volcengine-zh-voices.raw.json",
    ROOT / "data" / "volcengine-zh-en-voices.raw.json",
]
OUT = (
    ROOT
    / "src"
    / "storyteller"
    / "providers"
    / "volcengine"
    / "voices.json"
)

# First matching category decides the role the voice is used for. Voices
# tagged only with service personas (客服/陪聊/直播) match none and drop out.
PRIMARY_ORDER = (
    "有声阅读",
    "通用场景",
    "角色扮演",
    "视频配音",
    "教学场景",
    "多情感",
    "电台",
)
NARRATOR_CATEGORIES = {"有声阅读"}
# The v3 unidirectional API documents only seed-tts-2.0 (and seed-icl-2.0
# for cloned voices). Older seed-tts-1.0 speakers are not part of the
# contract and must not be shipped.
SUPPORTED_RESOURCES = {"seed-tts-2.0"}

_GENDER = {"男": "male", "女": "female"}
_AGE = {
    "儿童": "child",
    "少年/少女": "teen",
    "青年": "young_adult",
    "中年": "middle_aged",
    "老年": "senior",
}
_GENDER_ORDER = {"female": 0, "male": 1}
_AGE_ORDER = {"child": 0, "teen": 1, "young_adult": 2,
              "middle_aged": 3, "senior": 4}


def _categories(speaker):
    return [
        c
        for group in (speaker.get("Categories") or [])
        for c in (group.get("Categories") or [])
    ]


def _clean_name(name):
    name = re.sub(r"\s+", " ", (name or "")).strip()
    return re.sub(r"\s*2\.0$", "", name).strip()


def _is_bilingual(speaker):
    flags = "".join(
        l.get("Flag", "") for l in (speaker.get("Languages") or [])
    )
    # The bilingual export flags voices with both CN and US flags.
    return "🇨🇳" in flags and "🇺🇸" in flags


def _primary_category(categories):
    """Pick the story role for a voice, or None to exclude it.

    - regional accents are unsuitable for standard narration: exclude
    - if it has a usable story category, the highest-priority one wins
      (a voice that is both 客服 and 有声阅读 stays, via 有声阅读)
    - completely uncategorized voices are kept as ordinary characters
    - voices tagged only with service/chat/live categories are dropped
    """
    if any("口音" in c for c in categories):
        return None
    for cat in PRIMARY_ORDER:
        if cat in categories:
            return cat
    if not categories:
        return ""
    return None


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


def _load_speakers(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["Result"]["Speakers"]


def main():
    voices = []
    seen = set()
    skipped = 0

    for raw_file in RAW_FILES:
        if not raw_file.exists():
            continue
        for s in _load_speakers(raw_file):
            voice_id = s["VoiceType"]
            if voice_id in seen:
                continue

            resource_id = s.get("ResourceID", "seed-tts-2.0")
            if resource_id not in SUPPORTED_RESOURCES:
                skipped += 1
                continue

            categories = _categories(s)
            primary = _primary_category(categories)
            if primary is None:
                skipped += 1
                continue

            gender = _GENDER.get(s.get("Gender"), "male")
            age = _AGE.get(s.get("Age"), "young_adult")
            record = {
                "voice_id": voice_id,
                "name": _clean_name(s.get("Name")),
                "gender": gender,
                "age": age,
                "category": primary,
                "description": (s.get("Description") or "").strip(),
                "tags": [t for t in (s.get("SpecialLabels") or []) if t],
                "language": "zh-CN",
                "bilingual": _is_bilingual(s),
                "resource_id": s.get("ResourceID", "seed-tts-2.0"),
            }
            seen.add(voice_id)
            voices.append(record)

    voices.sort(key=_sort_key)

    payload = {
        "default_resource_id": "seed-tts-2.0",
        "count": len(voices),
        "voices": voices,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    genders = {}
    for v in voices:
        genders[v["gender"]] = genders.get(v["gender"], 0) + 1
    resources = {}
    for v in voices:
        resources[v["resource_id"]] = resources.get(v["resource_id"], 0) + 1
    print("Wrote {} voices to {}".format(len(voices), OUT))
    print("By gender:", genders)
    print("By resource:", resources)
    print("Bilingual:", sum(1 for v in voices if v["bilingual"]))
    print("Skipped:", skipped)


if __name__ == "__main__":
    main()
