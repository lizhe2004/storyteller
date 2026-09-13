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
ROW = re.compile(
    r"^\|\s*\d+\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*"
    r"(.*?)\s*\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*"
    r"(.*?)\s*\|"
)
AGE_BANDS = ((12, "child"), (17, "teen"), (45, "young_adult"),
             (59, "middle_aged"))


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
    voices = list(existing["voices"])
    known_ids = {voice["voice_id"] for voice in voices}
    for model, source in SOURCES:
        for voice in _parse_source(model, source):
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
