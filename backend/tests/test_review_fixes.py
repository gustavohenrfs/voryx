"""Regression tests for the final-review findings (C1-C3, I1-I9)."""

import asyncio
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from telethon import types
from telethon.errors import FloodWaitError

from app.jobs.handlers import FAIL_HOOKS, HANDLERS, RETRY_HOOKS
from app.jobs.runner import JobContext, JobRunner, enqueue
from app.joins.service import poll_all
from app.models import AccountStatus, Channel, Job, JobStatus, JoinRequest, ScheduledPost
from app.posts.service import recover_interrupted_posts, send_post
from app.tg import http as tg_http
from app.tg import telethon_gateway as tgw
from app.tg.types import ChatRef, JoinRequestInfo, TgFloodWait, TgTransient
from tests.conftest import CHAT_ID, make_account, reload
from tests.test_joins import T0

RUN_AT = "2026-11-10T20:00:00-03:00"
RUN_AT_UTC = datetime(2026, 11, 10, 23, 0, tzinfo=UTC)


def _runner(sessionmaker, app):
    return JobRunner(sessionmaker, app.state.manager, HANDLERS, FAIL_HOOKS, RETRY_HOOKS)


# ---------------------------------------------------------------- C1
class _StubTelethon:
    """Minimal TelegramClient stand-in: knows its OWN access hash for the channel only after get_dialogs()."""

    def __init__(self, own_hash: int):
        self.own_hash = own_hash
        self.cache_warm = False
        self.sent_to = []

    async def get_input_entity(self, peer):
        if isinstance(peer, types.PeerChannel) and self.cache_warm:
            return types.InputPeerChannel(peer.channel_id, self.own_hash)
        raise ValueError("not in cache")

    async def get_dialogs(self, limit=None):
        self.cache_warm = True
        return []

    async def send_message(self, peer, text, **kw):
        self.sent_to.append(peer)
        return types.Message(id=1, peer_id=None, message=text)


async def test_c1_peer_resolved_with_the_accounts_own_access_hash():
    stub = _StubTelethon(own_hash=222)
    client = tgw.TelethonClient(stub)
    await client.send_post(ChatRef(CHAT_ID, 111), "oi", [])  # 111 = hash of the account that imported
    assert stub.sent_to[0].access_hash == 222


# ---------------------------------------------------------------- C2
async def test_c2_recovery_requeues_claimed_but_unstarted_post(a_client, a_account, a_channel, sessionmaker, app, fake):
    pid = (
        await a_client.post(
            "/posts", json={"account_id": a_account.id, "channel_id": a_channel["id"], "text": "x", "run_at": RUN_AT}
        )
    ).json()["id"]
    async with sessionmaker() as s:
        post = await s.get(ScheduledPost, pid)
        (await s.get(Job, post.job_id)).status = JobStatus.RUNNING  # claimed, never started
        await s.commit()
    async with sessionmaker() as s:
        await recover_interrupted_posts(s)
        await s.commit()
    await _runner(sessionmaker, app).run_once(RUN_AT_UTC)
    assert (await reload(sessionmaker, ScheduledPost, pid)).status == "sent"


# ---------------------------------------------------------------- C3
class _ConnectStub:
    def __init__(self, exc):
        self.exc = exc

    async def connect(self):
        return None

    async def is_user_authorized(self):
        return False  # what Telethon returns on ANY RPCError, e.g. FloodWait

    async def get_me(self):
        raise self.exc

    async def disconnect(self):
        return None


async def test_c3_transient_error_on_connect_is_not_fatal(monkeypatch):
    monkeypatch.setattr(tgw, "_new_client", lambda *a: _ConnectStub(FloodWaitError(request=None, capture=30)))
    with pytest.raises((TgFloodWait, TgTransient)):
        await tgw.TelethonGateway().connect("s", 1, "h")


# ---------------------------------------------------------------- I1
async def test_i1_floodwait_pushes_back_other_jobs_of_the_account(sessionmaker, manager, partner_a):
    acc = await make_account(sessionmaker, partner_a)
    await manager.start_all()

    async def flood(ctx):
        raise TgFloodWait(60)

    runner = JobRunner(sessionmaker, manager, {"t": flood})
    async with sessionmaker() as s:
        jobs = [await enqueue(s, "t", {}, acc.id, run_at=T0 + timedelta(seconds=3 * i)) for i in range(3)]
        await s.commit()
    await runner.run_once(T0)
    later = [await reload(sessionmaker, Job, j.id) for j in jobs[1:]]
    assert all(j.status == "pending" for j in later)
    assert all(j.run_at >= T0 + timedelta(seconds=65) for j in later)
    assert later[1].run_at - later[0].run_at == timedelta(seconds=3)  # spacing preserved


# ---------------------------------------------------------------- I2
async def test_i2_failed_approval_releases_request(a_client, a_channel, a_account, fake, sessionmaker, app):
    fake.pending[CHAT_ID] = [JoinRequestInfo(user_id=10, name="x", username=None, requested_at=T0)]
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    rid = (await a_client.get(f"/channels/{a_channel['id']}/requests")).json()[0]["id"]
    await a_client.post(f"/channels/{a_channel['id']}/requests/{rid}/approve")
    async with sessionmaker() as s:
        (await s.get(type(a_account), a_account.id)).status = AccountStatus.DEAD
        await s.commit()
    await _runner(sessionmaker, app).run_once(datetime.now(UTC) + timedelta(minutes=1))
    assert (await reload(sessionmaker, JoinRequest, rid)).queued_at is None


# ---------------------------------------------------------------- I3 + I4
async def _post(a_client, a_account, a_channel):
    return (
        await a_client.post(
            "/posts", json={"account_id": a_account.id, "channel_id": a_channel["id"], "text": "x", "run_at": RUN_AT}
        )
    ).json()["id"]


async def test_i3_post_moved_later_is_not_sent_at_old_time(a_client, a_account, a_channel, sessionmaker, app, fake):
    pid = await _post(a_client, a_account, a_channel)
    async with sessionmaker() as s:  # simulate: job already claimed when the user moved the post to 22:00
        post = await s.get(ScheduledPost, pid)
        post.run_at = RUN_AT_UTC + timedelta(hours=2)
        await s.commit()
    await _runner(sessionmaker, app).run_once(RUN_AT_UTC)
    assert not [c for c in fake.calls if c[0] == "send_post"]
    async with sessionmaker() as s:
        post = await s.get(ScheduledPost, pid)
        job = await s.get(Job, post.job_id)
    assert job.status == "pending" and job.run_at == RUN_AT_UTC + timedelta(hours=2)


async def test_i4_cancel_wins_over_stale_send(a_client, a_account, a_channel, sessionmaker, app, fake):
    pid = await _post(a_client, a_account, a_channel)
    async with sessionmaker() as stale:
        post = await stale.get(ScheduledPost, pid)  # loaded as scheduled
        job = await stale.get(Job, post.job_id)
        assert (await a_client.delete(f"/posts/{pid}")).status_code == 200  # committed elsewhere
        ctx = JobContext(
            db=stale, job=job, client=app.state.manager.get(a_account.id), manager=app.state.manager, now=RUN_AT_UTC
        )
        await send_post(ctx)
        await stale.commit()
    assert not [c for c in fake.calls if c[0] == "send_post"]
    assert (await reload(sessionmaker, ScheduledPost, pid)).status == "canceled"


# ---------------------------------------------------------------- I5
async def test_i5_mark_dead_flags_managed_channels(a_channel, a_account, app, sessionmaker):
    await app.state.manager.mark_dead(a_account.id, "SessionRevokedError")
    assert (await reload(sessionmaker, Channel, a_channel["id"])).status == "conta_caida"


async def test_i5_import_session_enqueues_sync(a_client, a_account, sessionmaker):
    await a_client.post(f"/accounts/{a_account.id}/session", json={"session": "fake-session-novo"})
    async with sessionmaker() as s:
        jobs = (await s.execute(select(Job).where(Job.type == "sync_channels"))).scalars().all()
    assert [j.account_id for j in jobs] == [a_account.id]


# ---------------------------------------------------------------- I6
async def test_i6_jobs_of_different_accounts_run_concurrently(sessionmaker, manager, partner_a):
    a = await make_account(sessionmaker, partner_a, phone="+1")
    b = await make_account(sessionmaker, partner_a, phone="+2")
    await manager.start_all()
    b_started = asyncio.Event()

    async def handler(ctx):
        if ctx.job.account_id == a.id:
            await asyncio.wait_for(b_started.wait(), 2)  # A's long upload waits for B to have started
        else:
            b_started.set()

    runner = JobRunner(sessionmaker, manager, {"t": handler})
    async with sessionmaker() as s:
        ja = await enqueue(s, "t", {}, a.id, run_at=T0)
        jb = await enqueue(s, "t", {}, b.id, run_at=T0 + timedelta(seconds=1))
        await s.commit()
    await runner.run_once(T0 + timedelta(seconds=2))
    assert (await reload(sessionmaker, Job, ja.id)).status == "done"
    assert (await reload(sessionmaker, Job, jb.id)).status == "done"


async def test_i6_panel_call_on_busy_account_returns_409(manager, sessionmaker, partner_a, monkeypatch):
    acc = await make_account(sessionmaker, partner_a)
    await manager.start_all()
    monkeypatch.setattr(tg_http, "LOCK_WAIT_S", 0.05)
    async with manager.lock(acc.id):
        with pytest.raises(HTTPException) as e:
            await tg_http.tg_call(manager, acc.id, lambda c: c.get_me())
    assert e.value.status_code == 409


# ---------------------------------------------------------------- I9
async def test_i9_start_all_connects_concurrently(fake, manager, sessionmaker, partner_a):
    for i in range(4):
        await make_account(sessionmaker, partner_a, phone=f"+{i}")
    fake.connect_delay = 0.2
    t = time.perf_counter()
    await manager.start_all()
    assert time.perf_counter() - t < 0.6
    assert len(manager.clients) == 4
