from fastapi import APIRouter, HTTPException, Request

from ..providers.aliyun.tts import load_voice_catalog
from .auth import SESSION_COOKIE

router = APIRouter()

_DEFAULT_MODELS = {
    ("tts", "volcengine"): "seed-tts-2.0",
    ("tts", "openai_compatible"): "tts-1",
}


def configured_models(config, group, provider, include_fallback=True):
    """Configured default model plus the user-curated candidate list."""
    values = config.get("{}.provider_config.{}".format(group, provider), {}) or {}
    result = []
    current = values.get("model") or values.get("resource_id")
    if current:
        result.append(str(current))
    for item in str(values.get("models") or "").split(","):
        item = item.strip()
        if item and item not in result:
            result.append(item)
    fallback = (
        _DEFAULT_MODELS.get((group, str(values.get("type") or "").lower()))
        if include_fallback
        else None
    )
    if fallback and fallback not in result:
        result.append(fallback)
    return result


def _catalog_model_name(record):
    if isinstance(record, str):
        return record.strip()
    if isinstance(record, dict):
        return str(record.get("model") or "").strip()
    return ""


def _audio_models(config):
    result = []
    for provider in config.get("tts.providers", []) or []:
        names = configured_models(config, "tts", provider)
        if not names and provider.lower() == "aliyun":
            # 白名单为空表示不限制：下拉提供本地音色目录里的全部模型；
            # 一旦后台勾选了模型，下拉严格等于勾选集合。
            try:
                records = load_voice_catalog()
            except (OSError, ValueError):
                records = []
            names.extend(
                model for model in (_catalog_model_name(record) for record in records)
                if model
            )
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
        values = (
            config.get("llm.provider_config.{}".format(provider), {}) or {}
        )
        default_model = str(values.get("model") or "")
        for model in configured_models(
            config, "llm", provider, include_fallback=False
        ):
            llm_models.append({
                "provider": provider,
                "model": model,
                "label": "{} / {}".format(provider, model),
                "is_default": model == default_model,
            })
    return {
        "lengths": ["short", "medium", "long"],
        "complexities": ["simple", "medium", "rich"],
        "tts_providers": [{"name": n} for n in request.app.state.registry.list_tts_names()],
        "sound_enabled": bool(request.app.state.config.get("sound.enabled")),
        "llm_models": llm_models,
        "audio_models": _audio_models(config),
    }
