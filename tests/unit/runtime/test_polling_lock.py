"""Tests for src/runtime/integrations/polling_lock.py — machine guarantee for #2189.

Replacing the deleted check_bot_runtime_env.py preflight probe (#3099):
PollingLockBusy must carry owner + pttl in its message so operators get
actionable diagnostics without the preflight script.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.runtime.integrations.polling_lock import PollingLockBusy, RedisPollingLock


def test_polling_lock_busy_message_diagnostics() -> None:
    """PollingLockBusy message must contain both owner and pttl."""
    exc = PollingLockBusy(
        "Polling lock busy key='telegram-bot:polling'"
        " owner='host:456'"
        " pttl_ms=70000"
        " ttl_sec=None;"
        " stop the other bot instance first"
    )
    msg = str(exc)
    assert "owner=" in msg, "message must include owner field"
    assert "pttl" in msg, "message must include pttl field"
    assert "host:456" in msg
    assert "70000" in msg


@pytest.mark.asyncio
async def test_acquire_raises_with_owner_and_pttl_in_message() -> None:
    """RedisPollingLock.acquire raises PollingLockBusy with owner + pttl_ms."""
    backend_lock = MagicMock()
    backend_lock.acquire = AsyncMock(return_value=False)
    redis = MagicMock()
    redis.lock.return_value = backend_lock
    redis.get = AsyncMock(return_value=b"host:456")
    redis.pttl = AsyncMock(return_value=70000)

    lock = RedisPollingLock(redis=redis, key="telegram-bot:polling", ttl_sec=90)

    with pytest.raises(PollingLockBusy) as exc_info:
        await lock.acquire(owner="host:123")

    msg = str(exc_info.value)
    assert "owner=" in msg
    assert "pttl" in msg
    assert "host:456" in msg
    assert "70000" in msg
