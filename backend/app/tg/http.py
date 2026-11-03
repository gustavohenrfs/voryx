"""Run an interactive (panel-triggered) Telegram call and map failures to HTTP errors."""

import asyncio
from collections.abc import Awaitable, Callable

from fastapi import HTTPException

from app.tg.gateway import TgClient
from app.tg.manager import AccountUnavailable, ClientManager
from app.tg.types import TgError, TgFatalAuth, TgFloodWait, TgPermanent, TgTransient

LOCK_WAIT_S = 15.0


async def tg_call[T](manager: ClientManager, account_id: int, fn: Callable[[TgClient], Awaitable[T]]) -> T:
    try:
        client = manager.get(account_id)
    except AccountUnavailable as e:
        raise HTTPException(409, "conta offline — verifique a conta e tente de novo") from e
    lock = manager.lock(account_id)
    try:
        await asyncio.wait_for(lock.acquire(), LOCK_WAIT_S)
    except TimeoutError as e:
        raise HTTPException(409, "a conta está ocupada (enviando um post), tente de novo em instantes") from e
    try:
        return await fn(client)
    except TgFloodWait as e:
        raise HTTPException(429, f"aguarde {e.seconds}s") from e
    except TgFatalAuth as e:
        await manager.mark_dead(account_id, e.reason)
        raise HTTPException(409, "a conta caiu (sessão inválida ou banida)") from e
    except TgTransient as e:
        raise HTTPException(503, "Telegram indisponível, tente de novo") from e
    except TgPermanent as e:
        raise HTTPException(422, f"Telegram recusou: {e}") from e
    except TgError as e:
        raise HTTPException(400, f"erro do Telegram: {e}") from e
    finally:
        lock.release()
