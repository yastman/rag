"""Tests for the polling-lock preflight guard (issue #2189).

The guard must detect an existing Redis polling lock BEFORE full bot
startup and report key, owner, PTTL, and remediation without deleting
the lock.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.preflight import check_polling_lock


@pytest.mark.asyncio
async def test_no_lock_returns_none() -> None:
    """When no polling lock exists, the guard returns None (no issue)."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    result = await check_polling_lock(redis)
    assert result is None


@pytest.mark.asyncio
async def test_lock_exists_returns_diagnostics() -> None:
    """When a polling lock exists, the guard returns diagnostics dict."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=b"WIN-HOST:12345")
    redis.pttl = AsyncMock(return_value=70000)
    result = await check_polling_lock(redis)
    assert result is not None
    assert result["key"] == "telegram-bot:polling"
    assert result["owner"] == "WIN-HOST:12345"
    assert result["pttl_ms"] == 70000


@pytest.mark.asyncio
async def test_lock_exists_with_no_expiry() -> None:
    """When the lock has no TTL (-1), diagnostics still returned."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=b"host:999")
    redis.pttl = AsyncMock(return_value=-1)
    result = await check_polling_lock(redis)
    assert result is not None
    assert result["pttl_ms"] == -1
    assert result["owner"] == "host:999"


@pytest.mark.asyncio
async def test_does_not_delete_lock() -> None:
    """The guard must NOT delete the lock automatically."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=b"host:123")
    redis.pttl = AsyncMock(return_value=50000)
    redis.delete = AsyncMock()
    await check_polling_lock(redis)
    redis.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_custom_key() -> None:
    """The guard accepts a custom key name."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=b"owner:1")
    redis.pttl = AsyncMock(return_value=1000)
    result = await check_polling_lock(redis, key="custom:lock")
    assert result is not None
    assert result["key"] == "custom:lock"
    redis.get.assert_awaited_once_with("custom:lock")
