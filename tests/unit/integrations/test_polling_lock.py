from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.integrations.polling_lock import PollingLockBusy, RedisPollingLock


@pytest.mark.asyncio
async def test_acquire_raises_when_lock_already_exists() -> None:
    backend_lock = MagicMock()
    backend_lock.acquire = AsyncMock(return_value=False)
    redis = MagicMock()
    redis.lock.return_value = backend_lock
    lock = RedisPollingLock(redis=redis, key="bot:polling", ttl_sec=90)

    with pytest.raises(PollingLockBusy):
        await lock.acquire(owner="host:123")

    redis.lock.assert_called_once_with(
        "bot:polling",
        timeout=90,
        blocking=False,
        thread_local=False,
    )
    backend_lock.acquire.assert_awaited_once_with(token="host:123")


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
