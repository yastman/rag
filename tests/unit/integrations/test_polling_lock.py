from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.integrations.polling_lock import PollingLockBusy, RedisPollingLock


@pytest.mark.asyncio
async def test_acquire_raises_when_lock_already_exists() -> None:
    backend_lock = MagicMock()
    backend_lock.acquire = AsyncMock(return_value=False)
    redis = MagicMock()
    redis.lock.return_value = backend_lock
    redis.get = AsyncMock(return_value=b"host:456")
    redis.pttl = AsyncMock(return_value=42000)
    lock = RedisPollingLock(redis=redis, key="bot:polling", ttl_sec=90)

    with pytest.raises(PollingLockBusy, match="owner='host:456'") as exc:
        await lock.acquire(owner="host:123")

    assert "key='bot:polling'" in str(exc.value)
    assert "pttl_ms=42000" in str(exc.value)

    redis.lock.assert_called_once_with(
        "bot:polling",
        timeout=90,
        blocking=False,
        thread_local=False,
    )
    backend_lock.acquire.assert_awaited_once_with(token="host:123")
    redis.get.assert_awaited_once_with("bot:polling")
    redis.pttl.assert_awaited_once_with("bot:polling")


@pytest.mark.asyncio
async def test_acquire_uses_ttl_when_pttl_unavailable() -> None:
    backend_lock = MagicMock()
    backend_lock.acquire = AsyncMock(return_value=False)
    redis = MagicMock()
    redis.lock.return_value = backend_lock
    redis.get = AsyncMock(return_value="host:999")
    redis.pttl = AsyncMock(return_value=None)
    redis.ttl = AsyncMock(return_value=77)
    lock = RedisPollingLock(redis=redis, key="bot:polling", ttl_sec=90)

    with pytest.raises(PollingLockBusy, match="ttl_sec=77"):
        await lock.acquire(owner="host:123")

    redis.ttl.assert_awaited_once_with("bot:polling")


@pytest.mark.asyncio
async def test_refresh_reacquires_owned_lock() -> None:
    backend_lock = MagicMock()
    backend_lock.acquire = AsyncMock(return_value=True)
    backend_lock.reacquire = AsyncMock(return_value=True)
    redis = MagicMock()
    redis.lock.return_value = backend_lock
    lock = RedisPollingLock(redis=redis, key="bot:polling", ttl_sec=90)

    await lock.acquire(owner="host:123")
    await lock.refresh()

    backend_lock.reacquire.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_release_deletes_only_owned_lock() -> None:
    backend_lock = MagicMock()
    backend_lock.acquire = AsyncMock(return_value=True)
    backend_lock.release = AsyncMock()
    redis = MagicMock()
    redis.lock.return_value = backend_lock
    lock = RedisPollingLock(redis=redis, key="bot:polling", ttl_sec=90)

    await lock.acquire(owner="host:123")
    await lock.release()

    backend_lock.release.assert_awaited_once_with()
