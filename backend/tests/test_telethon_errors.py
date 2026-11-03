import pytest
from telethon.errors import (
    AuthKeyUnregisteredError,
    ChannelPrivateError,
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionRevokedError,
    UserDeactivatedBanError,
)

from app.tg.telethon_gateway import map_telethon_error
from app.tg.types import (
    TgCodeExpired,
    TgFatalAuth,
    TgFloodWait,
    TgInvalidCode,
    TgInvalidPassword,
    TgPermanent,
    TgPhoneInvalid,
    TgTransient,
)


@pytest.mark.parametrize(
    "exc,expected",
    [
        (AuthKeyUnregisteredError(request=None), TgFatalAuth),
        (UserDeactivatedBanError(request=None), TgFatalAuth),
        (SessionRevokedError(request=None), TgFatalAuth),
        (FloodWaitError(request=None, capture=42), TgFloodWait),
        (PhoneCodeInvalidError(request=None), TgInvalidCode),
        (PhoneCodeExpiredError(request=None), TgCodeExpired),
        (PasswordHashInvalidError(request=None), TgInvalidPassword),
        (PhoneNumberInvalidError(request=None), TgPhoneInvalid),
        (ChannelPrivateError(request=None), TgPermanent),
        (ConnectionError(), TgTransient),
    ],
)
def test_map_telethon_error(exc, expected):
    err = map_telethon_error(exc)
    assert isinstance(err, expected)
    if expected is TgFloodWait:
        assert err.seconds == 42
    if expected is TgFatalAuth:
        assert err.reason == type(exc).__name__
