from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class ChatRef:
    """chat_id is Telethon's marked peer id (e.g. -100123... for channels)."""

    chat_id: int
    access_hash: int | None


@dataclass
class TgUser:
    id: int
    name: str
    username: str | None = None
    phone: str | None = None


@dataclass
class DialogInfo:
    chat_id: int
    access_hash: int | None
    title: str
    username: str | None
    kind: Literal["channel", "supergroup", "group"]
    member_count: int | None


@dataclass
class AdminInfo:
    user_id: int
    name: str
    rights: dict[str, bool] = field(default_factory=dict)


@dataclass
class JoinRequestInfo:
    user_id: int
    name: str
    username: str | None
    requested_at: datetime


@dataclass
class MemberInfo:
    user_id: int
    name: str
    username: str | None


class TgError(Exception):
    pass


class TgFatalAuth(TgError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class TgFloodWait(TgError):
    def __init__(self, seconds: int):
        super().__init__(f"flood wait {seconds}s")
        self.seconds = seconds


class TgNeedPassword(TgError):
    pass


class TgInvalidCode(TgError):
    pass


class TgCodeExpired(TgError):
    pass


class TgInvalidPassword(TgError):
    pass


class TgPhoneInvalid(TgError):
    pass


class TgTransient(TgError):
    pass


class TgPermanent(TgError):
    pass
