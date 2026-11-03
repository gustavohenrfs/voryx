import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.jobs.handlers import FAIL_HOOKS, HANDLERS, RETRY_HOOKS
from app.jobs.runner import JobRunner
from app.models import Job, PostMedia, ScheduledPost
from app.posts.media import cleanup_media
from app.posts.service import recover_interrupted_posts
from app.tg.types import TgFloodWait, TgTransient
from tests.conftest import CHAT_ID, make_account, reload

RUN_AT = "2026-11-10T20:00:00-03:00"
RUN_AT_UTC = datetime(2026, 11, 10, 23, 0, tzinfo=UTC)
TEXT = "Prévia nova \U0001f525"


@pytest.fixture
def runner(sessionmaker, app):
    return JobRunner(sessionmaker, app.state.manager, HANDLERS, FAIL_HOOKS, RETRY_HOOKS)


@pytest.fixture
def base(a_account, a_channel):
    return {"account_id": a_account.id, "channel_id": a_channel["id"], "text": TEXT}


async def _upload(c, name="f.jpg", mime="image/jpeg"):
    r = await c.post("/media", files={"file": (name, b"\xff\xd8\xff123", mime)})
    assert r.status_code == 201
    return r.json()["id"]


async def test_timezone_stored_utc(a_client, base, sessionmaker):
    r = await a_client.post("/posts", json={**base, "run_at": RUN_AT})
    assert r.status_code == 201, r.text
    post = await reload(sessionmaker, ScheduledPost, r.json()["id"])
    assert post.run_at == RUN_AT_UTC and post.status == "scheduled"


async def test_past_run_at_422(a_client, base):
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    r = await a_client.post("/posts", json={**base, "run_at": past})
    assert r.status_code == 422 and "horário no passado" in r.text


async def test_missing_run_at_422(a_client, base):
    assert (await a_client.post("/posts", json=base)).status_code == 422


async def test_empty_post_422(a_client, base):
    r = await a_client.post("/posts", json={**base, "text": "  ", "run_at": RUN_AT})
    assert r.status_code == 422


async def test_caption_1025_with_media_422(a_client, base):
    mid = await _upload(a_client)
    r = await a_client.post("/posts", json={**base, "text": "x" * 1025, "media_ids": [mid], "run_at": RUN_AT})
    assert r.status_code == 422


async def test_text_4097_422_and_4096_ok(a_client, base):
    assert (await a_client.post("/posts", json={**base, "text": "x" * 4097, "run_at": RUN_AT})).status_code == 422
    assert (await a_client.post("/posts", json={**base, "text": "x" * 4096, "run_at": RUN_AT})).status_code == 201


async def test_more_than_10_media_422(a_client, base):
    ids = [await _upload(a_client, f"{i}.jpg") for i in range(11)]
    r = await a_client.post("/posts", json={**base, "text": "", "media_ids": ids, "run_at": RUN_AT})
    assert r.status_code == 422


async def test_media_reuse_409(a_client, base):
    mid = await _upload(a_client)
    assert (await a_client.post("/posts", json={**base, "media_ids": [mid], "run_at": RUN_AT})).status_code == 201
    assert (await a_client.post("/posts", json={**base, "media_ids": [mid], "run_at": RUN_AT})).status_code == 409


async def test_other_owner_media_404(a_client, b_client, base):
    mid = await _upload(b_client)
    r = await a_client.post("/posts", json={**base, "media_ids": [mid], "run_at": RUN_AT})
    assert r.status_code == 404


async def test_cannot_post_422(a_client, base, fake):
    fake.no_post.add(CHAT_ID)
    r = await a_client.post("/posts", json={**base, "run_at": RUN_AT})
    assert r.status_code == 422 and r.json()["detail"] == "a conta não pode postar neste grupo"


async def test_send_post_success_with_album(a_client, base, runner, sessionmaker, fake):
    ids = [await _upload(a_client, "a.jpg"), await _upload(a_client, "b.mp4", "video/mp4")]
    r = await a_client.post("/posts", json={**base, "media_ids": ids, "run_at": RUN_AT})
    await runner.run_once(RUN_AT_UTC)
    post = await reload(sessionmaker, ScheduledPost, r.json()["id"])
    assert post.status == "sent" and post.sent_message_ids == [1000, 1001]
    sent = [c for c in fake.calls if c[0] == "send_post"][0]
    assert sent[2] == TEXT and [os.path.splitext(p)[1] for p in sent[3]] == [".jpg", ".mp4"]


async def test_post_now_runs_immediately(a_client, base, runner, sessionmaker):
    r = await a_client.post("/posts", json={**base, "post_now": True})
    assert r.status_code == 201
    await runner.run_once()
    assert (await reload(sessionmaker, ScheduledPost, r.json()["id"])).status == "sent"


async def test_cancel_prevents_send(a_client, base, runner, sessionmaker, fake):
    pid = (await a_client.post("/posts", json={**base, "run_at": RUN_AT})).json()["id"]
    assert (await a_client.delete(f"/posts/{pid}")).status_code == 200
    await runner.run_once(RUN_AT_UTC)
    assert (await reload(sessionmaker, ScheduledPost, pid)).status == "canceled"
    assert not [c for c in fake.calls if c[0] == "send_post"]


async def test_edit_moves_job(a_client, base, sessionmaker):
    pid = (await a_client.post("/posts", json={**base, "run_at": RUN_AT})).json()["id"]
    r = await a_client.patch(f"/posts/{pid}", json={"run_at": "2026-11-11T09:30:00-03:00", "text": "editado"})
    assert r.status_code == 200 and r.json()["text"] == "editado"
    post = await reload(sessionmaker, ScheduledPost, pid)
    job = await reload(sessionmaker, Job, post.job_id)
    assert job.run_at == datetime(2026, 11, 11, 12, 30, tzinfo=UTC)


async def test_edit_sent_post_409(a_client, base, runner):
    pid = (await a_client.post("/posts", json={**base, "run_at": RUN_AT})).json()["id"]
    await runner.run_once(RUN_AT_UTC)
    assert (await a_client.patch(f"/posts/{pid}", json={"text": "x"})).status_code == 409


async def test_floodwait_keeps_scheduled(a_client, base, runner, sessionmaker, fake):
    pid = (await a_client.post("/posts", json={**base, "run_at": RUN_AT})).json()["id"]
    fake.fail_next["send_post"] = TgFloodWait(40)
    await runner.run_once(RUN_AT_UTC)
    post = await reload(sessionmaker, ScheduledPost, pid)
    assert post.status == "scheduled" and "flood" in post.error


async def test_network_error_during_send_fails_without_retry(a_client, base, runner, sessionmaker, fake):
    pid = (await a_client.post("/posts", json={**base, "run_at": RUN_AT})).json()["id"]
    fake.fail_next["send_post"] = TgTransient("connection reset")
    await runner.run_once(RUN_AT_UTC)
    post = await reload(sessionmaker, ScheduledPost, pid)
    assert post.status == "failed" and "verificar no grupo" in post.error
    await runner.run_once(RUN_AT_UTC + timedelta(hours=1))
    assert len([c for c in fake.calls if c[0] == "send_post"]) == 1


async def test_recover_sending_marks_failed_not_resent(a_client, base, runner, sessionmaker, fake):
    pid = (await a_client.post("/posts", json={**base, "run_at": RUN_AT})).json()["id"]
    async with sessionmaker() as s:
        post = await s.get(ScheduledPost, pid)
        post.status = "sending"
        (await s.get(Job, post.job_id)).status = "running"
        await s.commit()
    async with sessionmaker() as s:
        await recover_interrupted_posts(s)
        await s.commit()
    await runner.run_once(RUN_AT_UTC + timedelta(hours=1))
    post = await reload(sessionmaker, ScheduledPost, pid)
    assert post.status == "failed" and post.error == "interrompido durante o envio — verificar no grupo"
    assert not [c for c in fake.calls if c[0] == "send_post"]


async def test_recover_requeues_other_running_jobs(sessionmaker):
    async with sessionmaker() as s:
        s.add(Job(type="sync_channels", payload={}, status="running", run_at=RUN_AT_UTC))
        await s.commit()
        await recover_interrupted_posts(s)
        await s.commit()
        job = (await s.execute(select(Job))).scalar_one()
    assert job.status == "pending"


async def test_list_posts_filters(a_client, base):
    await a_client.post("/posts", json={**base, "run_at": RUN_AT})
    r = await a_client.get("/posts", params={"from": "2026-11-10T00:00:00-03:00", "to": "2026-11-11T00:00:00-03:00"})
    assert len(r.json()) == 1
    r = await a_client.get("/posts", params={"from": "2026-11-12T00:00:00-03:00"})
    assert r.json() == []


async def test_account_of_other_owner_404(a_client, base, sessionmaker, partner_b):
    other = await make_account(sessionmaker, partner_b, phone="+77")
    r = await a_client.post("/posts", json={**base, "account_id": other.id, "run_at": RUN_AT})
    assert r.status_code == 404


async def test_cleanup_removes_old_media(a_client, base, runner, sessionmaker):
    mid = await _upload(a_client)
    orphan = await _upload(a_client, "o.jpg")
    pid = (await a_client.post("/posts", json={**base, "media_ids": [mid], "run_at": RUN_AT})).json()["id"]
    await runner.run_once(RUN_AT_UTC)
    async with sessionmaker() as s:
        paths = [m.path for m in (await s.execute(select(PostMedia))).scalars()]
        assert all(os.path.exists(p) for p in paths)
        await cleanup_media(s, RUN_AT_UTC + timedelta(days=1))
        await s.commit()
    assert await reload(sessionmaker, PostMedia, mid) is not None  # sent 1 day ago: kept
    assert await reload(sessionmaker, PostMedia, orphan) is None  # orphan older than 24h: removed
    async with sessionmaker() as s:
        await cleanup_media(s, RUN_AT_UTC + timedelta(days=8))
        await s.commit()
    assert await reload(sessionmaker, PostMedia, mid) is None
    assert not any(os.path.exists(p) for p in paths)
    assert (await reload(sessionmaker, ScheduledPost, pid)).status == "sent"
