from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.service import ref_of
from app.deps import current_user, get_db
from app.joins.routes import _channel_with_manager
from app.logs.service import log_action
from app.models import User
from app.tg.http import tg_call

router = APIRouter(prefix="/channels/{channel_id}/members", tags=["members"])

MAX_LIMIT = 200


class MemberOut(BaseModel):
    user_id: int
    name: str
    username: str | None


class MemberAction(BaseModel):
    name: str | None = None


@router.get("", response_model=list[MemberOut])
async def list_members(
    channel_id: int,
    request: Request,
    q: str = "",
    offset: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ch = await _channel_with_manager(db, channel_id, user)
    ref = ref_of(ch)
    limit = min(max(limit, 1), MAX_LIMIT)
    offset = max(offset, 0)
    members = await tg_call(
        request.app.state.manager, ch.manager_account_id, lambda c: c.search_members(ref, q.strip(), offset, limit)
    )
    return [MemberOut(user_id=m.user_id, name=m.name, username=m.username) for m in members]


async def _act(
    action: str, channel_id: int, tg_user_id: int, name: str | None, request: Request, db: AsyncSession, user: User
):
    ch = await _channel_with_manager(db, channel_id, user)
    ref = ref_of(ch)
    target = f"{name} ({tg_user_id})" if name else str(tg_user_id)

    async def run(c):
        if action == "kick":
            await c.kick(ref, tg_user_id)
        else:
            await c.ban(ref, tg_user_id)

    try:
        await tg_call(request.app.state.manager, ch.manager_account_id, run)
    except HTTPException as e:
        await log_action(
            db,
            ch.owner_id,
            action,
            account_id=ch.manager_account_id,
            channel_id=ch.id,
            target=target,
            result="error",
            detail=str(e.detail),
        )
        await db.commit()
        raise
    await log_action(db, ch.owner_id, action, account_id=ch.manager_account_id, channel_id=ch.id, target=target)
    await db.commit()
    return {"ok": True}


@router.post("/{tg_user_id}/kick")
async def kick(
    channel_id: int,
    tg_user_id: int,
    request: Request,
    body: MemberAction | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return await _act("kick", channel_id, tg_user_id, body.name if body else None, request, db, user)


@router.post("/{tg_user_id}/ban")
async def ban(
    channel_id: int,
    tg_user_id: int,
    request: Request,
    body: MemberAction | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return await _act("ban", channel_id, tg_user_id, body.name if body else None, request, db, user)
