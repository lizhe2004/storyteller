from fastapi import APIRouter, HTTPException, Request

from .auth import SESSION_COOKIE

router = APIRouter()


def _require(request):
    if not request.app.state.issuer.verify(request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(status_code=401, detail="未登录")


@router.get("/api/config/options")
def options(request: Request):
    _require(request)
    return {
        "lengths": ["short", "medium", "long"],
        "complexities": ["simple", "medium", "rich"],
        "tts_providers": [{"name": n} for n in request.app.state.registry.list_tts_names()],
        "sound_enabled": bool(request.app.state.config.get("sound.enabled")),
    }
