from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import COOKIE_NAME, read_session
from app.models import Role, User

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_HEADER = "X-Voryx-CSRF"


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


async def csrf_guard(request: Request) -> None:
    if request.method in WRITE_METHODS and request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(403, "CSRF header ausente")


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    parsed = read_session(token) if token else None
    if not parsed:
        raise HTTPException(401, "não autenticado")
    user_id, version = parsed
    user = await db.get(User, user_id)
    if not user or user.disabled or user.session_version != version:
        raise HTTPException(401, "não autenticado")
    return user


async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != Role.ADMIN:
        raise HTTPException(403, "acesso restrito")
    return user


def owned(stmt: Select, model, user: User) -> Select:
    """Scope a select to the user's rows (admin sees all)."""
    if user.role == Role.ADMIN:
        return stmt
    return stmt.where(model.owner_id == user.id)


async def get_owned[M](db: AsyncSession, model: type[M], obj_id: int, user: User) -> M:
    obj = await db.get(model, obj_id)
    if obj is None or (user.role != Role.ADMIN and obj.owner_id != user.id):
        raise HTTPException(404, "não encontrado")
    return obj
