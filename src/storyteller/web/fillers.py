from __future__ import annotations

import hashlib
import re
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ..core.voice_matcher import is_narration_voice

_INTRO = ("故事就要开始喽，准备好了吗？", "那我们开始啦，认真听哦。",
          "故事就要开始了，我们一起来听吧。")


def _clean(text, topic):
    value = (text or "").strip().strip('“”"\'「」\n\t')
    value = re.sub(r"^(好的，?|嗯，?|OK，?)", "", value).strip()
    value = re.sub(r"\s+", "", value)
    if not value:
        value = "好的，关于{}的故事，让我好好想一想……".format(str(topic)[:20])
    if len(value) > 50:
        cut = value[:50]
        pos = max(cut.rfind("，"), cut.rfind("。"))
        value = cut[:pos] if pos > 12 else cut
    return value


def build_thinking_text(llm, topic):
    system = ("你是儿童故事应用的主持人。请从用户主题提取关键诉求，"
              "用温暖口语复述并表示要去构思。只输出口播文本，无引号、markdown、"
              "emoji 或称呼前缀，1-2句，不超过50个汉字，严禁开始讲故事。")
    try:
        return _clean(llm.chat([{"role": "system", "content": system},
                                {"role": "user", "content": str(topic)}],
                               temperature=0.3, max_tokens=150), topic)
    except Exception:
        return "好的，关于{}的故事，让我好好想一想……".format(str(topic)[:20])


def intro_text():
    return random.choice(_INTRO)


def choose_host_voice(registry, tts_names, filler_voice=None):
    if filler_voice and ":" in filler_voice:
        name, voice_id = filler_voice.split(":", 1)
        if name in tts_names:
            for voice in registry.get_tts(name).list_voices():
                if voice.voice_id == voice_id:
                    return name, voice
    for name in tts_names:
        voices = registry.get_tts(name).list_voices()
        for voice in voices:
            if is_narration_voice(voice):
                return name, voice
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
        self.registry, self.llm_name, self.tts_names = registry, llm_name, tts_names
        self.cache_dir = Path(cache_dir) / "fillers"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.host = choose_host_voice(registry, tts_names, filler_voice)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="filler")
        self._futures = {}

    def _synth(self, kind, text):
        if not self.host:
            return None
        provider, voice = self.host
        key = hashlib.sha256("|".join((provider, voice.voice_id,
                                        str(voice.speed), str(voice.pitch), text)).encode()).hexdigest()
        path = self.cache_dir / (key + ".mp3")
        if not path.exists():
            self.registry.get_tts(provider).synthesize(text, voice, path)
        return FillerClip(kind, text, str(path))

    def start(self, topic, on_thinking_text=None, on_thinking_ready=None):
        def prepare_thinking():
            text = build_thinking_text(self.registry.get_llm(self.llm_name), topic)
            if on_thinking_text:
                on_thinking_text(text)
            clip = self._synth("thinking", text)
            if clip and on_thinking_ready:
                on_thinking_ready(clip)
            return clip
        self._futures["thinking"] = self._executor.submit(prepare_thinking)
        self._futures["intro"] = self._executor.submit(
            lambda: self._synth("intro", intro_text()))

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
        self._executor.shutdown(wait=False)
