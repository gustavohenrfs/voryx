import time
from collections import deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import get_settings

COOKIE_NAME = "voryx_session"
SESSION_MAX_AGE = 30 * 24 * 3600

_hasher = PasswordHasher()


def hash_password(pw: str) -> str:
    return _hasher.hash(pw)


def verify_password(hashed: str, pw: str) -> bool:
    try:
        return _hasher.verify(hashed, pw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="voryx-session")


def sign_session(user_id: int, version: int) -> str:
    return _serializer().dumps({"u": user_id, "v": version})


def read_session(token: str) -> tuple[int, int] | None:
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
        return int(data["u"]), int(data["v"])
    except (BadSignature, KeyError, TypeError, ValueError):
        return None


class LoginRateLimiter:
    """Counts failed logins per IP in a sliding window."""

    def __init__(self, max_failures: int = 10, window_s: int = 15 * 60, clock=time.monotonic):
        self.max_failures = max_failures
        self.window_s = window_s
        self.clock = clock
        self._fails: dict[str, deque[float]] = {}

    def _prune(self, ip: str) -> deque[float]:
        q = self._fails.setdefault(ip, deque())
        cutoff = self.clock() - self.window_s
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def check(self, ip: str) -> bool:
        return len(self._prune(ip)) < self.max_failures

    def fail(self, ip: str) -> None:
        self._prune(ip).append(self.clock())
