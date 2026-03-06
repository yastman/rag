"""Telegram Mini App initData HMAC-SHA256 validation."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs


def validate_init_data(
    raw: str,
    bot_token: str,
    max_age: int = 86400,
) -> dict:
    """Validate Telegram WebApp initData and return parsed user data.

    Raises ValueError on invalid hash or expired data.
    """
    parsed = parse_qs(raw, keep_blank_values=True)
    params = {k: v[0] for k, v in parsed.items()}

    received_hash = params.pop("hash", None)
    if not received_hash:
        msg = "Invalid initData: missing hash"
        raise ValueError(msg)

    auth_date = int(params.get("auth_date", "0"))
    if max_age and (time.time() - auth_date) > max_age:
        msg = "initData expired"
        raise ValueError(msg)

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))

    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, received_hash):
        msg = "Invalid initData: hash mismatch"
        raise ValueError(msg)

    result = dict(params)
    if "user" in result:
        result["user"] = json.loads(result["user"])
    return result
