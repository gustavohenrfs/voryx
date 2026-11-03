import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass, field

from app.tg.gateway import LoginHandle

LOGIN_TTL_S = 10 * 60


@dataclass
class PendingLogin:
    owner_id: int
    handle: LoginHandle
    phone: str
    api_id: int
    api_hash: str
    account_id: int | None
    label: str | None
    created: float = field(default=0.0)


class PendingLogins:
    """Two-step Telegram logins kept in memory (the same client must finish the login)."""

    def __init__(self, clock=time.monotonic) -> None:
        self.clock = clock
        self._items: dict[str, PendingLogin] = {}

    def create(
        self,
        owner_id: int,
        handle: LoginHandle,
        phone: str,
        api_id: int,
        api_hash: str,
        account_id: int | None,
        label: str | None = None,
    ) -> str:
        self._expire()
        login_id = uuid.uuid4().hex
        self._items[login_id] = PendingLogin(
            owner_id, handle, phone, api_id, api_hash, account_id, label, created=self.clock()
        )
        return login_id

    def get(self, login_id: str, owner_id: int) -> PendingLogin | None:
        self._expire()
        item = self._items.get(login_id)
        if item is None or item.owner_id != owner_id:
            return None
        return item

    def pop(self, login_id: str) -> PendingLogin | None:
        return self._items.pop(login_id, None)

    def _expire(self) -> None:
        cutoff = self.clock() - LOGIN_TTL_S
        for k in [k for k, v in self._items.items() if v.created < cutoff]:
            item = self._items.pop(k)
            # release the half-open Telegram connection of an abandoned login
            with contextlib.suppress(RuntimeError):
                asyncio.get_running_loop().create_task(item.handle.cancel())
