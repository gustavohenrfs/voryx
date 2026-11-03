from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import COOKIE_NAME, SESSION_MAX_AGE, sign_session, verify_password
from app.config import get_settings
from app.deps import current_user, get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    disabled: bool = False

    @classmethod
    def of(cls, u: User) -> "UserOut":
        return cls(id=u.id, email=u.email, name=u.name, role=u.role, disabled=u.disabled)


def client_ip(request: Request) -> str:
    # X-Real-IP is overwritten by our nginx; the first X-Forwarded-For hop is client-controlled.
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=UserOut)
async def login(body: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    limiter = request.app.state.login_limiter
    ip = client_ip(request)
    if not limiter.check(ip):
        raise HTTPException(429, "muitas tentativas, tente mais tarde")
    user = (
        await db.execute(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    ).scalar_one_or_none()
    if not user or user.disabled or not verify_password(user.password_hash, body.password):
        limiter.fail(ip)
        raise HTTPException(401, "email ou senha inválidos")
    s = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        sign_session(user.id, user.session_version),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        domain=s.cookie_domain or None,
    )
    return UserOut.of(user)


@router.post("/logout")
async def logout(response: Response):
    s = get_settings()
    response.delete_cookie(COOKIE_NAME, domain=s.cookie_domain or None)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return UserOut.of(user)
