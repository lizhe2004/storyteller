from fastapi import APIRouter, HTTPException, Request
from pathlib import Path
import json

from .auth import SESSION_COOKIE

router = APIRouter()

_DEFAULT_MODELS = {
    ("llm", "volcengine"): "deepseek-v4-flash-260425",
    ("llm", "openai_compatible"): "gpt-4o-mini",
    ("tts", "volcengine"): "seed-tts-2.0",
    ("tts", "openai_compatible"): "tts-1",
}


def _configured_models(config, group, provider):
    values = config.get("{}.provider_config.{}".format(group, provider), {}) or {}
    result = []
    current = values.get("model") or values.get("resource_id")
    if current:
        result.append(str(current))
    for item in str(values.get("models") or "").split(","):
        item = item.strip()
        if item and item not in result:
            result.append(item)
    fallback = _DEFAULT_MODELS.get((group, str(values.get("type") or "").lower()))
    if fallback and fallback not in result:
        result.append(fallback)
    return result


def _audio_models(config):
    result = []
    for provider in config.get("tts.providers", []) or []:
        names = _configured_models(config, "tts", provider)
        if provider.lower() == "aliyun":
            catalog = Path(__file__).resolve().parent.parent / "providers" / "aliyun" / "voices.json"
            try:
                records = json.loads(catalog.read_text(encoding="utf-8"))
                names.extend(str(record.get("model")) for record in records if record.get("model"))
            except (OSError, ValueError):
                pass
        for model in dict.fromkeys(names):
            result.append({"provider": provider, "model": model,
                           "label": "{} / {}".format(provider, model)})
    return result


def _require(request):
    if not request.app.state.issuer.verify(request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(status_code=401, detail="未登录")


@router.get("/api/config/options")
def options(request: Request):
    _require(request)
    config = request.app.state.config
    llm_models = []
    for provider in config.get("llm.providers", []) or []:
        for model in _configured_models(config, "llm", provider):
            llm_models.append({"provider": provider, "model": model,
                               "label": "{} / {}".format(provider, model)})
    return {
        "lengths": ["short", "medium", "long"],
        "complexities": ["simple", "medium", "rich"],
        "tts_providers": [{"name": n} for n in request.app.state.registry.list_tts_names()],
        "sound_enabled": bool(request.app.state.config.get("sound.enabled")),
        "llm_models": llm_models,
        "audio_models": _audio_models(config),
    }
