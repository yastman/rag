"""Telegram Mini App initData validation.

SDK-audited (***REMOVED***1595, Context7 ``/aiogram/aiogram``): aiogram 3.x ships a
vetted WebApp validator at :mod:`aiogram.utils.web_app` that uses
``hmac.compare_digest`` for timing-attack protection. We delegate the
HMAC-SHA256 signature check + URL-encoded payload parsing to the SDK and
keep just the bits that aiogram does not own:

* a configurable ``auth_date`` freshness check (the SDK only validates
  the signature, not the payload age);
* a stable ``dict``-shaped public return so the existing
  :mod:`mini_app.api` callers and the unit tests remain wire-compatible.

Content was rephrased for compliance with licensing restrictions.
"""

from __future__ import annotations

import time
from typing import Any

from aiogram.utils.web_app import safe_parse_webapp_init_data


def validate_init_data(
    raw: str,
    bot_token: str,
    max_age: int = 86400,
) -> dict[str, Any]:
    """Validate Telegram WebApp initData and return parsed payload as a dict.

    Parameters
    ----------
    raw:
        Raw URL-encoded initData query string from
        ``Telegram.WebApp.initData``.
    bot_token:
        Telegram bot token (the same secret the bot uses to talk to the
        Bot API).  The SDK derives the WebApp HMAC secret from it.
    max_age:
        Maximum permissible age of the ``auth_date`` field, in seconds.
        Defaults to 24 h, matching the previous custom validator's
        envelope. Pass ``0`` to disable the freshness check.

    Returns
    -------
    dict
        Parsed initData with the same shape the previous custom
        validator emitted: ``{"user": {"id": ..., ...}, "auth_date":
        "<unix-seconds-as-str>", ...}``.

    Raises
    ------
    ValueError
        On any validation failure — missing/invalid signature, malformed
        payload, or expired ``auth_date``. The message stays conservative
        ("Invalid initData", "initData expired") so handlers can surface
        a 401 without leaking specifics.
    """
    try:
        webapp_data = safe_parse_webapp_init_data(token=bot_token, init_data=raw)
    except ValueError as exc:
        ***REMOVED*** SDK raises ValueError for both bad signature and malformed
        ***REMOVED*** payloads; treat both as "invalid" without leaking details.
        msg = "Invalid initData"
        raise ValueError(msg) from exc

    auth_dt = webapp_data.auth_date
    auth_ts = int(auth_dt.timestamp()) if hasattr(auth_dt, "timestamp") else int(auth_dt)
    if max_age and (time.time() - auth_ts) > max_age:
        msg = "initData expired"
        raise ValueError(msg)

    ***REMOVED*** Mirror the previous public shape so the existing callers and the
    ***REMOVED*** ``test_auth.py`` regression suite stay byte-compatible.
    result: dict[str, Any] = {"auth_date": str(auth_ts)}
    if webapp_data.user is not None:
        ***REMOVED*** ``WebAppUser`` is a Pydantic v2 model with optional fields;
        ***REMOVED*** ``model_dump(exclude_none=True)`` drops anything Telegram did
        ***REMOVED*** not send so the dict stays compact.
        result["user"] = webapp_data.user.model_dump(exclude_none=True)
    if webapp_data.query_id is not None:
        result["query_id"] = webapp_data.query_id
    if webapp_data.chat_instance is not None:
        result["chat_instance"] = webapp_data.chat_instance
    if webapp_data.chat_type is not None:
        result["chat_type"] = webapp_data.chat_type
    if webapp_data.start_param is not None:
        result["start_param"] = webapp_data.start_param
    return result
