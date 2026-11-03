from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.service import apply_info, ref_of, refresh_channel
from app.deps import current_user, get_db, get_owned, owned
from app.models import (
    Channel,
    ChannelAdmin,
    JoinMode,
    JoinRequest,
    JoinStatus,
    PostStatus,
    ScheduledPost,
    TgAccount,
    User,
)
from app.tg.http import tg_call

router = APIRouter(tags=["channels"])


class ChannelOut(BaseModel):
    id: int
    title: str
    username: str | None
    kind: str
    member_count: int | None
    status: str
    join_mode: str
    manager_account_id: int | None
    pending_count: int
    last_synced_at: datetime | None


class AdminOut(BaseModel):
    tg_user_id: int
    name: str
    rights: dict[str, bool]


class ChannelDetail(ChannelOut):
    admins: list[AdminOut]


class DialogOut(BaseModel):
    chat_id: int
    title: str
    username: str | None
    kind: str
    member_count: int | None


class ChannelImport(BaseModel):
    account_id: int
    chat_id: int


class ChannelPatch(BaseModel):
    manager_account_id: int | None = None
    join_mode: Literal["auto", "manual"] | None = None


async def _pending_counts(db: AsyncSession, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    rows = await db.execute(
        select(JoinRequest.channel_id, func.count())
        .where(JoinRequest.channel_id.in_(ids), JoinRequest.status == JoinStatus.PENDING)
        .group_by(JoinRequest.channel_id)
    )
    return dict(rows.all())


def _out(ch: Channel, pending: int) -> ChannelOut:
    return ChannelOut(
        id=ch.id,
        title=ch.title,
        username=ch.username,
        kind=ch.kind,
        member_count=ch.member_count,
        status=ch.status,
        join_mode=ch.join_mode,
        manager_account_id=ch.manager_account_id,
        pending_count=pending,
        last_synced_at=ch.last_synced_at,
    )


async def _detail(db: AsyncSession, ch: Channel) -> ChannelDetail:
    admins = (
        await db.execute(select(ChannelAdmin).where(ChannelAdmin.channel_id == ch.id).order_by(ChannelAdmin.id))
    ).scalars()
    pending = (await _pending_counts(db, [ch.id])).get(ch.id, 0)
    return ChannelDetail(
        **_out(ch, pending).model_dump(),
        admins=[AdminOut(tg_user_id=a.tg_user_id, name=a.name, rights=a.rights) for a in admins],
    )


@router.get("/accounts/{account_id}/dialogs", response_model=list[DialogOut])
async def available_dialogs(
    account_id: int, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    acc = await get_owned(db, TgAccount, account_id, user)
    dialogs = await tg_call(request.app.state.manager, acc.id, lambda c: c.list_admin_dialogs())
    imported = set(
        (await db.execute(select(Channel.tg_chat_id).where(Channel.owner_id == acc.owner_id))).scalars().all()
    )
    return [
        DialogOut(chat_id=d.chat_id, title=d.title, username=d.username, kind=d.kind, member_count=d.member_count)
        for d in dialogs
        if d.chat_id not in imported
    ]


@router.post("/channels", response_model=ChannelDetail, status_code=201)
async def import_channel(
    body: ChannelImport, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    acc = await get_owned(db, TgAccount, body.account_id, user)
    exists = (
        await db.execute(select(Channel.id).where(Channel.owner_id == acc.owner_id, Channel.tg_chat_id == body.chat_id))
    ).first()
    if exists:
        raise HTTPException(409, "grupo já importado")
    manager = request.app.state.manager
    dialogs = await tg_call(manager, acc.id, lambda c: c.list_admin_dialogs())
    info = next((d for d in dialogs if d.chat_id == body.chat_id), None)
    if info is None:
        raise HTTPException(404, "grupo não encontrado nesta conta (ela precisa ser admin)")
    ch = Channel(
        owner_id=acc.owner_id,
        tg_chat_id=info.chat_id,
        title=info.title,
        kind=info.kind,
        manager_account_id=acc.id,
        join_mode=JoinMode.MANUAL,
    )
    apply_info(ch, info)
    db.add(ch)
    await db.flush()
    await refresh_channel(db, ch, manager)
    await db.commit()
    return await _detail(db, ch)


@router.get("/channels", response_model=list[ChannelOut])
async def list_channels(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    chans = (await db.execute(owned(select(Channel), Channel, user).order_by(Channel.title))).scalars().all()
    counts = await _pending_counts(db, [c.id for c in chans])
    return [_out(c, counts.get(c.id, 0)) for c in chans]


@router.get("/channels/{channel_id}", response_model=ChannelDetail)
async def get_channel(channel_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return await _detail(db, await get_owned(db, Channel, channel_id, user))


@router.patch("/channels/{channel_id}", response_model=ChannelDetail)
async def patch_channel(
    channel_id: int,
    body: ChannelPatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ch = await get_owned(db, Channel, channel_id, user)
    manager = request.app.state.manager
    if body.manager_account_id is not None and body.manager_account_id != ch.manager_account_id:
        acc = await get_owned(db, TgAccount, body.manager_account_id, user)
        if acc.owner_id != ch.owner_id:
            raise HTTPException(404, "não encontrado")
        ref = ref_of(ch)
        await tg_call(manager, acc.id, lambda c: c.get_chat(ref))
        ch.manager_account_id = acc.id
        await refresh_channel(db, ch, manager)
    if body.join_mode is not None and body.join_mode != ch.join_mode:
        ch.join_mode = body.join_mode
        if body.join_mode == JoinMode.AUTO:
            from app.joins.service import enqueue_pending_auto

            await enqueue_pending_auto(db, ch, request.app.state.throttle)
    await db.commit()
    return await _detail(db, ch)


@router.post("/channels/{channel_id}/refresh", response_model=ChannelDetail)
async def refresh(
    channel_id: int, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    ch = await get_owned(db, Channel, channel_id, user)
    await refresh_channel(db, ch, request.app.state.manager)
    await db.commit()
    return await _detail(db, ch)


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    ch = await get_owned(db, Channel, channel_id, user)
    await db.execute(
        update(ScheduledPost)
        .where(ScheduledPost.channel_id == ch.id, ScheduledPost.status == PostStatus.SCHEDULED)
        .values(status=PostStatus.CANCELED, error="grupo removido do painel")
    )
    await db.execute(update(ScheduledPost).where(ScheduledPost.channel_id == ch.id).values(channel_id=None))
    await db.execute(delete(JoinRequest).where(JoinRequest.channel_id == ch.id))
    await db.execute(delete(ChannelAdmin).where(ChannelAdmin.channel_id == ch.id))
    await db.delete(ch)
    await db.commit()
    return {"ok": True}
