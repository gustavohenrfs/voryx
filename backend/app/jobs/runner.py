"""Postgres-backed job queue. One runner loop in the single app process."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccountStatus, Job, JobStatus, TgAccount
from app.tg.gateway import TgClient
from app.tg.manager import AccountUnavailable, ClientManager
from app.tg.types import TgFatalAuth, TgFloodWait, TgTransient
from app.timeutil import utcnow

log = logging.getLogger("voryx.jobs")

RETRY_DELAYS_S = (30, 120, 600)
CLAIM_BATCH = 20
ACCOUNT_DOWN = "conta caída"


@dataclass
class JobContext:
    db: AsyncSession
    job: Job
    client: TgClient | None
    manager: ClientManager
    now: datetime


Handler = Callable[[JobContext], Awaitable[None]]


async def enqueue(
    db: AsyncSession, type: str, payload: dict[str, Any], account_id: int | None, run_at: datetime | None = None
) -> Job:
    job = Job(type=type, payload=payload, account_id=account_id, run_at=run_at or utcnow())
    db.add(job)
    await db.flush()
    return job


class _Retry(Exception):
    pass


class JobRunner:
    def __init__(
        self,
        sessionmaker,
        manager: ClientManager,
        handlers: dict[str, Handler],
        fail_hooks: dict[str, Handler] | None = None,
        retry_hooks: dict[str, Handler] | None = None,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.manager = manager
        self.handlers = handlers
        self.fail_hooks = fail_hooks or {}
        self.retry_hooks = retry_hooks or {}

    async def _claim(self, now: datetime) -> list[int]:
        async with self.sessionmaker() as db:
            stmt = (
                select(Job)
                .where(Job.status == JobStatus.PENDING, Job.run_at <= now)
                .order_by(Job.run_at, Job.id)
                .limit(CLAIM_BATCH)
                .with_for_update(skip_locked=True)
            )
            jobs = (await db.execute(stmt)).scalars().all()
            for j in jobs:
                j.status = JobStatus.RUNNING
            await db.commit()
            return [j.id for j in jobs]

    async def run_once(self, now: datetime | None = None) -> int:
        now = now or utcnow()
        ids = await self._claim(now)
        for job_id in ids:
            try:
                await self._process(job_id, now)
            except Exception:  # noqa: BLE001 - never let one job kill the loop
                log.exception("job %s crashed the runner", job_id)
        return len(ids)

    async def _process(self, job_id: int, now: datetime) -> None:
        async with self.sessionmaker() as db:
            job = await db.get(Job, job_id)
            handler = self.handlers.get(job.type)
            if handler is None:
                await self._fail(db, job, now, f"tipo de job desconhecido: {job.type}", hook=False)
                return
            client = None
            account_id = job.account_id
            if account_id is not None:
                acc = await db.get(TgAccount, job.account_id)
                if acc is None or acc.status == AccountStatus.DEAD:
                    await self._fail(db, job, now, ACCOUNT_DOWN)
                    return
                try:
                    client = self.manager.get(job.account_id)
                except AccountUnavailable:
                    await self._retry_transient(db, job, now, "conta offline")
                    return
            ctx = JobContext(db=db, job=job, client=client, manager=self.manager, now=now)
            try:
                if account_id is not None:
                    async with self.manager.lock(account_id):
                        await handler(ctx)
                else:
                    await handler(ctx)
            except TgFloodWait as e:
                await db.rollback()
                job = await db.get(Job, job_id)
                job.status = JobStatus.PENDING
                job.run_at = now + timedelta(seconds=e.seconds + 5)
                job.last_error = f"flood wait {e.seconds}s"
                await self._hook(self.retry_hooks, db, job, client, now)
                await db.commit()
                return
            except TgTransient as e:
                await db.rollback()
                job = await db.get(Job, job_id)
                await self._retry_transient(db, job, now, str(e) or "erro de rede", client)
                return
            except TgFatalAuth as e:
                await db.rollback()
                await self.manager.mark_dead(account_id, e.reason)
                job = await db.get(Job, job_id)
                await self._fail(db, job, now, f"{ACCOUNT_DOWN} ({e.reason})", client=client)
                return
            except Exception as e:  # noqa: BLE001
                await db.rollback()
                job = await db.get(Job, job_id)
                await self._fail(db, job, now, str(e) or type(e).__name__, client=client)
                return
            job.status = JobStatus.DONE
            job.last_error = None
            await db.commit()

    async def _hook(self, hooks, db, job, client, now) -> None:
        hook = hooks.get(job.type)
        if hook is not None:
            await hook(JobContext(db=db, job=job, client=client, manager=self.manager, now=now))

    async def _retry_transient(self, db, job: Job, now: datetime, error: str, client=None) -> None:
        job.attempts += 1
        job.last_error = error
        if job.attempts > len(RETRY_DELAYS_S):
            await self._fail(db, job, now, error, client=client)
            return
        job.status = JobStatus.PENDING
        job.run_at = now + timedelta(seconds=RETRY_DELAYS_S[job.attempts - 1])
        await self._hook(self.retry_hooks, db, job, client, now)
        await db.commit()

    async def _fail(self, db, job: Job, now: datetime, error: str, client=None, hook: bool = True) -> None:
        job.status = JobStatus.FAILED
        job.last_error = error
        if hook:
            await self._hook(self.fail_hooks, db, job, client, now)
        await db.commit()

    async def loop(self, interval: float = 3.0) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:  # noqa: BLE001
                log.exception("job runner iteration failed")
            await asyncio.sleep(interval)
