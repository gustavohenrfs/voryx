import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccountStatus, Channel, ChannelAdmin, ChannelStatus, TgAccount
from app.tg.manager import AccountUnavailable, ClientManager
from app.tg.types import ChatRef, DialogInfo, TgError, TgFatalAuth, TgPermanent
from app.timeutil import utcnow

log = logging.getLogger("voryx.channels")


def ref_of(channel: Channel) -> ChatRef:
    return ChatRef(channel.tg_chat_id, channel.access_hash)


def apply_info(channel: Channel, info: DialogInfo) -> None:
    channel.title = info.title
    channel.username = info.username
    channel.kind = info.kind
    channel.member_count = info.member_count
    if info.access_hash is not None:
        channel.access_hash = info.access_hash


async def refresh_channel(db: AsyncSession, channel: Channel, manager: ClientManager) -> None:
    """Refresh title/members/admins. Updates channel.status; never raises Telegram errors."""
    acc = await db.get(TgAccount, channel.manager_account_id) if channel.manager_account_id else None
    if acc is None or acc.status == AccountStatus.DEAD:
        channel.status = ChannelStatus.ACCOUNT_DOWN
        return
    try:
        client = manager.get(acc.id)
    except AccountUnavailable:
        return  # offline: keep last known data, try again next cycle
    ref = ref_of(channel)
    try:
        async with manager.lock(acc.id):
            info = await client.get_chat(ref)
            admins = await client.get_admins(ref)
    except TgFatalAuth as e:
        await manager.mark_dead(acc.id, e.reason)
        channel.status = ChannelStatus.ACCOUNT_DOWN
        return
    except TgPermanent as e:
        log.info("channel %s lost access: %s", channel.id, e)
        channel.status = ChannelStatus.NO_ACCESS
        return
    except TgError as e:
        log.warning("channel %s refresh failed: %s", channel.id, e)
        return
    apply_info(channel, info)
    await db.execute(delete(ChannelAdmin).where(ChannelAdmin.channel_id == channel.id))
    now = utcnow()
    for a in admins:
        db.add(ChannelAdmin(channel_id=channel.id, tg_user_id=a.user_id, name=a.name, rights=a.rights, synced_at=now))
    channel.status = ChannelStatus.OK
    channel.last_synced_at = now


async def refresh_for_account(db: AsyncSession, account_id: int, manager: ClientManager) -> None:
    channels = (await db.execute(select(Channel).where(Channel.manager_account_id == account_id))).scalars().all()
    for ch in channels:
        await refresh_channel(db, ch, manager)
    await db.commit()


async def refresh_all(sessionmaker, manager: ClientManager) -> None:
    async with sessionmaker() as db:
        channels = (await db.execute(select(Channel))).scalars().all()
        for ch in channels:
            await refresh_channel(db, ch, manager)
            await db.commit()
