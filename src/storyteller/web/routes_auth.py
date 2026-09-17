import hmac
import secrets

from fastapi import APIRouter, HTTPException, Request, Response

from .auth import SESSION_COOKIE, check_password, hash_password
from .schemas import AuthRequest, SetupRequest

router = APIRouter()


@router.get("/api/auth/status")
def auth_status(request: Request):
    state = request.app.state
    return {
        "setup_required": not bool(state.config.get("web.passwords")),
        "setup_available": bool(state.setup_code),
    }


@router.post("/api/auth", status_code=204)
def login(body: AuthRequest, request: Request, response: Response):
    state = request.app.state
    if not state.config.get("web.passwords"):
        raise HTTPException(status_code=409, detail="请先完成首次密码设置")
    if not state.limiter.allow(request.client.host if request.client else "?"):
        raise HTTPException(status_code=429, detail="请求过于频繁")
    if not check_password(body.password, state.config.get("web.passwords") or []):
        raise HTTPException(status_code=401, detail="密码错误")
    response.set_cookie(SESSION_COOKIE, state.issuer.issue(), httponly=True,
                        samesite="lax", secure=request.url.scheme == "https",
                        path="/", max_age=state.config.get("web.token_ttl_days") * 86400)


@router.post("/api/auth/setup", status_code=204)
def setup(body: SetupRequest, request: Request, response: Response):
    state = request.app.state
    if not state.limiter.allow(request.client.host if request.client else "?"):
        raise HTTPException(status_code=429, detail="请求过于频繁")
    if len(body.password) < 8:
        raise HTTPException(status_code=422, detail="密码至少需要 8 个字符")
    with state.setup_lock:
        if state.config.get("web.passwords") or not state.setup_code:
            raise HTTPException(status_code=409, detail="首次设置已完成")
        if not hmac.compare_digest(body.code, state.setup_code):
            raise HTTPException(status_code=401, detail="初始化码错误")
        secret = secrets.token_hex(32)
        state.runtime_settings.update({"web": {
            "passwords": [hash_password(body.password)],
            "secret": secret,
        }})
        state.setup_code = None
        current = state.refresh_runtime_config()
    response.set_cookie(
        SESSION_COOKIE, state.issuer.issue(), httponly=True,
        samesite="lax", secure=request.url.scheme == "https", path="/",
        max_age=current.get("web.token_ttl_days") * 86400,
    )


@router.post("/api/auth/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/api/me")
def me(request: Request):
    return {"authenticated": request.app.state.issuer.verify(
        request.cookies.get(SESSION_COOKIE))}
