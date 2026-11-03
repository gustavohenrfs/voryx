from app.models import AccountStatus, Channel
from app.tg.types import TgPermanent
from tests.conftest import CHAT_ID, add_dialog, make_account, reload


async def test_import_and_detail(a_client, a_channel):
    assert a_channel["title"] == "Prévias VIP" and a_channel["member_count"] == 1500
    assert a_channel["join_mode"] == "manual" and a_channel["status"] == "ok"
    r = await a_client.get(f"/channels/{a_channel['id']}")
    assert [a["name"] for a in r.json()["admins"]] == ["Dona", "Ana"]
    assert r.json()["admins"][1]["rights"]["ban_users"] is True


async def test_dialogs_excludes_imported(a_client, a_account, a_channel, fake):
    add_dialog(fake, chat_id=-1009, title="Outro")
    r = await a_client.get(f"/accounts/{a_account.id}/dialogs")
    assert [d["title"] for d in r.json()] == ["Outro"]


async def test_import_twice_409(a_client, a_account, a_channel):
    r = await a_client.post("/channels", json={"account_id": a_account.id, "chat_id": CHAT_ID})
    assert r.status_code == 409


async def test_import_unknown_chat_404(a_client, a_account):
    r = await a_client.post("/channels", json={"account_id": a_account.id, "chat_id": -1})
    assert r.status_code == 404


async def test_list_channels_has_pending_count(a_client, a_channel):
    r = await a_client.get("/channels")
    assert r.json()[0]["pending_count"] == 0


async def test_manager_account_of_other_owner_404(a_client, a_channel, sessionmaker, partner_b):
    other = await make_account(sessionmaker, partner_b, phone="+2")
    r = await a_client.patch(f"/channels/{a_channel['id']}", json={"manager_account_id": other.id})
    assert r.status_code == 404


async def test_change_manager_account(a_client, a_channel, sessionmaker, partner_a, app):
    second = await make_account(sessionmaker, partner_a, phone="+5")
    await app.state.manager.start_all()
    r = await a_client.patch(f"/channels/{a_channel['id']}", json={"manager_account_id": second.id})
    assert r.status_code == 200 and r.json()["manager_account_id"] == second.id


async def test_change_join_mode(a_client, a_channel):
    r = await a_client.patch(f"/channels/{a_channel['id']}", json={"join_mode": "auto"})
    assert r.json()["join_mode"] == "auto"
    r = await a_client.patch(f"/channels/{a_channel['id']}", json={"join_mode": "bogus"})
    assert r.status_code == 422


async def test_dead_manager_shows_conta_caida(a_client, a_channel, a_account, app):
    await app.state.manager.mark_dead(a_account.id, "AuthKeyUnregisteredError")
    r = await a_client.post(f"/channels/{a_channel['id']}/refresh")
    assert r.json()["status"] == "conta_caida"


async def test_lost_access_shows_sem_acesso(a_client, a_channel, fake):
    fake.fail_next["get_chat"] = TgPermanent("CHANNEL_PRIVATE")
    r = await a_client.post(f"/channels/{a_channel['id']}/refresh")
    assert r.json()["status"] == "sem_acesso"


async def test_refresh_all_via_sync_job(a_channel, fake, sessionmaker, app, a_account):
    from app.jobs.handlers import HANDLERS
    from app.jobs.runner import JobRunner

    fake.dialogs[0].member_count = 1600
    runner = JobRunner(sessionmaker, app.state.manager, HANDLERS)
    from tests.test_jobs import _enqueue  # reuse helper

    await _enqueue(sessionmaker, a_account.id, type_="sync_channels")
    await runner.run_once()
    assert (await reload(sessionmaker, Channel, a_channel["id"])).member_count == 1600


async def test_delete_channel(a_client, a_channel, sessionmaker):
    assert (await a_client.delete(f"/channels/{a_channel['id']}")).status_code == 200
    assert await reload(sessionmaker, Channel, a_channel["id"]) is None


async def test_dialogs_of_offline_account_409(a_client, sessionmaker, partner_a):
    acc = await make_account(sessionmaker, partner_a, phone="+8", status=AccountStatus.OFFLINE)
    assert (await a_client.get(f"/accounts/{acc.id}/dialogs")).status_code == 409
