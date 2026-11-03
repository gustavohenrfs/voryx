from datetime import UTC, datetime, timedelta
from random import Random

from sqlalchemy import select

from app.jobs.handlers import HANDLERS
from app.jobs.runner import JobRunner
from app.joins.service import ApprovalThrottle, poll_all
from app.models import ActionLog, Job, JoinRequest
from app.tg.types import JoinRequestInfo
from tests.conftest import CHAT_ID

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def _req(uid, name=None):
    return JoinRequestInfo(user_id=uid, name=name or f"user{uid}", username=None, requested_at=T0)


def test_throttle_spacing_and_hourly_cap():
    t = ApprovalThrottle(rng=Random(1))
    slots = [t.next_slot(1, T0) for _ in range(301)]
    gaps = [(b - a).total_seconds() for a, b in zip(slots, slots[1:300], strict=False)]
    assert all(2 <= g <= 4 for g in gaps)
    assert slots[300] >= slots[0] + timedelta(hours=1)


def test_throttle_is_per_account():
    t = ApprovalThrottle(rng=Random(1))
    assert t.next_slot(1, T0) == T0 and t.next_slot(2, T0) == T0


def test_throttle_never_in_past():
    t = ApprovalThrottle(rng=Random(1))
    t.next_slot(1, T0)
    later = T0 + timedelta(minutes=5)
    assert t.next_slot(1, later) == later


async def _jobs(sessionmaker, type_):
    async with sessionmaker() as s:
        return (await s.execute(select(Job).where(Job.type == type_).order_by(Job.run_at))).scalars().all()


async def _requests(sessionmaker):
    async with sessionmaker() as s:
        return (await s.execute(select(JoinRequest).order_by(JoinRequest.tg_user_id))).scalars().all()


async def test_manual_mode_records_pending_and_enqueues_nothing(a_channel, fake, sessionmaker, app):
    fake.pending[CHAT_ID] = [_req(10), _req(11)]
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    assert [r.tg_user_id for r in await _requests(sessionmaker)] == [10, 11]
    assert await _jobs(sessionmaker, "approve_join") == []


async def test_poll_is_idempotent(a_channel, fake, sessionmaker, app):
    fake.pending[CHAT_ID] = [_req(10)]
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    assert len(await _requests(sessionmaker)) == 1


async def test_auto_mode_enqueues_spaced_jobs_once(a_client, a_channel, fake, sessionmaker, app):
    await a_client.patch(f"/channels/{a_channel['id']}", json={"join_mode": "auto"})
    fake.pending[CHAT_ID] = [_req(10), _req(11), _req(12)]
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    jobs = await _jobs(sessionmaker, "approve_join")
    assert len(jobs) == 3
    gaps = [(b.run_at - a.run_at).total_seconds() for a, b in zip(jobs, jobs[1:], strict=False)]
    assert all(2 <= g <= 4 for g in gaps)


async def test_switching_to_auto_enqueues_existing_pending(a_client, a_channel, fake, sessionmaker, app):
    fake.pending[CHAT_ID] = [_req(10), _req(11)]
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    await a_client.patch(f"/channels/{a_channel['id']}", json={"join_mode": "auto"})
    assert len(await _jobs(sessionmaker, "approve_join")) == 2


async def test_approve_job_decides_and_logs(a_client, a_channel, fake, sessionmaker, app):
    fake.pending[CHAT_ID] = [_req(10, "Carlos")]
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    rid = (await _requests(sessionmaker))[0].id
    r = await a_client.post(f"/channels/{a_channel['id']}/requests/{rid}/approve")
    assert r.status_code == 200
    await JobRunner(sessionmaker, app.state.manager, HANDLERS).run_once(datetime.now(UTC) + timedelta(minutes=1))
    assert ("decide_request", CHAT_ID, 10, True) in fake.calls
    jr = (await _requests(sessionmaker))[0]
    assert jr.status == "approved" and jr.decided_by == "user"
    async with sessionmaker() as s:
        log = (await s.execute(select(ActionLog))).scalar_one()
    assert log.action == "approve" and log.target == "Carlos" and log.channel_id == a_channel["id"]


async def test_reject_and_double_decide_409(a_client, a_channel, fake, sessionmaker, app):
    fake.pending[CHAT_ID] = [_req(10)]
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    rid = (await _requests(sessionmaker))[0].id
    assert (await a_client.post(f"/channels/{a_channel['id']}/requests/{rid}/reject")).status_code == 200
    await JobRunner(sessionmaker, app.state.manager, HANDLERS).run_once(datetime.now(UTC) + timedelta(minutes=1))
    assert ("decide_request", CHAT_ID, 10, False) in fake.calls
    assert (await a_client.post(f"/channels/{a_channel['id']}/requests/{rid}/approve")).status_code == 409


async def test_approve_all_single_call(a_client, a_channel, fake, sessionmaker, app):
    fake.pending[CHAT_ID] = [_req(i) for i in range(10, 15)]
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    r = await a_client.post(f"/channels/{a_channel['id']}/requests/approve-all")
    assert r.status_code == 200
    await JobRunner(sessionmaker, app.state.manager, HANDLERS).run_once(datetime.now(UTC) + timedelta(seconds=5))
    assert [c for c in fake.calls if c[0] == "approve_all"] == [("approve_all", CHAT_ID)]
    assert {r.status for r in await _requests(sessionmaker)} == {"approved"}


async def test_list_pending(a_client, a_channel, fake, sessionmaker, app):
    fake.pending[CHAT_ID] = [_req(10, "Bia")]
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    r = await a_client.get(f"/channels/{a_channel['id']}/requests?status=pending")
    assert [x["name"] for x in r.json()] == ["Bia"]


async def test_request_gone_from_telegram_marked_external(a_channel, fake, sessionmaker, app):
    fake.pending[CHAT_ID] = [_req(10)]
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    fake.pending[CHAT_ID] = []
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    jr = (await _requests(sessionmaker))[0]
    assert jr.status == "rejected" and jr.decided_by == "external"


async def test_poll_skips_channel_with_dead_manager(a_channel, a_account, fake, sessionmaker, app):
    await app.state.manager.mark_dead(a_account.id, "AuthKeyUnregisteredError")
    fake.calls.clear()
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    assert not [c for c in fake.calls if c[0] == "get_pending_requests"]


async def test_request_of_other_owner_404(b_client, a_channel, fake, sessionmaker, app):
    fake.pending[CHAT_ID] = [_req(10)]
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    rid = (await _requests(sessionmaker))[0].id
    assert (await b_client.post(f"/channels/{a_channel['id']}/requests/{rid}/approve")).status_code == 404
    assert (await b_client.get(f"/channels/{a_channel['id']}/requests")).status_code == 404
