"""Keeps one connected TgClient per live account in memory and runs health checks.

Dead accounts (fatal auth errors) are disconnected and never reconnected automatically;
only a new login / imported session brings them back (see accounts routes)."""

import asyncio
import logging

from sqlalchemy import select, update

from app.crypto import decrypt
from app.models import AccountStatus, Channel, ChannelStatus, TgAccount
from app.tg.gateway import TelegramGateway, TgClient
from app.tg.types import TgError, TgFatalAuth
from app.timeutil import utcnow

log = logging.getLogger("voryx.manager")

START_CONCURRENCY = 5


class AccountUnavailable(Exception):
    def __init__(self, status: str):
        super().__init__(f"conta indisponível ({status})")
        self.status = status


class ClientManager:
    def __init__(self, gateway: TelegramGateway, sessionmaker) -> None:
        self.gateway = gateway
        self.sessionmaker = sessionmaker
        self.clients: dict[int, TgClient] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def lock(self, account_id: int) -> asyncio.Lock:
        return self._locks.setdefault(account_id, asyncio.Lock())

    def get(self, account_id: int) -> TgClient:
        client = self.clients.get(account_id)
        if client is None:
            raise AccountUnavailable("offline")
        return client

    async def _set_status(self, account_id: int, status: str, reason: str | None = None) -> None:
        async with self.sessionmaker() as db:
            acc = await db.get(TgAccount, account_id)
            if acc is None:
                return
            acc.status = status
            if status == AccountStatus.DEAD:
                acc.dead_reason = reason
                await db.execute(
                    update(Channel)
                    .where(Channel.manager_account_id == account_id)
                    .values(status=ChannelStatus.ACCOUNT_DOWN)
                )
            elif status == AccountStatus.ONLINE:
                acc.dead_reason = None
                acc.last_seen_at = utcnow()
            await db.commit()

    async def _connect(self, account_id: int, session: str | None = None) -> str:
        async with self.sessionmaker() as db:
            acc = await db.get(TgAccount, account_id)
            if acc is None:
                return AccountStatus.DEAD
            session = session or (decrypt(acc.session_enc) if acc.session_enc else None)
            api_id, api_hash = acc.api_id, decrypt(acc.api_hash_enc)
        if not session:
            await self._set_status(account_id, AccountStatus.DEAD, "sem session")
            return AccountStatus.DEAD
        try:
            client = await self.gateway.connect(session, api_id, api_hash)
        except TgFatalAuth as e:
            await self._set_status(account_id, AccountStatus.DEAD, e.reason)
            return AccountStatus.DEAD
        except TgError as e:
            log.warning("account %s connect failed: %s", account_id, e)
            await self._set_status(account_id, AccountStatus.OFFLINE)
            return AccountStatus.OFFLINE
        self.clients[account_id] = client
        await self._set_status(account_id, AccountStatus.ONLINE)
        return AccountStatus.ONLINE

    async def start_all(self) -> None:
        async with self.sessionmaker() as db:
            ids = (await db.execute(select(TgAccount.id).where(TgAccount.status != AccountStatus.DEAD))).scalars().all()
        sem = asyncio.Semaphore(START_CONCURRENCY)

        async def one(account_id: int) -> None:
            async with sem:
                await self._connect(account_id)

        await asyncio.gather(*(one(i) for i in ids))

    async def add(self, account_id: int, session: str) -> str:
        await self.remove(account_id)
        return await self._connect(account_id, session)

    async def remove(self, account_id: int) -> None:
        client = self.clients.pop(account_id, None)
        if client is not None:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                log.exception("disconnect failed for account %s", account_id)

    async def mark_dead(self, account_id: int, reason: str) -> None:
        log.warning("account %s is dead: %s", account_id, reason)
        await self.remove(account_id)
        await self._set_status(account_id, AccountStatus.DEAD, reason)

    async def check(self, account_id: int) -> str:
        async with self.sessionmaker() as db:
            acc = await db.get(TgAccount, account_id)
            if acc is None or acc.status == AccountStatus.DEAD:
                return AccountStatus.DEAD
        client = self.clients.get(account_id)
        if client is None:
            return await self._connect(account_id)
        try:
            await client.get_me()
        except TgFatalAuth as e:
            await self.mark_dead(account_id, e.reason)
            return AccountStatus.DEAD
        except TgError as e:
            log.warning("account %s health check failed: %s", account_id, e)
            await self._set_status(account_id, AccountStatus.OFFLINE)
            return AccountStatus.OFFLINE
        await self._set_status(account_id, AccountStatus.ONLINE)
        return AccountStatus.ONLINE

    async def check_all(self) -> None:
        async with self.sessionmaker() as db:
            ids = (await db.execute(select(TgAccount.id).where(TgAccount.status != AccountStatus.DEAD))).scalars().all()
        for account_id in ids:
            await self.check(account_id)

    async def stop(self) -> None:
        for account_id in list(self.clients):
            await self.remove(account_id)
