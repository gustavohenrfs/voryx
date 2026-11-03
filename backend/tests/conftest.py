import os

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import Base, make_engine, make_sessionmaker


@pytest.fixture(autouse=True)
def settings_override(monkeypatch, tmp_path):
    monkeypatch.setenv("VORYX_DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite://"))
    monkeypatch.setenv("VORYX_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VORYX_SECRET_KEY", "test-secret")
    monkeypatch.setenv("VORYX_COOKIE_SECURE", "false")
    monkeypatch.setenv("VORYX_START_BACKGROUND", "false")
    monkeypatch.setenv("VORYX_MEDIA_DIR", str(tmp_path / "media"))
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
async def engine(settings_override):
    url = settings_override.database_url
    kwargs = {"poolclass": StaticPool} if url.startswith("sqlite") else {}
    eng = make_engine(url, **kwargs)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def sessionmaker(engine):
    return make_sessionmaker(engine)


@pytest.fixture
async def session(sessionmaker):
    async with sessionmaker() as s:
        yield s
