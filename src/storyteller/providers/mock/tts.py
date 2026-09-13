from __future__ import annotations

import wave
import math
import struct
from pathlib import Path

from ...core.models import VoiceConfig
from ...core.tts import TTSProvider, StreamChunk, CHUNK_AUDIO, STREAM_SAMPLE_RATE
from ...providers.base import BaseProvider


MOCK_VOICES = [
    VoiceConfig(
        provider="mock",
        voice_id="narrator_01",
        language="zh-CN",
        name="少儿故事",
        gender="female",
        age="young_adult",
        category="有声阅读",
        description="语调活泼亲切，适配儿童故事的治愈旁白女声",
    ),
    VoiceConfig(
        provider="mock",
        voice_id="male_01",
        language="zh-CN",
        name="青年男声",
        gender="male",
        age="young_adult",
        category="通用场景",
        description="阳光清亮的青年男声",
    ),
    VoiceConfig(
        provider="mock",
        voice_id="female_01",
        language="zh-CN",
        name="温柔妈妈",
        gender="female",
        age="middle_aged",
        category="通用场景",
        description="语调舒缓、咬字温润，自带母性柔光的治愈女声",
    ),
    VoiceConfig(
        provider="mock",
        voice_id="child_01",
        language="zh-CN",
        name="稚嫩童声",
        gender="male",
        age="child",
        category="角色扮演",
        description="天真活泼的儿童声音",
    ),
]


def _write_silence_wav(path, duration_ms=100, frame_rate=16000):
    """Write a real silent WAV file using the stdlib wave module.

    pydub/ffmpeg can read this regardless of the file extension.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n_frames = int(frame_rate * duration_ms / 1000)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(frame_rate)
        wf.writeframes(b"\x00\x00" * n_frames)


class MockTTSProvider(BaseProvider, TTSProvider):
    """TTS provider that writes silent placeholder audio files. Used for tests."""

    def __init__(self, config):
        super().__init__(config)
        self._error = None
        self.synth_calls = []

    @property
    def name(self):
        return "mock"

    @property
    def display_name(self):
        return "Mock（测试）"

    @property
    def display_description(self):
        return "测试用桩 provider，合成结果为静音音频"

    def list_voices(self, **kwargs):
        return list(MOCK_VOICES)

    def set_error(self, error):
        """Configure an error that subsequent synthesize() calls raise."""
        self._error = error

    def synthesize(self, text, voice_config, output_path, **kwargs):
        self.synth_calls.append(
            {
                "text": text,
                "voice_config": voice_config,
                "output_path": str(output_path),
                "kwargs": kwargs,
            }
        )
        if self._error is not None:
            raise self._error
        _write_silence_wav(output_path)
        return Path(output_path)


class MockStreamingTTS(MockTTSProvider):
    supports_streaming = True

    def stream_synthesize(self, text, voice_config, *, directives=None, context=None):
        self.synth_calls.append({
            "text": text, "voice_config": voice_config, "output_path": None,
            "kwargs": {"directives": directives, "context": context},
        })
        if self._error is not None:
            raise self._error
        samples = STREAM_SAMPLE_RATE // 2
        pcm = bytearray()
        for i in range(samples):
            value = int(0.2 * 32767 * math.sin(2 * math.pi * 220 * i / STREAM_SAMPLE_RATE))
            pcm.extend(struct.pack("<h", value))
        block = STREAM_SAMPLE_RATE * 2 // 10
        for off in range(0, len(pcm), block):
            yield StreamChunk(CHUNK_AUDIO, bytes(pcm[off:off + block]))
