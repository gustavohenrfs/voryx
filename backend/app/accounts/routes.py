from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.login import PendingLogin
from app.crypto import decrypt, encrypt
from app.deps import current_user, get_db, get_owned, owned
from app.models import AccountStatus, Channel, Job, PostStatus, ScheduledPost, TgAccount, User
from app.tg.types import (
    TgCodeExpired,
    TgError,
    TgFatalAuth,
    TgFloodWait,
    TgInvalidCode,
    TgInvalidPassword,
    TgNeedPassword,
    TgPhoneInvalid,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


class AccountOut(BaseModel):
    id: int
    label: str | None
    phone: str
    display_name: str | None
    status: str
    dead_reason: str | None
    last_seen_at: datetime | None
    created_at: datetime

    @classmethod
    def of(cls, a: TgAccount) -> "AccountOut":
        return cls(
            id=a.id,
            label=a.label,
            phone=a.phone,
            display_name=a.display_name,
            status=a.status,
            dead_reason=a.dead_reason,
            last_seen_at=a.last_seen_at,
            created_at=a.created_at,
        )


class LoginStart(BaseModel):
    phone: str = Field(min_length=5, max_length=32)
    api_id: int = Field(gt=0)
    api_hash: str = Field(min_length=5, max_length=64)
    label: str | None = Field(default=None, max_length=120)
    account_id: int | None = None


class LoginCode(BaseModel):
    login_id: str
    code: str = Field(min_length=1, max_length=16)


class LoginPassword(BaseModel):
    login_id: str
    password: str = Field(min_length=1, max_length=256)


class SessionImport(BaseModel):
    session: str = Field(min_length=10)


class AccountPatch(BaseModel):
    label: str | None = Field(default=None, max_length=120)


def tg_http_error(e: TgError) -> HTTPException:
    if isinstance(e, TgInvalidCode):
        return HTTPException(400, "código inválido")
    if isinstance(e, TgCodeExpired):
        return HTTPException(400, "código expirado, comece de novo")
    if isinstance(e, TgInvalidPassword):
        return HTTPException(400, "senha 2FA incorreta")
    if isinstance(e, TgPhoneInvalid):
        return HTTPException(400, "número inválido")
    if isinstance(e, TgFloodWait):
        return HTTPException(400, f"aguarde {e.seconds}s antes de tentar de novo")
    if isinstance(e, TgFatalAuth):
        return HTTPException(400, f"conta bloqueada pelo Telegram ({e.reason})")
    return HTTPException(400, f"erro do Telegram: {e}")


def _normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 5:
        raise HTTPException(422, "número inválido")
    return "+" + digits


async def _finish_login(request: Request, db: AsyncSession, user: User, entry: PendingLogin, session: str):
    acc = None
    if entry.account_id is not None:
        acc = await get_owned(db, TgAccount, entry.account_id, user)
    else:
        acc = (
            await db.execute(select(TgAccount).where(TgAccount.owner_id == user.id, TgAccount.phone == entry.phone))
        ).scalar_one_or_none()
    if acc is None:
        acc = TgAccount(owner_id=user.id, phone=entry.phone)
        db.add(acc)
    acc.label = entry.label or acc.label
    acc.api_id = entry.api_id
    acc.api_hash_enc = encrypt(entry.api_hash)
    acc.session_enc = encrypt(session)
    acc.status = AccountStatus.CONNECTING
    acc.dead_reason = None
    await db.commit()

    manager = request.app.state.manager
    await manager.add(acc.id, session)
    try:
        me = await manager.get(acc.id).get_me()
        acc = await db.get(TgAccount, acc.id)
        acc.tg_user_id, acc.display_name = me.id, me.name
    except Exception:  # noqa: BLE001 - status already reflects the problem
        pass
    db.add(Job(type="sync_channels", payload={"account_id": acc.id}, account_id=acc.id))
    await db.commit()
    await db.refresh(acc)
    return {"status": "ok", "account": AccountOut.of(acc)}


@router.get("", response_model=list[AccountOut])
async def list_accounts(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    rows = (await db.execute(owned(select(TgAccount), TgAccount, user).order_by(TgAccount.id))).scalars()
    return [AccountOut.of(a) for a in rows]


@router.post("/login/start")
async def login_start(
    body: LoginStart, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    if body.account_id is not None:
        await get_owned(db, TgAccount, body.account_id, user)
    phone = _normalize_phone(body.phone)
    try:
        handle = await request.app.state.gateway.start_login(phone, body.api_id, body.api_hash.strip())
    except TgError as e:
        raise tg_http_error(e) from e
    login_id = request.app.state.logins.create(
        user.id, handle, phone, body.api_id, body.api_hash.strip(), body.account_id, body.label
    )
    return {"login_id": login_id}


def _pending(request: Request, login_id: str, user: User) -> PendingLogin:
    entry = request.app.state.logins.get(login_id, user.id)
    if entry is None:
        raise HTTPException(404, "login expirado")
    return entry


@router.post("/login/code")
async def login_code(
    body: LoginCode, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    entry = _pending(request, body.login_id, user)
    try:
        session = await entry.handle.submit_code(body.code.strip())
    except TgNeedPassword:
        return {"status": "needs_password"}
    except TgError as e:
        if isinstance(e, TgCodeExpired):
            request.app.state.logins.pop(body.login_id)
        raise tg_http_error(e) from e
    request.app.state.logins.pop(body.login_id)
    return await _finish_login(request, db, user, entry, session)


@router.post("/login/password")
async def login_password(
    body: LoginPassword, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    entry = _pending(request, body.login_id, user)
    try:
        session = await entry.handle.submit_password(body.password)
    except TgError as e:
        raise tg_http_error(e) from e
    request.app.state.logins.pop(body.login_id)
    return await _finish_login(request, db, user, entry, session)


@router.post("/{account_id}/session", response_model=AccountOut)
async def import_session(
    account_id: int,
    body: SessionImport,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    acc = await get_owned(db, TgAccount, account_id, user)
    session = body.session.strip()
    gateway = request.app.state.gateway
    try:
        probe = await gateway.connect(session, acc.api_id, decrypt(acc.api_hash_enc))
        me = await probe.get_me()
        await probe.disconnect()
    except TgError as e:
        raise HTTPException(400, "session inválida") from e
    acc.session_enc = encrypt(session)
    acc.status = AccountStatus.CONNECTING
    acc.dead_reason = None
    acc.tg_user_id, acc.display_name = me.id, me.name
    await db.commit()
    await request.app.state.manager.add(acc.id, session)
    await db.refresh(acc)
    return AccountOut.of(acc)


@router.patch("/{account_id}", response_model=AccountOut)
async def patch_account(
    account_id: int, body: AccountPatch, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    acc = await get_owned(db, TgAccount, account_id, user)
    acc.label = body.label
    await db.commit()
    return AccountOut.of(acc)


@router.post("/{account_id}/check", response_model=AccountOut)
async def check_account(
    account_id: int, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    acc = await get_owned(db, TgAccount, account_id, user)
    await request.app.state.manager.check(acc.id)
    await db.refresh(acc)
    return AccountOut.of(acc)


@router.delete("/{account_id}")
async def delete_account(
    account_id: int, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    acc = await get_owned(db, TgAccount, account_id, user)
    in_use = (await db.execute(select(Channel.id).where(Channel.manager_account_id == acc.id))).first()
    if in_use:
        raise HTTPException(409, "a conta é gestora de um grupo — troque a conta gestora antes")
    await request.app.state.manager.remove(acc.id)
    await db.execute(delete(Job).where(Job.account_id == acc.id))
    await db.execute(
        update(ScheduledPost)
        .where(ScheduledPost.account_id == acc.id, ScheduledPost.status == PostStatus.SCHEDULED)
        .values(status=PostStatus.CANCELED, error="conta removida")
    )
    await db.execute(update(ScheduledPost).where(ScheduledPost.account_id == acc.id).values(account_id=None))
    await db.delete(acc)
    await db.commit()
    return {"ok": True}
