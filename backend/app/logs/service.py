from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActionLog


async def log_action(
    db: AsyncSession,
    owner_id: int,
    action: str,
    *,
    account_id: int | None = None,
    channel_id: int | None = None,
    target: str | None = None,
    result: str = "ok",
    detail: str | None = None,
) -> None:
    db.add(
        ActionLog(
            owner_id=owner_id,
            action=action,
            account_id=account_id,
            channel_id=channel_id,
            target=target,
            result=result,
            detail=detail,
        )
    )
