from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

import requests

from ...core.exceptions import TTSError
from ...core.models import VoiceConfig
from ...core.tts import TTSProvider
from ..base import BaseProvider

_DEFAULT_ENDPOINT = "https://dashscope.aliyuncs.com"
_API_PATH = "/api/v1/services/audio/tts/SpeechSynthesizer"
logger = logging.getLogger(__name__)


class AliyunTTS(BaseProvider, TTSProvider):
    """Aliyun Bailian (Model Studio) text-to-speech provider.

    Speaks the Qwen-Audio-TTS model family through the non-streaming
    SpeechSynthesizer HTTP API: the response carries a 24-hour audio URL
    which is downloaded immediately so artifacts never depend on it.
    """

    def __init__(self, config):
        super().__init__(config)
        provider_config = config.get(
            "tts.provider_config.aliyun", {}
        ) or {}
        self.api_key = provider_config.get("api_key")
        endpoint = (
            provider_config.get("endpoint") or _DEFAULT_ENDPOINT
        ).rstrip("/")
        self.endpoint = (
            endpoint
            if endpoint.endswith(_API_PATH)
            else endpoint + _API_PATH
        )
        # Default model for voices absent from the packaged catalog
        # (e.g. cloned voices). Catalog voices carry their own model.
        self.model = provider_config.get("model")

        if not self.api_key:
            raise TTSError(
                "Aliyun TTS api_key is missing "
                "(STORYTELLER_TTS_ALIYUN_API_KEY)"
            )

        self._session = requests.Session()

    @property
    def name(self):
        return "aliyun"

    @property
    def display_name(self):
        return "阿里云百炼"

    @property
    def display_description(self):
        return "Qwen-Audio-TTS 语音合成（阿里云百炼）"

    def list_voices(self, **kwargs):
        return [
            VoiceConfig(
                provider="aliyun",
                voice_id=record["voice_id"],
                language=record.get("language", "zh-CN"),
                name=record.get("name"),
                gender=record.get("gender"),
                age=record.get("age"),
                category=record.get("category"),
                description=record.get("description"),
            )
            for record in load_voice_catalog()
        ]

    def synthesize(
        self,
        text,
        voice_config,
        output_path,
        directives=None,
        context=None,
        **kwargs,
    ):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        model = self._model_for(voice_config.voice_id)
        audio_format = _encoding_for_path(output_path)
        req_input = {
            "text": text,
            "voice": voice_config.voice_id,
            "format": audio_format,
            # opus is only supported at 48 kHz; other formats use 24 kHz.
            "sample_rate": 48000 if audio_format == "opus" else 24000,
        }

        # rate/pitch are native 0.5..2.0 multipliers, same scale as
        # VoiceConfig; volume is a 0..100 integer centered at 50.
        rate = _clamp(voice_config.speed, 0.5, 2.0)
        pitch = _clamp(voice_config.pitch, 0.5, 2.0)
        if rate != 1.0:
            req_input["rate"] = rate
        if pitch != 1.0:
            req_input["pitch"] = pitch
        if voice_config.volume != 1.0:
            req_input["volume"] = _clamp(
                int(round((voice_config.volume - 1.0) * 50)) + 50, 0, 100
            )

        instruction = _build_instruction(directives)
        if instruction:
            req_input["instruction"] = instruction

        headers = {
            "Authorization": "Bearer {}".format(self.api_key),
            "Content-Type": "application/json",
        }
        body = {"model": model, "input": req_input}

        response = None
        try:
            response = self._session.post(
                self.endpoint,
                headers=headers,
                json=body,
                timeout=120,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            error_payload = _response_payload(response)
            logger.error(
                "event=tts_request_failed provider=aliyun model=%s "
                "voice_id=%s request_input_json=%s http_status=%s "
                "response_code=%s response_message=%s request_id=%s",
                model,
                voice_config.voice_id,
                json.dumps(req_input, ensure_ascii=False, separators=(",", ":")),
                getattr(response, "status_code", None),
                error_payload.get("code"),
                error_payload.get("message"),
                error_payload.get("request_id"),
            )
            raise TTSError(
                "Aliyun TTS request failed: {}".format(
                    _error_detail(exc, response)
                )
            ) from exc
        except ValueError as exc:
            _log_request_failure(
                "non_json_response", model, voice_config, req_input, response
            )
            raise TTSError(
                "Aliyun TTS returned a non-JSON response"
            ) from exc

        audio_url = (
            payload.get("output", {}).get("audio", {}).get("url")
            if isinstance(payload, dict)
            else None
        )
        if not audio_url:
            _log_request_failure(
                "missing_audio_url", model, voice_config, req_input, response,
                payload=payload,
            )
            raise TTSError("Aliyun TTS returned no audio URL")

        download = None
        try:
            download = self._session.get(audio_url, timeout=60)
            download.raise_for_status()
            audio_bytes = download.content
        except requests.RequestException as exc:
            # Never echo str(exc) here: requests' HTTP/connection errors
            # embed the signed audio URL, a 24h credential, and this text
            # flows into pipeline error logs. The chained traceback
            # (from exc) stays local and keeps the detail for debugging.
            status_code = getattr(download, "status_code", None)
            _log_request_failure(
                "audio_download_failed", model, voice_config, req_input,
                response, payload={"download_http_status": status_code},
            )
            if status_code is not None:
                detail = "HTTP {}".format(status_code)
            else:
                detail = "network error ({})".format(type(exc).__name__)
            raise TTSError(
                "Aliyun TTS audio download failed: {}".format(detail)
            ) from exc

        if not audio_bytes:
            raise TTSError("Aliyun TTS audio download was empty")

        output_path.write_bytes(bytes(audio_bytes))
        return output_path

    def _model_for(self, voice_id):
        record = load_voice_index().get(voice_id)
        if record:
            return record["model"]
        if self.model:
            return self.model
        raise TTSError(
            "No Aliyun TTS model for voice {!r} and no default model "
            "configured".format(voice_id)
        )


def _encoding_for_path(output_path):
    suffix = output_path.suffix.lower().lstrip(".")
    if suffix in ("mp3", "wav", "pcm", "opus", "ogg"):
        if suffix == "ogg":
            return "opus"
        return suffix
    return "mp3"


def _clamp(value, low, high):
    return max(low, min(high, value))


def _build_instruction(directives):
    """Collapse acting directives into Aliyun's single `instruction`.

    Volcengine separates directives (#-prefixed) from quoted context;
    Aliyun has one instruction string, so directives are joined and the
    quoted context is dropped.
    """
    parts = []
    for d in directives or []:
        d = (d or "").strip().lstrip("#").strip()
        if d:
            parts.append(d)
    return "，".join(parts)


def _error_detail(exc, response):
    """Prefer the server's message field, fall back to the exception text."""
    if response is not None:
        try:
            payload = response.json()
        except (ValueError, AttributeError):
            payload = None
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("code")
            if message:
                return message
    return str(exc)


def _response_payload(response):
    if response is None:
        return {}
    try:
        payload = response.json()
    except (ValueError, AttributeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _log_request_failure(reason, model, voice_config, req_input, response,
                         payload=None):
    payload = payload if payload is not None else _response_payload(response)
    logger.error(
        "event=tts_request_diagnostic provider=aliyun reason=%s model=%s "
        "voice_id=%s request_input_json=%s http_status=%s response_code=%s "
        "response_message=%s request_id=%s",
        reason,
        model,
        voice_config.voice_id,
        json.dumps(req_input, ensure_ascii=False, separators=(",", ":")),
        getattr(response, "status_code", None),
        payload.get("code"),
        payload.get("message"),
        payload.get("request_id"),
    )


@lru_cache(maxsize=1)
def load_voice_catalog():
    """Return the packaged Aliyun voice records as a list of dicts.

    Each record has voice_id, name, model, gender, age, category,
    description, tags, language, bilingual. Cached.
    """
    data = json.loads(_VOICE_CATALOG.read_text(encoding="utf-8"))
    return data["voices"]


@lru_cache(maxsize=1)
def load_voice_index():
    """Map voice_id -> record for the packaged catalog."""
    return {v["voice_id"]: v for v in load_voice_catalog()}


_VOICE_CATALOG = Path(__file__).with_name("voices.json")
