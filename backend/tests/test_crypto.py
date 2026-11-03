import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.crypto import decrypt, encrypt


def test_roundtrip():
    tok = encrypt("1BVtsOK...session")
    assert tok != "1BVtsOK...session"
    assert decrypt(tok) == "1BVtsOK...session"


def test_wrong_key_fails(monkeypatch):
    tok = encrypt("x")
    monkeypatch.setenv("VORYX_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    with pytest.raises(InvalidToken):
        decrypt(tok)
