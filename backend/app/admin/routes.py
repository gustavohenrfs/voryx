from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.routes import UserOut
from app.auth.security import hash_password
from app.deps import get_db, require_admin
from app.models import Role, User

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    role: str = Role.PARTNER


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    disabled: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)


@router.get("/users", response_model=list[UserOut])
async def list_users(db: AsyncSession = Depends(get_db)):
    users = (await db.execute(select(User).order_by(User.id))).scalars()
    return [UserOut.of(u) for u in users]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db)):
    if body.role not in (Role.ADMIN, Role.PARTNER):
        raise HTTPException(422, "papel inválido")
    email = body.email.strip().lower()
    exists = (await db.execute(select(User.id).where(func.lower(User.email) == email))).first()
    if exists:
        raise HTTPException(409, "email já cadastrado")
    u = User(email=email, name=body.name, role=body.role, password_hash=hash_password(body.password))
    db.add(u)
    await db.commit()
    return UserOut.of(u)


@router.patch("/users/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: int, body: UserPatch, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)
):
    u = await db.get(User, user_id)
    if not u:
        raise HTTPException(404, "não encontrado")
    if body.disabled is not None:
        if u.id == admin.id and body.disabled:
            raise HTTPException(422, "não é possível desativar a si mesmo")
        u.disabled = body.disabled
        u.session_version += 1
    if body.password is not None:
        u.password_hash = hash_password(body.password)
        u.session_version += 1
    if body.name is not None:
        u.name = body.name
    await db.commit()
    return UserOut.of(u)
