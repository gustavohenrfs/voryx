from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Channel, User


async def test_datetime_is_utc_aware(session):
    u = User(email="a@x.com", password_hash="h", role="admin", name="A")
    session.add(u)
    await session.commit()
    await session.refresh(u)
    assert u.created_at.tzinfo is not None
    assert u.created_at.utcoffset() == timedelta(0)


async def test_channel_unique_per_owner(session):
    u = User(email="a@x.com", password_hash="h", role="partner", name="A")
    session.add(u)
    await session.flush()
    session.add(Channel(owner_id=u.id, tg_chat_id=100, title="t", kind="channel"))
    await session.flush()
    session.add(Channel(owner_id=u.id, tg_chat_id=100, title="t2", kind="channel"))
    with pytest.raises(IntegrityError):
        await session.flush()
