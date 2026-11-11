from pathlib import Path

import requests

from ...core.exceptions import TTSError
from ...core.sfx import SoundEffectProvider
from ..base import BaseProvider

_ENDPOINT = 'https://api.elevenlabs.io/v1/sound-generation'
_DEFAULT_MODEL = 'eleven_text_to_sound_v2'
_MP3_FORMATS = {22050: 'mp3_22050_32', 24000: 'mp3_24000_48', 44100: 'mp3_44100_128'}


class ElevenLabsSoundProvider(BaseProvider, SoundEffectProvider):
    """Text-to-sound effects through ElevenLabs' binary audio endpoint."""

    supports_duration_parameter = True
    cache_version = "english-structured-duration-v2"
    prompt_language = "en"

    def __init__(self, config, provider_name='elevenlabs', session=None):
        super().__init__(config)
        self.provider_name = provider_name
        settings = config.get('sound.provider_config.{}'.format(provider_name), {}) or {}
        self.api_key = settings.get('api_key')
        self.model = settings.get('model') or _DEFAULT_MODEL
        if not self.api_key:
            raise TTSError('ElevenLabs sound api_key is missing (STORYTELLER_SOUND_ELEVENLABS_API_KEY)')
        self._session = session or requests.Session()

    @property
    def name(self):
        return self.provider_name

    def generate(self, prompt, output_path, *, audio_format='mp3', sample_rate=None, references=None, duration_seconds=None):
        if (audio_format or 'mp3').lower().lstrip('.') != 'mp3':
            raise TTSError('ElevenLabs sound currently supports MP3 output only')
        if sample_rate is not None and sample_rate not in _MP3_FORMATS:
            raise TTSError('Unsupported ElevenLabs MP3 sample rate')
        if references:
            raise TTSError('ElevenLabs sound generation does not support reference audio')
        if not isinstance(prompt, str) or not prompt.strip():
            raise TTSError('ElevenLabs sound prompt must not be empty')
        body = {'text': prompt, 'model_id': self.model}
        if duration_seconds is not None:
            body['duration_seconds'] = max(0.5, min(30.0, float(duration_seconds)))
        response = None
        try:
            response = self._session.post(
                _ENDPOINT,
                headers={'xi-api-key': self.api_key, 'Content-Type': 'application/json'},
                params={'output_format': _MP3_FORMATS[sample_rate or 44100]},
                json=body, timeout=300,
            )
            response.raise_for_status()
            data = response.content
        except requests.RequestException:
            status = getattr(response, 'status_code', None)
            raise TTSError('ElevenLabs sound request failed{}'.format(
                ' (HTTP {})'.format(status) if status is not None else '')) from None
        finally:
            if response is not None:
                response.close()
        if not data:
            raise TTSError('ElevenLabs sound returned no audio data')
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data)
        return output_path, None
