from fastapi import APIRouter, HTTPException, Request, Response

from .auth import SESSION_COOKIE, check_password
from .schemas import AuthRequest

router = APIRouter()


@router.post("/api/auth", status_code=204)
def login(body: AuthRequest, request: Request, response: Response):
    state = request.app.state
    if not state.limiter.allow(request.client.host if request.client else "?"):
        raise HTTPException(status_code=429, detail="请求过于频繁")
    if not check_password(body.password, state.config.get("web.passwords") or []):
        raise HTTPException(status_code=401, detail="密码错误")
    response.set_cookie(SESSION_COOKIE, state.issuer.issue(), httponly=True,
                        samesite="lax", secure=request.url.scheme == "https",
                        path="/", max_age=state.config.get("web.token_ttl_days") * 86400)


@router.post("/api/auth/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/api/me")
def me(request: Request):
    return {"authenticated": request.app.state.issuer.verify(
        request.cookies.get(SESSION_COOKIE))}
