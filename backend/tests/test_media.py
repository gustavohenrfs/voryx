import os

from app.config import get_settings


async def test_upload_image(a_client, partner_a, settings_override):
    r = await a_client.post("/media", files={"file": ("foto.JPG", b"\xff\xd8\xff" + b"0" * 100, "image/jpeg")})
    assert r.status_code == 201
    body = r.json()
    assert body["mime"] == "image/jpeg" and body["size"] == 103
    folder = os.path.join(settings_override.media_dir, str(partner_a.id))
    files = os.listdir(folder)
    assert len(files) == 1 and files[0].endswith(".jpg")


async def test_upload_rejects_non_media_415(a_client):
    r = await a_client.post("/media", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415


async def test_upload_too_large_413_and_no_file_left(a_client, partner_a, monkeypatch, settings_override):
    monkeypatch.setenv("VORYX_MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    big = b"0" * (1024 * 1024 + 10)
    r = await a_client.post("/media", files={"file": ("v.mp4", big, "video/mp4")})
    assert r.status_code == 413 and r.json()["detail"] == "arquivo maior que 1 MB"
    folder = os.path.join(get_settings().media_dir, str(partner_a.id))
    assert not os.path.exists(folder) or os.listdir(folder) == []
