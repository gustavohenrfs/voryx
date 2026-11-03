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


# ---- app / http fixtures -------------------------------------------------
import httpx  # noqa: E402

from app.auth.security import hash_password  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Role, User  # noqa: E402

CSRF = {"X-Voryx-CSRF": "1"}


@pytest.fixture
def fake():
    try:
        from app.tg.fake import FakeGateway
    except ImportError:  # until the telegram layer exists
        return None
    return FakeGateway()


@pytest.fixture
async def app(engine, sessionmaker, fake):
    application = create_app(gateway=fake, start_background=False, sessionmaker=sessionmaker)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _make_user(sessionmaker, email, role, password="secret123"):
    async with sessionmaker() as s:
        u = User(email=email, password_hash=hash_password(password), role=role, name=email.split("@")[0])
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


@pytest.fixture
async def admin_user(sessionmaker):
    return await _make_user(sessionmaker, "admin@voryx.pro", Role.ADMIN)


@pytest.fixture
async def partner_a(sessionmaker):
    return await _make_user(sessionmaker, "a@voryx.pro", Role.PARTNER)


@pytest.fixture
async def partner_b(sessionmaker):
    return await _make_user(sessionmaker, "b@voryx.pro", Role.PARTNER)


@pytest.fixture
async def login_as(app):
    clients = []

    async def _login(user, password="secret123"):
        transport = httpx.ASGITransport(app=app)
        c = httpx.AsyncClient(transport=transport, base_url="http://test", headers=CSRF)
        r = await c.post("/auth/login", json={"email": user.email, "password": password})
        assert r.status_code == 200, r.text
        clients.append(c)
        return c

    yield _login
    for c in clients:
        await c.aclose()


@pytest.fixture
async def admin_client(login_as, admin_user):
    return await login_as(admin_user)


@pytest.fixture
async def a_client(login_as, partner_a):
    return await login_as(partner_a)


@pytest.fixture
async def b_client(login_as, partner_b):
    return await login_as(partner_b)
