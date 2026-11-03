import asyncio
from datetime import UTC, datetime

import httpx

from app import background
from app.main import create_app
from app.models import AccountStatus, Channel, ScheduledPost, TgAccount
from tests.conftest import make_account, reload


async def test_health_counts(client, sessionmaker, partner_a):
    await make_account(sessionmaker, partner_a, phone="+1")
    await make_account(sessionmaker, partner_a, phone="+2", status=AccountStatus.DEAD)
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "accounts": {"online": 1, "offline": 0, "dead": 1, "connecting": 0}}


async def test_lifespan_recovers_and_starts(fake, sessionmaker, partner_a, monkeypatch):
    monkeypatch.setattr(background, "INTERVALS", {k: 0.05 for k in background.INTERVALS})
    acc = await make_account(sessionmaker, partner_a, status=AccountStatus.OFFLINE)
    async with sessionmaker() as s:
        ch = Channel(owner_id=partner_a.id, tg_chat_id=-100, title="P", kind="channel", manager_account_id=acc.id)
        s.add(ch)
        await s.flush()
        post = ScheduledPost(
            owner_id=partner_a.id,
            account_id=acc.id,
            channel_id=ch.id,
            text="x",
            run_at=datetime(2026, 1, 1, tzinfo=UTC),
            status="sending",
        )
        s.add(post)
        await s.commit()
    app = create_app(gateway=fake, start_background=True, sessionmaker=sessionmaker)
    async with app.router.lifespan_context(app):
        assert len(app.state.tasks) == 6  # start_all + 5 loops
        await asyncio.sleep(0.2)
        assert (await reload(sessionmaker, TgAccount, acc.id)).status == AccountStatus.ONLINE
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            assert (await c.get("/health")).json()["accounts"]["online"] == 1
    assert all(t.done() for t in app.state.tasks)
    p = await reload(sessionmaker, ScheduledPost, post.id)
    assert p.status == "failed" and "interrompido" in p.error
    assert ("disconnect", "fake-session-+5511900000001") in fake.calls


async def test_periodic_survives_exceptions():
    calls = []

    async def boom():
        calls.append(1)
        raise RuntimeError("x")

    task = asyncio.create_task(background.periodic("t", 0.01, boom))
    await asyncio.sleep(0.08)
    task.cancel()
    assert len(calls) >= 3
