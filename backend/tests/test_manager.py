import pytest

from app.models import AccountStatus, TgAccount
from app.tg.manager import AccountUnavailable
from app.tg.types import TgFatalAuth, TgTransient
from tests.conftest import make_account, reload


@pytest.fixture
async def account(sessionmaker, partner_a):
    return await make_account(sessionmaker, partner_a)


async def test_start_all_connects_and_marks_online(manager, fake, sessionmaker, partner_a):
    acc = await make_account(sessionmaker, partner_a, status=AccountStatus.OFFLINE)
    await manager.start_all()
    assert manager.get(acc.id) is not None
    assert (await reload(sessionmaker, TgAccount, acc.id)).status == AccountStatus.ONLINE


async def test_start_all_skips_dead(manager, fake, sessionmaker, partner_a):
    dead = await make_account(sessionmaker, partner_a, phone="+9", status=AccountStatus.DEAD)
    await manager.start_all()
    assert ("connect", "fake-session-+9") not in fake.calls
    with pytest.raises(AccountUnavailable):
        manager.get(dead.id)


async def test_fatal_marks_dead_and_never_retries(manager, fake, sessionmaker, account):
    await manager.start_all()
    fake.fail_next["get_me"] = TgFatalAuth("AuthKeyUnregisteredError")
    assert await manager.check(account.id) == AccountStatus.DEAD
    await manager.check_all()
    await manager.check_all()
    assert fake.calls.count(("get_me", "fake-session-+5511900000001")) == 1
    assert fake.calls.count(("connect", "fake-session-+5511900000001")) == 1
    acc = await reload(sessionmaker, TgAccount, account.id)
    assert acc.status == AccountStatus.DEAD and acc.dead_reason == "AuthKeyUnregisteredError"
    with pytest.raises(AccountUnavailable):
        manager.get(account.id)


async def test_fatal_on_connect_marks_dead(manager, fake, sessionmaker, partner_a):
    acc = await make_account(sessionmaker, partner_a, phone="+7")
    fake.dead_sessions.add("fake-session-+7")
    await manager.start_all()
    assert (await reload(sessionmaker, TgAccount, acc.id)).status == AccountStatus.DEAD


async def test_transient_marks_offline_then_recovers(manager, fake, sessionmaker, account):
    await manager.start_all()
    fake.fail_next["get_me"] = TgTransient("network down")
    assert await manager.check(account.id) == AccountStatus.OFFLINE
    assert (await reload(sessionmaker, TgAccount, account.id)).status == AccountStatus.OFFLINE
    assert await manager.check(account.id) == AccountStatus.ONLINE
    acc = await reload(sessionmaker, TgAccount, account.id)
    assert acc.status == AccountStatus.ONLINE and acc.last_seen_at is not None


async def test_transient_on_connect_retries_next_cycle(manager, fake, sessionmaker, account):
    fake.fail_next["connect"] = TgTransient("dns")
    await manager.start_all()
    assert (await reload(sessionmaker, TgAccount, account.id)).status == AccountStatus.OFFLINE
    assert await manager.check(account.id) == AccountStatus.ONLINE
    assert manager.get(account.id) is not None


async def test_mark_dead_disconnects(manager, fake, sessionmaker, account):
    await manager.start_all()
    await manager.mark_dead(account.id, "UserDeactivatedBanError")
    assert ("disconnect", "fake-session-+5511900000001") in fake.calls
    assert (await reload(sessionmaker, TgAccount, account.id)).dead_reason == "UserDeactivatedBanError"


async def test_lock_is_per_account(manager):
    assert manager.lock(1) is manager.lock(1)
    assert manager.lock(1) is not manager.lock(2)
