from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import current_user, get_db, get_owned
from app.jobs.runner import enqueue
from app.joins.service import poll_channel, queue_decision
from app.models import AccountStatus, Channel, JoinRequest, JoinStatus, TgAccount, User
from app.tg.http import tg_call
from app.timeutil import utcnow

router = APIRouter(prefix="/channels/{channel_id}/requests", tags=["joins"])


class JoinRequestOut(BaseModel):
    id: int
    tg_user_id: int
    name: str
    username: str | None
    requested_at: datetime
    status: str
    decided_by: str | None
    decided_at: datetime | None
    queued: bool


def _out(jr: JoinRequest) -> JoinRequestOut:
    return JoinRequestOut(
        id=jr.id,
        tg_user_id=jr.tg_user_id,
        name=jr.name,
        username=jr.username,
        requested_at=jr.requested_at,
        status=jr.status,
        decided_by=jr.decided_by,
        decided_at=jr.decided_at,
        queued=jr.queued_at is not None,
    )


async def _channel_with_manager(db: AsyncSession, channel_id: int, user: User) -> Channel:
    ch = await get_owned(db, Channel, channel_id, user)
    acc = await db.get(TgAccount, ch.manager_account_id) if ch.manager_account_id else None
    if acc is None or acc.status == AccountStatus.DEAD:
        raise HTTPException(409, "a conta gestora do grupo caiu — troque a conta gestora")
    return ch


@router.get("", response_model=list[JoinRequestOut])
async def list_requests(
    channel_id: int,
    status: Literal["pending", "approved", "rejected"] = "pending",
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ch = await get_owned(db, Channel, channel_id, user)
    rows = (
        await db.execute(
            select(JoinRequest)
            .where(JoinRequest.channel_id == ch.id, JoinRequest.status == status)
            .order_by(JoinRequest.requested_at.desc())
            .limit(min(max(limit, 1), 500))
        )
    ).scalars()
    return [_out(jr) for jr in rows]


@router.post("/refresh", response_model=list[JoinRequestOut])
async def refresh_requests(
    channel_id: int, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    ch = await _channel_with_manager(db, channel_id, user)
    throttle, now = request.app.state.throttle, utcnow()
    await tg_call(request.app.state.manager, ch.manager_account_id, lambda c: poll_channel(db, ch, c, throttle, now))
    await db.commit()
    return await list_requests(channel_id, "pending", 200, db, user)


async def _decide(channel_id: int, request_id: int, approve: bool, request: Request, db: AsyncSession, user: User):
    ch = await _channel_with_manager(db, channel_id, user)
    jr = await db.get(JoinRequest, request_id)
    if jr is None or jr.channel_id != ch.id:
        raise HTTPException(404, "não encontrado")
    if jr.status != JoinStatus.PENDING or jr.queued_at is not None:
        raise HTTPException(409, "solicitação já decidida ou na fila")
    run_at = await queue_decision(db, ch, jr, approve, "user", request.app.state.throttle, utcnow())
    await db.commit()
    return {"queued": True, "run_at": run_at}


@router.post("/{request_id}/approve")
async def approve(
    channel_id: int,
    request_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return await _decide(channel_id, request_id, True, request, db, user)


@router.post("/{request_id}/reject")
async def reject(
    channel_id: int,
    request_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return await _decide(channel_id, request_id, False, request, db, user)


@router.post("/approve-all")
async def approve_all(channel_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    ch = await _channel_with_manager(db, channel_id, user)
    await enqueue(db, "approve_all", {"channel_id": ch.id}, ch.manager_account_id)
    await db.commit()
    return {"queued": True}
