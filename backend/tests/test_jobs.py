from datetime import UTC, datetime, timedelta

import pytest

from app.jobs.runner import JobRunner, enqueue
from app.models import AccountStatus, Job, JobStatus, TgAccount
from app.tg.types import TgFatalAuth, TgFloodWait, TgPermanent, TgTransient
from tests.conftest import make_account, reload

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


class Recorder:
    def __init__(self):
        self.ran = []
        self.failed = []
        self.retried = []
        self.raise_seq = []

    async def handler(self, ctx):
        self.ran.append((ctx.job.id, ctx.client is not None))
        if self.raise_seq:
            raise self.raise_seq.pop(0)

    async def on_fail(self, ctx):
        self.failed.append((ctx.job.id, ctx.job.last_error))

    async def on_retry(self, ctx):
        self.retried.append(ctx.job.id)


@pytest.fixture
def rec():
    return Recorder()


@pytest.fixture
async def account(sessionmaker, partner_a, manager):
    acc = await make_account(sessionmaker, partner_a)
    await manager.start_all()
    return acc


@pytest.fixture
def runner(sessionmaker, manager, rec):
    return JobRunner(
        sessionmaker,
        manager,
        handlers={"t": rec.handler},
        fail_hooks={"t": rec.on_fail},
        retry_hooks={"t": rec.on_retry},
    )


async def _enqueue(sessionmaker, account_id, run_at=NOW, type_="t"):
    async with sessionmaker() as db:
        job = await enqueue(db, type_, {"x": 1}, account_id, run_at=run_at)
        await db.commit()
        return job


async def test_success_marks_done_with_client(runner, rec, sessionmaker, account):
    job = await _enqueue(sessionmaker, account.id)
    assert await runner.run_once(NOW) == 1
    assert rec.ran == [(job.id, True)]
    assert (await reload(sessionmaker, Job, job.id)).status == JobStatus.DONE


async def test_future_job_not_run(runner, rec, sessionmaker, account):
    await _enqueue(sessionmaker, account.id, run_at=NOW + timedelta(seconds=10))
    assert await runner.run_once(NOW) == 0 and rec.ran == []


async def test_floodwait_reschedules_without_attempt(runner, rec, sessionmaker, account):
    job = await _enqueue(sessionmaker, account.id)
    rec.raise_seq = [TgFloodWait(60)]
    await runner.run_once(NOW)
    j = await reload(sessionmaker, Job, job.id)
    assert j.status == JobStatus.PENDING and j.attempts == 0
    assert j.run_at == NOW + timedelta(seconds=65)
    assert rec.retried == [job.id]


async def test_transient_retries_three_times_then_fails(runner, rec, sessionmaker, account):
    job = await _enqueue(sessionmaker, account.id)
    rec.raise_seq = [TgTransient("x")] * 4
    now = NOW
    for expected_delay in (30, 120, 600):
        await runner.run_once(now)
        j = await reload(sessionmaker, Job, job.id)
        assert j.status == JobStatus.PENDING and j.run_at == now + timedelta(seconds=expected_delay)
        now = j.run_at
    await runner.run_once(now)
    j = await reload(sessionmaker, Job, job.id)
    assert j.status == JobStatus.FAILED and j.attempts == 4
    assert rec.failed == [(job.id, j.last_error)]


async def test_dead_account_job_fails_without_calling_handler(runner, rec, sessionmaker, partner_a):
    dead = await make_account(sessionmaker, partner_a, phone="+3", status=AccountStatus.DEAD)
    job = await _enqueue(sessionmaker, dead.id)
    await runner.run_once(NOW)
    j = await reload(sessionmaker, Job, job.id)
    assert j.status == JobStatus.FAILED and j.last_error == "conta caída"
    assert rec.ran == [] and rec.failed == [(job.id, "conta caída")]


async def test_offline_account_is_retried(runner, rec, sessionmaker, partner_a):
    off = await make_account(sessionmaker, partner_a, phone="+4", status=AccountStatus.OFFLINE)
    job = await _enqueue(sessionmaker, off.id)  # manager never connected it
    await runner.run_once(NOW)
    j = await reload(sessionmaker, Job, job.id)
    assert j.status == JobStatus.PENDING and j.attempts == 1 and rec.ran == []


async def test_fatal_auth_marks_account_dead(runner, rec, sessionmaker, account):
    job = await _enqueue(sessionmaker, account.id)
    rec.raise_seq = [TgFatalAuth("UserDeactivatedBanError")]
    await runner.run_once(NOW)
    assert (await reload(sessionmaker, Job, job.id)).status == JobStatus.FAILED
    acc = await reload(sessionmaker, TgAccount, account.id)
    assert acc.status == AccountStatus.DEAD and acc.dead_reason == "UserDeactivatedBanError"


async def test_permanent_error_fails_with_message(runner, rec, sessionmaker, account):
    job = await _enqueue(sessionmaker, account.id)
    rec.raise_seq = [TgPermanent("CHAT_ADMIN_REQUIRED")]
    await runner.run_once(NOW)
    j = await reload(sessionmaker, Job, job.id)
    assert j.status == JobStatus.FAILED and "CHAT_ADMIN_REQUIRED" in j.last_error


async def test_job_without_account_runs_without_client(runner, rec, sessionmaker):
    job = await _enqueue(sessionmaker, None)
    await runner.run_once(NOW)
    assert rec.ran == [(job.id, False)]


async def test_unknown_type_fails(runner, sessionmaker):
    job = await _enqueue(sessionmaker, None, type_="nope")
    await runner.run_once(NOW)
    assert (await reload(sessionmaker, Job, job.id)).status == JobStatus.FAILED
