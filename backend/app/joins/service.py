"""Join requests: polling from Telegram, auto-approval queueing and the rate-limit throttle."""

import logging
import random
from collections import deque
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.service import ref_of
from app.jobs.runner import enqueue
from app.models import AccountStatus, Channel, ChannelStatus, JoinMode, JoinRequest, JoinStatus, TgAccount
from app.tg.gateway import TgClient
from app.tg.manager import AccountUnavailable, ClientManager
from app.tg.types import TgError, TgFatalAuth
from app.timeutil import utcnow

log = logging.getLogger("voryx.joins")

POLL_LIMIT = 100


class ApprovalThrottle:
    """Hands out approval time slots per account: 2–4 s apart, at most 300 per rolling hour.

    Exists to respect Telegram rate limits (not to disguise activity)."""

    def __init__(
        self, rng: random.Random | None = None, min_gap: float = 2.0, max_gap: float = 4.0, max_per_hour: int = 300
    ) -> None:
        self.rng = rng or random.Random()
        self.min_gap, self.max_gap, self.max_per_hour = min_gap, max_gap, max_per_hour
        self._slots: dict[int, deque[datetime]] = {}

    def next_slot(self, account_id: int, now: datetime) -> datetime:
        q = self._slots.setdefault(account_id, deque(maxlen=self.max_per_hour))
        slot = now
        if q:
            slot = max(slot, q[-1] + timedelta(seconds=self.rng.uniform(self.min_gap, self.max_gap)))
        if len(q) == self.max_per_hour:
            slot = max(slot, q[0] + timedelta(hours=1))
        q.append(slot)
        return slot


async def queue_decision(
    db: AsyncSession,
    channel: Channel,
    jr: JoinRequest,
    approve: bool,
    decided_by: str,
    throttle: ApprovalThrottle,
    now: datetime,
) -> datetime:
    run_at = throttle.next_slot(channel.manager_account_id, now)
    await enqueue(
        db,
        "approve_join" if approve else "reject_join",
        {"join_request_id": jr.id, "decided_by": decided_by},
        channel.manager_account_id,
        run_at=run_at,
    )
    jr.queued_at = now
    return run_at


async def enqueue_pending_auto(
    db: AsyncSession, channel: Channel, throttle: ApprovalThrottle, now: datetime | None = None
) -> int:
    now = now or utcnow()
    rows = (
        (
            await db.execute(
                select(JoinRequest)
                .where(
                    JoinRequest.channel_id == channel.id,
                    JoinRequest.status == JoinStatus.PENDING,
                    JoinRequest.queued_at.is_(None),
                )
                .order_by(JoinRequest.requested_at, JoinRequest.id)
            )
        )
        .scalars()
        .all()
    )
    for jr in rows:
        await queue_decision(db, channel, jr, True, "auto", throttle, now)
    return len(rows)


async def poll_channel(
    db: AsyncSession, channel: Channel, client: TgClient, throttle: ApprovalThrottle, now: datetime
) -> None:
    pending = await client.get_pending_requests(ref_of(channel), limit=POLL_LIMIT)
    existing = {
        jr.tg_user_id: jr
        for jr in (
            await db.execute(
                select(JoinRequest).where(
                    JoinRequest.channel_id == channel.id, JoinRequest.status == JoinStatus.PENDING
                )
            )
        ).scalars()
    }
    seen = set()
    for p in pending:
        seen.add(p.user_id)
        if p.user_id not in existing:
            db.add(
                JoinRequest(
                    channel_id=channel.id,
                    tg_user_id=p.user_id,
                    name=p.name[:200],
                    username=p.username,
                    requested_at=p.requested_at,
                )
            )
    if len(pending) < POLL_LIMIT:  # full picture: anything missing was handled outside the panel
        for uid, jr in existing.items():
            if uid not in seen and jr.queued_at is None:
                jr.status, jr.decided_by, jr.decided_at = JoinStatus.REJECTED, "external", now
    await db.flush()
    if channel.join_mode == JoinMode.AUTO:
        await enqueue_pending_auto(db, channel, throttle, now)


async def poll_all(sessionmaker, manager: ClientManager, throttle: ApprovalThrottle) -> None:
    now = utcnow()
    async with sessionmaker() as db:
        channels = (await db.execute(select(Channel).where(Channel.status == ChannelStatus.OK))).scalars().all()
        for ch in channels:
            acc = await db.get(TgAccount, ch.manager_account_id) if ch.manager_account_id else None
            if acc is None or acc.status != AccountStatus.ONLINE:
                continue
            try:
                client = manager.get(acc.id)
                async with manager.lock(acc.id):
                    await poll_channel(db, ch, client, throttle, now)
                await db.commit()
            except AccountUnavailable:
                await db.rollback()
            except TgFatalAuth as e:
                await db.rollback()
                await manager.mark_dead(acc.id, e.reason)
            except TgError as e:
                await db.rollback()
                log.warning("poll of channel %s failed: %s", ch.id, e)
