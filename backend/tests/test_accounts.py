from datetime import timedelta

from sqlalchemy import select

from app.crypto import decrypt
from app.models import AccountStatus, Channel, Job, TgAccount
from app.tg.types import TgFloodWait
from tests.conftest import make_account, reload

START = {"phone": "+5511999", "api_id": 1, "api_hash": "abc123hash"}


async def _db_account(sessionmaker, phone):
    async with sessionmaker() as s:
        return (await s.execute(select(TgAccount).where(TgAccount.phone == phone))).scalar_one()


async def test_login_flow_without_2fa(a_client, sessionmaker, app):
    r = await a_client.post("/accounts/login/start", json=START)
    assert r.status_code == 200
    r = await a_client.post("/accounts/login/code", json={"login_id": r.json()["login_id"], "code": "12345"})
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ok"
    assert body["account"]["status"] == "online"
    row = await _db_account(sessionmaker, "+5511999")
    assert row.session_enc != "fake-session-+5511999"
    assert decrypt(row.session_enc) == "fake-session-+5511999"
    assert decrypt(row.api_hash_enc) == "abc123hash"
    assert "fake-session" not in r.text and "abc123hash" not in r.text
    assert app.state.manager.get(row.id) is not None
    async with sessionmaker() as s:
        jobs = (await s.execute(select(Job).where(Job.type == "sync_channels"))).scalars().all()
    assert [j.account_id for j in jobs] == [row.id]


async def test_login_flow_with_2fa(a_client, fake):
    fake.require_password.add("+5511999")
    r = await a_client.post("/accounts/login/start", json=START)
    lid = r.json()["login_id"]
    r = await a_client.post("/accounts/login/code", json={"login_id": lid, "code": "12345"})
    assert r.json() == {"status": "needs_password"}
    r = await a_client.post("/accounts/login/password", json={"login_id": lid, "password": "nope"})
    assert r.status_code == 400 and r.json()["detail"] == "senha 2FA incorreta"
    r = await a_client.post("/accounts/login/password", json={"login_id": lid, "password": "pw"})
    assert r.json()["status"] == "ok"


async def test_wrong_code_400(a_client):
    lid = (await a_client.post("/accounts/login/start", json=START)).json()["login_id"]
    r = await a_client.post("/accounts/login/code", json={"login_id": lid, "code": "00000"})
    assert r.status_code == 400 and r.json()["detail"] == "código inválido"


async def test_floodwait_on_start_400(a_client, fake):
    fake.fail_next["start_login"] = TgFloodWait(120)
    r = await a_client.post("/accounts/login/start", json=START)
    assert r.status_code == 400 and r.json()["detail"] == "aguarde 120s antes de tentar de novo"


async def test_login_id_of_other_user_404(a_client, b_client):
    lid = (await a_client.post("/accounts/login/start", json=START)).json()["login_id"]
    r = await b_client.post("/accounts/login/code", json={"login_id": lid, "code": "12345"})
    assert r.status_code == 404 and r.json()["detail"] == "login expirado"


async def test_expired_login_404(a_client, app):
    lid = (await a_client.post("/accounts/login/start", json=START)).json()["login_id"]
    logins = app.state.logins
    real = logins.clock
    logins.clock = lambda: real() + timedelta(minutes=11).total_seconds()
    r = await a_client.post("/accounts/login/code", json={"login_id": lid, "code": "12345"})
    assert r.status_code == 404 and r.json()["detail"] == "login expirado"


async def test_relogin_keeps_account_id(a_client, sessionmaker, partner_a):
    dead = await make_account(sessionmaker, partner_a, phone="+5511999", status=AccountStatus.DEAD)
    lid = (await a_client.post("/accounts/login/start", json={**START, "account_id": dead.id})).json()["login_id"]
    r = await a_client.post("/accounts/login/code", json={"login_id": lid, "code": "12345"})
    assert r.json()["account"]["id"] == dead.id
    acc = await reload(sessionmaker, TgAccount, dead.id)
    assert acc.status == AccountStatus.ONLINE and acc.dead_reason is None


async def test_relogin_other_owner_account_404(b_client, sessionmaker, partner_a):
    acc = await make_account(sessionmaker, partner_a)
    r = await b_client.post("/accounts/login/start", json={**START, "account_id": acc.id})
    assert r.status_code == 404


async def test_import_session_revives_dead(a_client, sessionmaker, partner_a):
    dead = await make_account(sessionmaker, partner_a, status=AccountStatus.DEAD)
    r = await a_client.post(f"/accounts/{dead.id}/session", json={"session": "fake-session-new"})
    assert r.status_code == 200 and r.json()["status"] == "online"
    assert decrypt((await reload(sessionmaker, TgAccount, dead.id)).session_enc) == "fake-session-new"


async def test_import_invalid_session_400(a_client, sessionmaker, partner_a, fake):
    acc = await make_account(sessionmaker, partner_a, status=AccountStatus.DEAD)
    fake.dead_sessions.add("bad-session-xyz")
    r = await a_client.post(f"/accounts/{acc.id}/session", json={"session": "bad-session-xyz"})
    assert r.status_code == 400 and r.json()["detail"] == "session inválida"


async def test_list_accounts_only_own(a_client, sessionmaker, partner_a, partner_b):
    await make_account(sessionmaker, partner_a, phone="+1")
    await make_account(sessionmaker, partner_b, phone="+2")
    r = await a_client.get("/accounts")
    assert [a["phone"] for a in r.json()] == ["+1"]
    assert "session_enc" not in r.text and "api_hash" not in r.text


async def test_patch_label_and_check(a_client, sessionmaker, partner_a):
    acc = await make_account(sessionmaker, partner_a)
    r = await a_client.patch(f"/accounts/{acc.id}", json={"label": "Ana"})
    assert r.json()["label"] == "Ana"
    r = await a_client.post(f"/accounts/{acc.id}/check")
    assert r.status_code == 200 and r.json()["status"] == "online"


async def test_delete_manager_account_409(a_client, sessionmaker, partner_a):
    acc = await make_account(sessionmaker, partner_a)
    async with sessionmaker() as s:
        s.add(Channel(owner_id=partner_a.id, tg_chat_id=-100, title="P", kind="channel", manager_account_id=acc.id))
        await s.commit()
    assert (await a_client.delete(f"/accounts/{acc.id}")).status_code == 409


async def test_delete_account(a_client, sessionmaker, partner_a):
    acc = await make_account(sessionmaker, partner_a)
    assert (await a_client.delete(f"/accounts/{acc.id}")).status_code == 200
    assert await reload(sessionmaker, TgAccount, acc.id) is None
