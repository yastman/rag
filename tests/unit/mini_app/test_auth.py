"""Tests for Telegram Mini App HMAC-SHA256 initData validation."""

import hashlib
import hmac
import time
from urllib.parse import quote

import pytest

from mini_app.auth import validate_init_data


BOT_TOKEN = "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"


def _make_init_data(bot_token: str, **overrides: str) -> str:
    """Build valid Telegram initData string with correct hash."""
    params = {
        "auth_date": str(int(time.time())),
        "user": '{"id":123,"first_name":"Test"}',
        **overrides,
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    hash_val = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    params["hash"] = hash_val
    return "&".join(f"{k}={quote(v)}" for k, v in params.items())


def test_validate_valid_init_data():
    raw = _make_init_data(BOT_TOKEN)
    result = validate_init_data(raw, BOT_TOKEN)
    assert result["user"]["id"] == 123


def test_validate_invalid_hash():
    raw = _make_init_data(BOT_TOKEN)
    ***REMOVED*** Replace valid hash with an invalid one
    parts = dict(pair.split("=", 1) for pair in raw.split("&"))
    parts["hash"] = "deadbeef" * 8  ***REMOVED*** wrong 64-char hex string
    raw_invalid = "&".join(f"{k}={v}" for k, v in parts.items())
    with pytest.raises(ValueError, match="Invalid"):
        validate_init_data(raw_invalid, BOT_TOKEN)


def test_validate_expired_data():
    raw = _make_init_data(BOT_TOKEN, auth_date="1000000000")
    with pytest.raises(ValueError, match="expired"):
        validate_init_data(raw, BOT_TOKEN, max_age=60)


def test_validate_missing_hash():
    raw = "auth_date=9999999999&user=%7B%22id%22%3A123%7D"
    with pytest.raises(ValueError, match="Invalid"):
        validate_init_data(raw, BOT_TOKEN)


def test_validate_missing_auth_date():
    """SDK rejects payloads missing the required ``auth_date`` field.

    The ``WebAppInitData`` Pydantic model treats ``auth_date`` as required,
    so a payload that lacks it raises a validation error before the freshness
    check runs. Both the parse-error and the freshness-error paths surface
    the same conservative ``"Invalid initData"`` / ``"initData expired"``
    message to callers (***REMOVED***1595).
    """
    ***REMOVED*** Build valid initData without auth_date — the SDK refuses to construct
    ***REMOVED*** the WebAppInitData model and our wrapper translates that into "Invalid
    ***REMOVED*** initData" so 401s look the same regardless of which branch fired.
    params = {"user": '{"id":123,"first_name":"Test"}'}
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    hash_val = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    params["hash"] = hash_val
    raw = "&".join(f"{k}={quote(v)}" for k, v in params.items())
    with pytest.raises(ValueError, match="Invalid"):
        validate_init_data(raw, BOT_TOKEN, max_age=60)
