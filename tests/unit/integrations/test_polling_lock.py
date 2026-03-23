from unittest.mock import AsyncMock

import pytest

from telegram_bot.integrations.polling_lock import PollingLockBusy, RedisPollingLock


@pytest.mark.asyncio
async def test_acquire_raises_when_lock_already_exists() -> None:
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=False)
    lock = RedisPollingLock(redis=redis, key="bot:polling", ttl_sec=90)

    with pytest.raises(PollingLockBusy):
        await lock.acquire(owner="host:123")


@pytest.mark.asyncio
async def test_release_deletes_only_owned_lock() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value="host:123")
    redis.delete = AsyncMock()
    lock = RedisPollingLock(redis=redis, key="bot:polling", ttl_sec=90)

    await lock.release(owner="host:123")

    redis.delete.assert_awaited_once_with("bot:polling")
