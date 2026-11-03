"""In-memory TelegramGateway for tests and local development."""

from app.tg.types import (
    AdminInfo,
    ChatRef,
    DialogInfo,
    JoinRequestInfo,
    MemberInfo,
    TgFatalAuth,
    TgInvalidCode,
    TgInvalidPassword,
    TgNeedPassword,
    TgPermanent,
    TgUser,
)

VALID_CODE = "12345"
VALID_PASSWORD = "pw"
MUTATING = {"decide_request", "approve_all", "kick", "ban", "send_post"}


class FakeGateway:
    def __init__(self) -> None:
        self.dialogs: list[DialogInfo] = []
        self.admins: dict[int, list[AdminInfo]] = {}
        self.pending: dict[int, list[JoinRequestInfo]] = {}
        self.members: dict[int, list[MemberInfo]] = {}
        self.no_post: set[int] = set()
        self.require_password: set[str] = set()
        self.dead_sessions: set[str] = set()
        self.fail_next: dict[str, Exception] = {}
        self.calls: list[tuple] = []
        self._next_msg_id = 1000

    # -- helpers for tests
    def _maybe_fail(self, method: str) -> None:
        exc = self.fail_next.pop(method, None)
        if exc is not None:
            raise exc

    def mutating_calls(self) -> list[tuple]:
        return [c for c in self.calls if c[0] in MUTATING]

    # -- gateway API
    async def start_login(self, phone: str, api_id: int, api_hash: str) -> "FakeLogin":
        self.calls.append(("start_login", phone))
        self._maybe_fail("start_login")
        return FakeLogin(self, phone)

    async def connect(self, session: str, api_id: int, api_hash: str) -> "FakeClient":
        self.calls.append(("connect", session))
        self._maybe_fail("connect")
        if session in self.dead_sessions:
            raise TgFatalAuth("AuthKeyUnregisteredError")
        return FakeClient(self, session)


class FakeLogin:
    def __init__(self, gw: FakeGateway, phone: str) -> None:
        self.gw, self.phone, self.code_ok = gw, phone, False

    async def submit_code(self, code: str) -> str:
        self.gw._maybe_fail("submit_code")
        if code != VALID_CODE:
            raise TgInvalidCode()
        self.code_ok = True
        if self.phone in self.gw.require_password:
            raise TgNeedPassword()
        return f"fake-session-{self.phone}"

    async def submit_password(self, password: str) -> str:
        if not self.code_ok:
            raise TgInvalidCode()
        if password != VALID_PASSWORD:
            raise TgInvalidPassword()
        return f"fake-session-{self.phone}"

    async def cancel(self) -> None:
        pass


class FakeClient:
    def __init__(self, gw: FakeGateway, session: str) -> None:
        self.gw, self.session = gw, session

    def _call(self, method: str, *args) -> None:
        self.gw.calls.append((method, *args))
        self.gw._maybe_fail(method)

    async def get_me(self) -> TgUser:
        self._call("get_me", self.session)
        phone = self.session.removeprefix("fake-session-")
        return TgUser(id=abs(hash(self.session)) % 10**9, name=f"Modelo {phone}", username=None, phone=phone)

    async def list_admin_dialogs(self) -> list[DialogInfo]:
        self._call("list_admin_dialogs", self.session)
        return list(self.gw.dialogs)

    async def get_chat(self, ref: ChatRef) -> DialogInfo:
        self._call("get_chat", ref.chat_id)
        for d in self.gw.dialogs:
            if d.chat_id == ref.chat_id:
                return d
        raise TgPermanent("CHANNEL_PRIVATE")

    async def get_admins(self, ref: ChatRef) -> list[AdminInfo]:
        self._call("get_admins", ref.chat_id)
        return list(self.gw.admins.get(ref.chat_id, []))

    async def get_pending_requests(self, ref: ChatRef, limit: int = 100) -> list[JoinRequestInfo]:
        self._call("get_pending_requests", ref.chat_id)
        return list(self.gw.pending.get(ref.chat_id, []))[:limit]

    async def decide_request(self, ref: ChatRef, user_id: int, approve: bool) -> None:
        self._call("decide_request", ref.chat_id, user_id, approve)
        self.gw.pending[ref.chat_id] = [p for p in self.gw.pending.get(ref.chat_id, []) if p.user_id != user_id]

    async def approve_all(self, ref: ChatRef) -> None:
        self._call("approve_all", ref.chat_id)
        self.gw.pending[ref.chat_id] = []

    async def search_members(self, ref: ChatRef, query: str, offset: int, limit: int) -> list[MemberInfo]:
        self._call("search_members", ref.chat_id, query, offset, limit)
        q = query.lower()
        found = [m for m in self.gw.members.get(ref.chat_id, []) if q in m.name.lower()]
        return found[offset : offset + limit]

    async def kick(self, ref: ChatRef, user_id: int) -> None:
        self._call("kick", ref.chat_id, user_id)

    async def ban(self, ref: ChatRef, user_id: int) -> None:
        self._call("ban", ref.chat_id, user_id)

    async def can_post(self, ref: ChatRef) -> bool:
        self._call("can_post", ref.chat_id)
        return ref.chat_id not in self.gw.no_post

    async def send_post(self, ref: ChatRef, text: str, media_paths: list[str]) -> list[int]:
        self._call("send_post", ref.chat_id, text, tuple(media_paths))
        n = max(1, len(media_paths))
        ids = list(range(self.gw._next_msg_id, self.gw._next_msg_id + n))
        self.gw._next_msg_id += n
        return ids

    async def disconnect(self) -> None:
        self.gw.calls.append(("disconnect", self.session))
