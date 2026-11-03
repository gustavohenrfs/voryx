from app.models import ActionLog
from app.tg.types import MemberInfo, TgFatalAuth, TgFloodWait
from tests.conftest import CHAT_ID, make_account


def _members(fake):
    fake.members[CHAT_ID] = [MemberInfo(user_id=700 + i, name=f"Fã {i}", username=None) for i in range(5)]
    fake.members[CHAT_ID].append(MemberInfo(user_id=777, name="Spammer", username="spam"))


async def test_members_search_passes_query(a_client, a_channel, fake):
    _members(fake)
    r = await a_client.get(f"/channels/{a_channel['id']}/members?q=spam&limit=10")
    assert r.status_code == 200 and [m["user_id"] for m in r.json()] == [777]
    assert ("search_members", CHAT_ID, "spam", 0, 10) in fake.calls


async def test_members_limit_capped(a_client, a_channel, fake):
    _members(fake)
    await a_client.get(f"/channels/{a_channel['id']}/members?limit=5000")
    assert ("search_members", CHAT_ID, "", 0, 200) in fake.calls


async def test_kick_calls_gateway_and_logs(a_client, a_channel, fake):
    r = await a_client.post(f"/channels/{a_channel['id']}/members/777/kick", json={"name": "Spammer"})
    assert r.status_code == 200
    assert ("kick", CHAT_ID, 777) in fake.calls
    logs = (await a_client.get("/logs")).json()
    assert logs[0]["action"] == "kick" and logs[0]["target"] == "Spammer (777)"


async def test_ban_calls_gateway(a_client, a_channel, fake):
    assert (await a_client.post(f"/channels/{a_channel['id']}/members/777/ban")).status_code == 200
    assert ("ban", CHAT_ID, 777) in fake.calls


async def test_ban_floodwait_429(a_client, a_channel, fake):
    fake.fail_next["ban"] = TgFloodWait(30)
    r = await a_client.post(f"/channels/{a_channel['id']}/members/777/ban")
    assert r.status_code == 429 and r.json()["detail"] == "aguarde 30s"


async def test_ban_fatal_marks_dead_409(a_client, a_channel, fake, a_account):
    fake.fail_next["ban"] = TgFatalAuth("SessionRevokedError")
    r = await a_client.post(f"/channels/{a_channel['id']}/members/777/ban")
    assert r.status_code == 409
    accs = (await a_client.get("/accounts")).json()
    assert accs[0]["status"] == "dead"


async def test_failed_action_is_logged(a_client, a_channel, fake, sessionmaker):
    fake.fail_next["kick"] = TgFloodWait(30)
    await a_client.post(f"/channels/{a_channel['id']}/members/777/kick")
    logs = (await a_client.get("/logs")).json()
    assert logs[0]["result"] == "error"


async def test_logs_scoped_by_owner(a_client, b_client, a_channel, fake):
    await a_client.post(f"/channels/{a_channel['id']}/members/777/kick")
    assert len((await a_client.get("/logs")).json()) == 1
    assert (await b_client.get("/logs")).json() == []


async def test_logs_filter_and_pagination(a_client, a_channel, fake, sessionmaker, partner_a):
    for i in range(5):
        await a_client.post(f"/channels/{a_channel['id']}/members/{800 + i}/kick")
    page1 = (await a_client.get("/logs?limit=2")).json()
    page2 = (await a_client.get(f"/logs?limit=2&before_id={page1[-1]['id']}")).json()
    assert len(page1) == 2 and len(page2) == 2 and page2[0]["id"] < page1[-1]["id"]
    other = await make_account(sessionmaker, partner_a, phone="+66")
    assert (await a_client.get(f"/logs?account_id={other.id}")).json() == []
    assert ActionLog  # imported for clarity
