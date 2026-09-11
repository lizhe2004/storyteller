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
