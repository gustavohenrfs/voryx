from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import current_user, get_db, owned
from app.models import ActionLog, User

router = APIRouter(prefix="/logs", tags=["logs"])


class LogOut(BaseModel):
    id: int
    action: str
    account_id: int | None
    channel_id: int | None
    target: str | None
    result: str
    detail: str | None
    created_at: datetime


@router.get("", response_model=list[LogOut])
async def list_logs(
    channel_id: int | None = None,
    account_id: int | None = None,
    before_id: int | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = owned(select(ActionLog), ActionLog, user)
    if channel_id is not None:
        stmt = stmt.where(ActionLog.channel_id == channel_id)
    if account_id is not None:
        stmt = stmt.where(ActionLog.account_id == account_id)
    if before_id is not None:
        stmt = stmt.where(ActionLog.id < before_id)
    rows = (await db.execute(stmt.order_by(ActionLog.id.desc()).limit(min(max(limit, 1), 500)))).scalars()
    return [
        LogOut(
            id=r.id,
            action=r.action,
            account_id=r.account_id,
            channel_id=r.channel_id,
            target=r.target,
            result=r.result,
            detail=r.detail,
            created_at=r.created_at,
        )
        for r in rows
    ]
