from tests.conftest import CSRF


async def test_login_sets_cookie_and_me(client, admin_user):
    r = await client.post("/auth/login", json={"email": "admin@voryx.pro", "password": "secret123"}, headers=CSRF)
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    set_cookie = r.headers["set-cookie"].lower()
    assert "voryx_session=" in set_cookie and "httponly" in set_cookie and "samesite=lax" in set_cookie
    me = await client.get("/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "admin@voryx.pro"


async def test_me_without_cookie_401(client):
    assert (await client.get("/auth/me")).status_code == 401


async def test_login_wrong_password_401(client, admin_user):
    r = await client.post("/auth/login", json={"email": "admin@voryx.pro", "password": "nope"}, headers=CSRF)
    assert r.status_code == 401
    assert r.json()["detail"] == "email ou senha inválidos"


async def test_login_unknown_email_same_message(client):
    r = await client.post("/auth/login", json={"email": "x@x.com", "password": "nope"}, headers=CSRF)
    assert r.status_code == 401 and r.json()["detail"] == "email ou senha inválidos"


async def test_login_rate_limited(client, admin_user):
    for _ in range(10):
        r = await client.post("/auth/login", json={"email": "admin@voryx.pro", "password": "x"}, headers=CSRF)
        assert r.status_code == 401
    r = await client.post("/auth/login", json={"email": "admin@voryx.pro", "password": "secret123"}, headers=CSRF)
    assert r.status_code == 429


async def test_write_without_csrf_header_403(client, admin_user):
    r = await client.post("/auth/login", json={"email": "admin@voryx.pro", "password": "secret123"})
    assert r.status_code == 403


async def test_logout_clears_session(admin_client):
    assert (await admin_client.post("/auth/logout")).status_code == 200
    admin_client.cookies.clear()
    assert (await admin_client.get("/auth/me")).status_code == 401


async def test_tampered_cookie_401(client, admin_user):
    client.cookies.set("voryx_session", "1.0.forged")
    assert (await client.get("/auth/me")).status_code == 401
