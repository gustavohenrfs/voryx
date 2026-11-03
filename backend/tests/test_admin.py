async def test_partner_cannot_access_admin(a_client):
    assert (await a_client.get("/admin/users")).status_code == 403


async def test_admin_creates_partner_who_can_login(admin_client, client):
    r = await admin_client.post("/admin/users", json={"email": "c@voryx.pro", "name": "C", "password": "longpass1"})
    assert r.status_code == 201 and r.json()["role"] == "partner"
    r = await client.post(
        "/auth/login", json={"email": "c@voryx.pro", "password": "longpass1"}, headers={"X-Voryx-CSRF": "1"}
    )
    assert r.status_code == 200


async def test_duplicate_email_409(admin_client, partner_a):
    r = await admin_client.post("/admin/users", json={"email": partner_a.email, "name": "x", "password": "longpass1"})
    assert r.status_code == 409


async def test_disabled_user_rejected(admin_client, a_client, partner_a):
    assert (await a_client.get("/auth/me")).status_code == 200
    r = await admin_client.patch(f"/admin/users/{partner_a.id}", json={"disabled": True})
    assert r.status_code == 200
    assert (await a_client.get("/auth/me")).status_code == 401


async def test_password_change_invalidates_sessions(admin_client, a_client, partner_a):
    await admin_client.patch(f"/admin/users/{partner_a.id}", json={"password": "newpass123"})
    assert (await a_client.get("/auth/me")).status_code == 401


async def test_password_hash_not_returned(admin_client, partner_a):
    r = await admin_client.get("/admin/users")
    assert r.status_code == 200 and len(r.json()) == 2
    assert "password_hash" not in r.text and "argon2" not in r.text
