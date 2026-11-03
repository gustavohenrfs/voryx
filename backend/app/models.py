from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.timeutil import utcnow

JSONType = JSON().with_variant(JSONB, "postgresql")


class Role:
    ADMIN = "admin"
    PARTNER = "partner"


class AccountStatus:
    ONLINE = "online"
    OFFLINE = "offline"
    DEAD = "dead"
    CONNECTING = "connecting"


class ChannelStatus:
    OK = "ok"
    NO_ACCESS = "sem_acesso"
    ACCOUNT_DOWN = "conta_caida"


class JoinMode:
    AUTO = "auto"
    MANUAL = "manual"


class JoinStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PostStatus:
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELED = "canceled"


class JobStatus:
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default=Role.PARTNER)
    name: Mapped[str] = mapped_column(String(120))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    session_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class TgAccount(Base):
    __tablename__ = "tg_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    label: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(32))
    api_id: Mapped[int] = mapped_column(Integer)
    api_hash_enc: Mapped[str] = mapped_column(Text)
    session_enc: Mapped[str | None] = mapped_column(Text)
    tg_user_id: Mapped[int | None] = mapped_column(BigInteger)
    display_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default=AccountStatus.CONNECTING)
    dead_reason: Mapped[str | None] = mapped_column(String(200))
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("owner_id", "tg_chat_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    tg_chat_id: Mapped[int] = mapped_column(BigInteger)
    access_hash: Mapped[int | None] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    member_count: Mapped[int | None] = mapped_column(Integer)
    manager_account_id: Mapped[int | None] = mapped_column(ForeignKey("tg_accounts.id"))
    join_mode: Mapped[str] = mapped_column(String(8), default=JoinMode.MANUAL)
    status: Mapped[str] = mapped_column(String(16), default=ChannelStatus.OK)
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ChannelAdmin(Base):
    __tablename__ = "channel_admins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(200))
    rights: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    synced_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class JoinRequest(Base):
    __tablename__ = "join_requests"
    __table_args__ = (Index("ix_join_requests_channel_user", "channel_id", "tg_user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    tg_user_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(200))
    username: Mapped[str | None] = mapped_column(String(64))
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(16), default=JoinStatus.PENDING)
    decided_by: Mapped[str | None] = mapped_column(String(16))
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("tg_accounts.id"))
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    text: Mapped[str] = mapped_column(Text, default="")
    run_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    status: Mapped[str] = mapped_column(String(16), default=PostStatus.SCHEDULED)
    error: Mapped[str | None] = mapped_column(Text)
    sent_message_ids: Mapped[list[int] | None] = mapped_column(JSONType)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PostMedia(Base):
    __tablename__ = "post_media"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    post_id: Mapped[int | None] = mapped_column(ForeignKey("scheduled_posts.id", ondelete="SET NULL"))
    path: Mapped[str] = mapped_column(String(500))
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(BigInteger)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_run_at", "status", "run_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("tg_accounts.id", ondelete="CASCADE"))
    run_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ActionLog(Base):
    __tablename__ = "action_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("tg_accounts.id", ondelete="SET NULL"))
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(32))
    target: Mapped[str | None] = mapped_column(String(200))
    result: Mapped[str] = mapped_column(String(16), default="ok")
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
