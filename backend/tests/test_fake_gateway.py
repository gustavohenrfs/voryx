import pytest

from app.tg.fake import FakeGateway
from app.tg.types import ChatRef, DialogInfo, TgFloodWait, TgInvalidCode, TgNeedPassword


async def test_fake_login_without_password():
    g = FakeGateway()
    h = await g.start_login("+5511", 1, "h")
    assert await h.submit_code("12345") == "fake-session-+5511"


async def test_fake_login_with_password():
    g = FakeGateway()
    g.require_password.add("+5511")
    h = await g.start_login("+5511", 1, "h")
    with pytest.raises(TgNeedPassword):
        await h.submit_code("12345")
    assert await h.submit_password("pw") == "fake-session-+5511"


async def test_fake_wrong_code():
    h = await FakeGateway().start_login("+1", 1, "h")
    with pytest.raises(TgInvalidCode):
        await h.submit_code("00000")


async def test_fake_client_records_calls_and_injects_failures():
    g = FakeGateway()
    g.dialogs = [DialogInfo(chat_id=10, access_hash=1, title="Prévias", username=None, kind="channel", member_count=5)]
    c = await g.connect("fake-session-+1", 1, "h")
    assert [d.title for d in await c.list_admin_dialogs()] == ["Prévias"]
    g.fail_next["kick"] = TgFloodWait(30)
    with pytest.raises(TgFloodWait):
        await c.kick(ChatRef(10, 1), 777)
    await c.kick(ChatRef(10, 1), 777)
    assert g.calls.count(("kick", 10, 777)) == 2
