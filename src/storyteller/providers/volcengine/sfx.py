from __future__ import annotations

import base64
import uuid
from pathlib import Path

import requests

from ...core.exceptions import TTSError
from ...core.sfx import SoundEffectProvider
from ..base import BaseProvider

_DEFAULT_ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/create"
_DEFAULT_MODEL = "seed-audio-1.0"


class VolcengineSoundProvider(BaseProvider, SoundEffectProvider):
    """Volcengine seed-audio text-to-sound provider.

    Non-streaming ``POST /api/v3/tts/create``: turns a natural-language
    ``text_prompt`` into a sound effect / ambient bed / music clip (no
    dictated speech). Reads its dedicated key from STORYTELLER_SOUND_VOLCENGINE_API_KEY;
    there is no fallback to the TTS key.
    """

    def __init__(self, config, session=None):
        super().__init__(config)
        sound_cfg = config.get("sound.provider_config.volcengine", {}) or {}

        self.api_key = sound_cfg.get("api_key")
        self.endpoint = (
            sound_cfg.get("endpoint") or _DEFAULT_ENDPOINT
        ).rstrip("/")
        self.model = sound_cfg.get("model") or _DEFAULT_MODEL

        if not self.api_key:
            raise TTSError(
                "Volcengine sound api_key is missing: set "
                "STORYTELLER_SOUND_VOLCENGINE_API_KEY"
            )

        self._session = session or requests.Session()

    @property
    def name(self):
        return "volcengine"

    def generate(
        self,
        prompt,
        output_path,
        *,
        audio_format="mp3",
        sample_rate=None,
        references=None,
    ):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fmt = _api_format(audio_format)
        audio_config = {
            "format": fmt,
            "sample_rate": sample_rate or _default_sample_rate(fmt),
        }
        body = {
            "model": self.model,
            "text_prompt": prompt,
            "audio_config": audio_config,
        }
        if references:
            body["references"] = references

        headers = {
            "X-Api-Key": self.api_key,
            "X-Api-Request-Id": uuid.uuid4().hex,
            "Content-Type": "application/json",
        }

        try:
            resp = self._session.post(
                self.endpoint,
                headers=headers,
                json=body,
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise TTSError(
                "Volcengine sound request failed: {}".format(exc)
            ) from exc

        code = data.get("code", 0)
        if code not in (0, None):
            raise TTSError(
                "Volcengine sound error (code {}): {}".format(
                    code, data.get("message", "unknown")
                )
            )

        audio_bytes = _decode_audio(data)
        if audio_bytes is None:
            url = data.get("url")
            if url:
                audio_bytes = self._download(url)
        if not audio_bytes:
            raise TTSError("Volcengine sound returned no audio data")

        output_path.write_bytes(audio_bytes)
        duration = data.get("duration") or data.get("original_duration")
        try:
            duration = float(duration) if duration is not None else None
        except (TypeError, ValueError):
            duration = None
        return output_path, duration

    def _download(self, url):
        resp = None
        try:
            resp = self._session.get(url, timeout=300)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as exc:
            # Never echo str(exc) here: requests' HTTP/connection errors
            # embed the signed audio URL, a short-lived credential, and
            # this text flows into pipeline error logs. The chained
            # traceback (from exc) stays local for debugging.
            status_code = getattr(resp, "status_code", None)
            if status_code is not None:
                detail = "HTTP {}".format(status_code)
            else:
                detail = "network error ({})".format(type(exc).__name__)
            raise TTSError(
                "Failed to download generated sound: {}".format(detail)
            ) from exc


def _decode_audio(data):
    """Return decoded bytes from an inline base64 field, else None."""
    for key in ("audio", "data"):
        payload = data.get(key)
        if not payload:
            continue
        if isinstance(payload, dict):
            payload = payload.get("data") or payload.get("audio")
        if not payload:
            continue
        try:
            return base64.b64decode(payload)
        except (ValueError, TypeError):
            continue
    return None


def _api_format(audio_format):
    fmt = (audio_format or "mp3").lower().lstrip(".")
    if fmt == "ogg":
        return "ogg_opus"
    if fmt in ("mp3", "wav", "ogg_opus", "pcm"):
        return fmt
    return "mp3"


def _default_sample_rate(fmt):
    # Per the seed-audio docs: mp3 defaults to 44.1 kHz, ogg_opus must be
    # 48 kHz, wav/pcm use 24 kHz.
    if fmt == "ogg_opus":
        return 48000
    if fmt == "mp3":
        return 44100
    return 24000
