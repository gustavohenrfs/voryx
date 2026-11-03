from sqlalchemy import select

from app.channels.service import ref_of
from app.jobs.runner import JobContext
from app.logs.service import log_action
from app.models import Channel, JoinRequest, JoinStatus
from app.tg.types import TgPermanent

GONE_MARKERS = ("HIDE_REQUESTER_MISSING", "USER_ALREADY_PARTICIPANT", "INVITE_REQUEST_SENT")


async def _decide(ctx: JobContext, approve: bool) -> None:
    jr = await ctx.db.get(JoinRequest, ctx.job.payload["join_request_id"])
    if jr is None or jr.status != JoinStatus.PENDING:
        return
    channel = await ctx.db.get(Channel, jr.channel_id)
    if channel is None:
        return
    decided_by = ctx.job.payload.get("decided_by", "user")
    try:
        await ctx.client.decide_request(ref_of(channel), jr.tg_user_id, approve)
    except TgPermanent as e:
        if not any(m in str(e) for m in GONE_MARKERS):
            raise
        jr.status, jr.decided_by, jr.decided_at = JoinStatus.REJECTED, "external", ctx.now
        return
    jr.status = JoinStatus.APPROVED if approve else JoinStatus.REJECTED
    jr.decided_by, jr.decided_at = decided_by, ctx.now
    await log_action(
        ctx.db,
        channel.owner_id,
        "approve" if approve else "reject",
        account_id=ctx.job.account_id,
        channel_id=channel.id,
        target=jr.name,
        detail=decided_by,
    )


async def approve_join(ctx: JobContext) -> None:
    await _decide(ctx, True)


async def reject_join(ctx: JobContext) -> None:
    await _decide(ctx, False)


async def approve_all(ctx: JobContext) -> None:
    channel = await ctx.db.get(Channel, ctx.job.payload["channel_id"])
    if channel is None:
        return
    await ctx.client.approve_all(ref_of(channel))
    rows = (
        (
            await ctx.db.execute(
                select(JoinRequest).where(
                    JoinRequest.channel_id == channel.id, JoinRequest.status == JoinStatus.PENDING
                )
            )
        )
        .scalars()
        .all()
    )
    for jr in rows:
        jr.status, jr.decided_by, jr.decided_at = JoinStatus.APPROVED, "user", ctx.now
    await log_action(
        ctx.db,
        channel.owner_id,
        "approve_all",
        account_id=ctx.job.account_id,
        channel_id=channel.id,
        target=f"{len(rows)} solicitações",
    )
