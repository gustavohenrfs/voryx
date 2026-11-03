"""Scheduled post sending (job handler + hooks) and crash recovery."""

import os
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.service import ref_of
from app.jobs.runner import JobContext, Reschedule
from app.logs.service import log_action
from app.models import Channel, Job, JobStatus, PostMedia, PostStatus, ScheduledPost
from app.tg.types import TgPermanent, TgTransient
from app.timeutil import utcnow

INTERRUPTED = "interrompido durante o envio — verificar no grupo"
NETWORK_DURING_SEND = "falha de rede durante o envio — verificar no grupo antes de reagendar"


async def media_paths(db: AsyncSession, post_id: int) -> list[str]:
    rows = (
        await db.execute(select(PostMedia).where(PostMedia.post_id == post_id).order_by(PostMedia.position))
    ).scalars()
    return [m.path for m in rows]


async def send_post(ctx: JobContext) -> None:
    post = await ctx.db.get(ScheduledPost, ctx.job.payload["post_id"])
    if post is None or post.status != PostStatus.SCHEDULED:
        return  # canceled / already handled
    channel = await ctx.db.get(Channel, post.channel_id) if post.channel_id else None
    if channel is None:
        raise TgPermanent("grupo removido do painel")
    if post.run_at > ctx.now + timedelta(seconds=1):
        raise Reschedule(post.run_at)  # edited to a later time after the job was claimed
    paths = await media_paths(ctx.db, post.id)
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise TgPermanent("mídia não encontrada no servidor")
    # Atomically claim the post (a concurrent cancel wins) and commit BEFORE calling Telegram:
    # if the process dies mid-send, recovery sees 'sending' and never re-sends (no duplicates).
    claimed = await ctx.db.execute(
        update(ScheduledPost)
        .where(ScheduledPost.id == post.id, ScheduledPost.status == PostStatus.SCHEDULED)
        .values(status=PostStatus.SENDING, error=None)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        await ctx.db.rollback()
        return
    await ctx.db.commit()
    await ctx.db.refresh(post)
    try:
        ids = await ctx.client.send_post(ref_of(channel), post.text, paths)
    except TgTransient as e:
        # the message may or may not have gone out — do not retry automatically
        raise TgPermanent(NETWORK_DURING_SEND) from e
    post.status = PostStatus.SENT
    post.sent_message_ids = ids
    post.finished_at = ctx.now
    await log_action(
        ctx.db,
        post.owner_id,
        "post",
        account_id=post.account_id,
        channel_id=channel.id,
        target=f"{len(paths)} mídia(s)" if paths else "texto",
    )


async def on_send_fail(ctx: JobContext) -> None:
    post = await ctx.db.get(ScheduledPost, ctx.job.payload["post_id"])
    if post is None or post.status in (PostStatus.SENT, PostStatus.CANCELED):
        return
    post.status = PostStatus.FAILED
    post.error = ctx.job.last_error
    post.finished_at = ctx.now


async def on_send_retry(ctx: JobContext) -> None:
    post = await ctx.db.get(ScheduledPost, ctx.job.payload["post_id"])
    if post is None or post.status not in (PostStatus.SCHEDULED, PostStatus.SENDING):
        return
    # FloodWait or offline account: Telegram did not accept the request, safe to retry
    post.status = PostStatus.SCHEDULED
    post.error = f"reagendado: {ctx.job.last_error}"


async def recover_interrupted_posts(db: AsyncSession) -> None:
    """On startup: posts stuck in 'sending' fail (never re-sent); other running jobs go back to pending."""
    now = utcnow()
    for post in (await db.execute(select(ScheduledPost).where(ScheduledPost.status == PostStatus.SENDING))).scalars():
        post.status = PostStatus.FAILED
        post.error = INTERRUPTED
        post.finished_at = now
    for job in (await db.execute(select(Job).where(Job.status == JobStatus.RUNNING))).scalars():
        if job.type == "send_post":
            post = await db.get(ScheduledPost, job.payload.get("post_id"))
            if post is not None and post.status == PostStatus.SCHEDULED:
                job.status = JobStatus.PENDING  # claimed but never started: safe to run
            else:
                job.status = JobStatus.FAILED
                job.last_error = INTERRUPTED
        else:
            job.status = JobStatus.PENDING
