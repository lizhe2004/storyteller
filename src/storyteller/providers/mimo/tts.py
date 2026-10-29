from __future__ import annotations

import base64
import binascii
import json
import threading
from pathlib import Path

import requests

from ...core.exceptions import TTSError
from ...core.models import VoiceConfig
from ...core.streaming_tts import StreamingTTSProvider, StreamingTTSSession
from ...core.tts import CHUNK_AUDIO, StreamChunk, TTSProvider
from ..base import BaseProvider

_MODEL = 'mimo-v2.5-tts'
_VOICES = [('mimo_default', None, 'zh-CN'), ('冰糖', 'female', 'zh-CN'),
           ('茉莉', 'female', 'zh-CN'), ('苏打', 'male', 'zh-CN'),
           ('白桦', 'male', 'zh-CN'), ('Mia', 'female', 'en-US'),
           ('Chloe', 'female', 'en-US'), ('Milo', 'male', 'en-US'),
           ('Dean', 'male', 'en-US')]


class MiMoBufferedSession(StreamingTTSSession):
    """Buffer text until finish, then stream one MiMo response to the reader."""

    def __init__(self, provider, voice, directives, context):
        self.provider = provider
        self.voice = voice
        self.directives = directives
        self.context = context
        self._condition = threading.Condition()
        self._parts = []
        self._finished = False
        self._cancelled = False
        self._done = threading.Event()

    def send_text(self, text):
        with self._condition:
            if self._finished or self._cancelled:
                raise TTSError('MiMo TTS session is closed')
            self._parts.append(text)

    def finish(self):
        with self._condition:
            self._finished = True
            self._condition.notify_all()
        # The scheduler slot must remain held until the HTTP stream drains.
        self._done.wait()

    def cancel(self):
        with self._condition:
            self._cancelled = True
            self._condition.notify_all()

    def iter_audio(self):
        try:
            with self._condition:
                while not self._finished and not self._cancelled:
                    self._condition.wait()
                if self._cancelled:
                    return
                text = ''.join(self._parts)
            if not text.strip():
                return
            for chunk in self.provider.stream_synthesize(
                    text, self.voice, directives=self.directives, context=self.context):
                with self._condition:
                    if self._cancelled:
                        return
                yield chunk
        finally:
            self._done.set()


class MiMoTTS(BaseProvider, TTSProvider, StreamingTTSProvider):
    supports_streaming = True

    def __init__(self, config, provider_name='mimo'):
        super().__init__(config)
        self.provider_name = provider_name
        settings = config.get('tts.provider_config.{}'.format(provider_name), {}) or {}
        self.api_key = settings.get('api_key')
        self.base_url = (settings.get('base_url') or 'https://api.xiaomimimo.com/v1').rstrip('/')
        self.model = _MODEL
        if not self.api_key:
            raise TTSError('MiMo TTS api_key is missing (STORYTELLER_TTS_MIMO_API_KEY)')
        self._session = requests.Session()

    @property
    def name(self):
        return self.provider_name

    @property
    def display_name(self):
        return '小米 MiMo'

    @property
    def display_description(self):
        return 'MiMo-V2.5-TTS 语音合成'

    def list_voices(self, **kwargs):
        return [VoiceConfig(provider=self.name, voice_id=voice, name=voice,
                            model=_MODEL, gender=gender, language=language)
                for voice, gender, language in _VOICES]

    def open_stream(self, voice, *, directives=None, context=None):
        return MiMoBufferedSession(self, voice, directives, context)

    def list_models(self):
        return [{'id': _MODEL, 'retiring': False}]

    def _request(self, text, voice, format_, directives, stream):
        instruction = '，'.join(str(d).strip().lstrip('#').strip() for d in (directives or []) if d and str(d).strip().lstrip('#').strip())
        messages = ([{'role': 'user', 'content': instruction}] if instruction else [])
        messages.append({'role': 'assistant', 'content': text})
        body = {'model': _MODEL, 'messages': messages,
                'audio': {'format': format_, 'voice': voice.voice_id}, 'stream': stream}
        try:
            response = self._session.post(self.base_url + '/chat/completions',
                headers={'api-key': self.api_key, 'Content-Type': 'application/json'},
                json=body, stream=stream, timeout=60)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise TTSError('MiMo TTS request failed: {}'.format(exc)) from exc

    @staticmethod
    def _decode(value):
        try:
            return base64.b64decode(value, validate=True)
        except (ValueError, TypeError, binascii.Error) as exc:
            raise TTSError('Invalid MiMo TTS audio data') from exc

    def synthesize(self, text, voice_config, output_path, *, directives=None, context=None, **kwargs):
        path = Path(output_path)
        format_ = path.suffix.lower().lstrip('.')
        if format_ not in ('wav', 'mp3', 'pcm'):
            raise TTSError('MiMo TTS supports wav, mp3 and pcm output')
        response = self._request(text, voice_config, format_, directives, False)
        try:
            audio = response.json()['choices'][0]['message']['audio']['data']
            data = self._decode(audio)
            if not data:
                raise ValueError('empty audio')
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise TTSError('Invalid MiMo TTS response') from exc
        finally:
            response.close()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def stream_synthesize(self, text, voice_config, *, directives=None, context=None):
        response = self._request(text, voice_config, 'pcm16', directives, True)
        received = False
        try:
            for line in response.iter_lines():
                if isinstance(line, bytes):
                    line = line.decode('utf-8')
                if not line or not line.startswith('data:'):
                    continue
                payload = line[5:].strip()
                if payload == '[DONE]':
                    break
                data = json.loads(payload)
                if data.get('error'):
                    raise TTSError('MiMo TTS stream error: {}'.format(data['error']))
                for choice in data.get('choices', []):
                    audio = (choice.get('delta') or {}).get('audio') or {}
                    if audio.get('data'):
                        received = True
                        yield StreamChunk(CHUNK_AUDIO, self._decode(audio['data']))
            if not received:
                raise TTSError('MiMo TTS stream returned no audio')
        except (requests.RequestException, ValueError, UnicodeError, TypeError) as exc:
            raise TTSError('Invalid MiMo TTS stream: {}'.format(exc)) from exc
        finally:
            response.close()
