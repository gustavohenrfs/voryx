"""Periodic loops that run inside the single app process."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI

from app.channels.service import refresh_all
from app.jobs.handlers import FAIL_HOOKS, HANDLERS, RETRY_HOOKS
from app.jobs.runner import JobRunner
from app.joins.service import poll_all
from app.posts.media import cleanup_media
from app.timeutil import utcnow

log = logging.getLogger("voryx.background")

INTERVALS = {
    "jobs": 3,
    "health": 600,
    "channels": 1800,
    "joins": 120,
    "media": 86400,
}


async def periodic(name: str, interval: float, fn: Callable[[], Awaitable[None]], initial_delay: float = 0) -> None:
    if initial_delay:
        await asyncio.sleep(initial_delay)
    while True:
        try:
            await fn()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("background loop %s failed", name)
        await asyncio.sleep(interval)


def start_background(app: FastAPI) -> list[asyncio.Task]:
    sm, manager, throttle = app.state.sessionmaker, app.state.manager, app.state.throttle
    runner = JobRunner(sm, manager, HANDLERS, FAIL_HOOKS, RETRY_HOOKS)

    async def jobs():
        await runner.run_once()

    async def health():
        await manager.check_all()

    async def channels():
        await refresh_all(sm, manager)

    async def joins():
        await poll_all(sm, manager, throttle)

    async def media():
        async with sm() as db:
            await cleanup_media(db, utcnow())
            await db.commit()

    i = INTERVALS
    return [
        asyncio.create_task(periodic("jobs", i["jobs"], jobs)),
        asyncio.create_task(periodic("health", i["health"], health, initial_delay=i["health"])),
        asyncio.create_task(periodic("channels", i["channels"], channels)),
        asyncio.create_task(periodic("joins", i["joins"], joins, initial_delay=min(30, i["joins"]))),
        asyncio.create_task(periodic("media", i["media"], media)),
    ]
