"""Partner B must never see or change partner A's data: every route answers 404 and nothing reaches Telegram."""

import pytest

from app.joins.service import poll_all
from app.tg.types import JoinRequestInfo
from tests.conftest import CHAT_ID
from tests.test_joins import T0

ROUTES = [
    ("GET", "/accounts/{acc}/dialogs"),
    ("PATCH", "/accounts/{acc}"),
    ("DELETE", "/accounts/{acc}"),
    ("POST", "/accounts/{acc}/session"),
    ("POST", "/accounts/{acc}/check"),
    ("GET", "/channels/{ch}"),
    ("PATCH", "/channels/{ch}"),
    ("POST", "/channels/{ch}/refresh"),
    ("DELETE", "/channels/{ch}"),
    ("GET", "/channels/{ch}/requests"),
    ("POST", "/channels/{ch}/requests/refresh"),
    ("POST", "/channels/{ch}/requests/{rq}/approve"),
    ("POST", "/channels/{ch}/requests/{rq}/reject"),
    ("POST", "/channels/{ch}/requests/approve-all"),
    ("GET", "/channels/{ch}/members"),
    ("POST", "/channels/{ch}/members/1/kick"),
    ("POST", "/channels/{ch}/members/1/ban"),
    ("PATCH", "/posts/{post}"),
    ("DELETE", "/posts/{post}"),
]

BODIES = {
    "/accounts/{acc}/session": {"session": "fake-session-stolen"},
    "/accounts/{acc}": {"label": "hack"},
    "/channels/{ch}": {"join_mode": "auto"},
    "/posts/{post}": {"text": "hack"},
}


@pytest.fixture
async def a_data(a_client, a_account, a_channel, fake, sessionmaker, app):
    fake.pending[CHAT_ID] = [JoinRequestInfo(user_id=10, name="x", username=None, requested_at=T0)]
    await poll_all(sessionmaker, app.state.manager, app.state.throttle)
    rq = (await a_client.get(f"/channels/{a_channel['id']}/requests")).json()[0]["id"]
    media = (await a_client.post("/media", files={"file": ("a.jpg", b"\xff\xd8", "image/jpeg")})).json()["id"]
    post = (
        await a_client.post(
            "/posts",
            json={
                "account_id": a_account.id,
                "channel_id": a_channel["id"],
                "text": "oi",
                "run_at": "2026-11-10T20:00:00-03:00",
            },
        )
    ).json()["id"]
    fake.calls.clear()
    return {"acc": a_account.id, "ch": a_channel["id"], "rq": rq, "post": post, "media": media}


@pytest.mark.parametrize("method,path", ROUTES)
async def test_other_owner_gets_404(method, path, b_client, a_data, fake, a_client):
    body = BODIES.get(path, {})
    r = await b_client.request(method, path.format(**a_data), json=body)
    assert r.status_code == 404, (path, r.status_code, r.text)
    assert fake.mutating_calls() == []
    assert ("connect", "fake-session-stolen") not in fake.calls
    # A's data is untouched
    assert (await a_client.get(f"/channels/{a_data['ch']}")).json()["join_mode"] == "manual"


async def test_list_endpoints_hide_other_owner(b_client, a_data):
    for path in ("/accounts", "/channels", "/posts", "/logs"):
        assert (await b_client.get(path)).json() == [], path


async def test_post_with_other_owner_account_channel_or_media_404(b_client, a_data, sessionmaker, partner_b):
    from tests.conftest import make_account

    b_acc = await make_account(sessionmaker, partner_b, phone="+55119")
    for payload in (
        {"account_id": a_data["acc"], "channel_id": a_data["ch"]},
        {"account_id": b_acc.id, "channel_id": a_data["ch"]},
    ):
        r = await b_client.post("/posts", json={**payload, "text": "x", "post_now": True})
        assert r.status_code == 404


async def test_media_of_other_owner_404(b_client, a_data, sessionmaker, partner_b, fake):
    from tests.conftest import add_dialog, make_account

    b_acc = await make_account(sessionmaker, partner_b, phone="+55118")
    await b_client.post(f"/accounts/{b_acc.id}/check")
    add_dialog(fake, chat_id=-1005, title="B group")
    ch = (await b_client.post("/channels", json={"account_id": b_acc.id, "chat_id": -1005})).json()["id"]
    r = await b_client.post(
        "/posts",
        json={"account_id": b_acc.id, "channel_id": ch, "text": "x", "media_ids": [a_data["media"]], "post_now": True},
    )
    assert r.status_code == 404


async def test_admin_sees_all(admin_client, a_data):
    assert len((await admin_client.get("/accounts")).json()) == 1
    assert len((await admin_client.get("/channels")).json()) == 1
    assert (await admin_client.get(f"/channels/{a_data['ch']}")).status_code == 200


async def test_no_secret_in_any_response(a_client, a_data):
    paths = [
        "/accounts",
        "/channels",
        f"/channels/{a_data['ch']}",
        f"/channels/{a_data['ch']}/requests",
        "/posts",
        "/logs",
        "/auth/me",
    ]
    for p in paths:
        text = (await a_client.get(p)).text
        assert "fake-session" not in text and "hash" not in text.lower() and "gAAAA" not in text, p
