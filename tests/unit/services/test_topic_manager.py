"""Tests for TopicManager — expert topic lifecycle in private chats."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.topic_manager import TopicManager


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.create_forum_topic = AsyncMock(return_value=MagicMock(message_thread_id=42))
    bot.edit_forum_topic = AsyncMock()
    return bot


@pytest.fixture
def mock_redis():
    store: dict[str, str] = {}

    async def _get(key: str) -> str | None:
        return store.get(key)

    async def _set(key: str, value: int | str, ex: int | None = None) -> None:
        store[key] = str(value)

    async def _delete(*keys: str) -> None:
        for k in keys:
            store.pop(k, None)

    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=_get)
    redis.set = AsyncMock(side_effect=_set)
    redis.delete = AsyncMock(side_effect=_delete)
    return redis


@pytest.fixture
def manager(mock_bot, mock_redis):
    return TopicManager(bot=mock_bot, redis=mock_redis)


@pytest.mark.asyncio
async def test_create_new_topic(manager, mock_bot):
    topic_id = await manager.get_or_create_topic(
        chat_id=111,
        expert_id="consultant",
        expert_name="Консультант",
        expert_emoji="👷",
    )
    assert topic_id == 42
    mock_bot.create_forum_topic.assert_called_once_with(
        chat_id=111,
        name="👷 Консультант",
    )


@pytest.mark.asyncio
async def test_reuse_existing_topic(manager, mock_bot, mock_redis):
    # Первый вызов — создаёт
    await manager.get_or_create_topic(
        chat_id=111,
        expert_id="consultant",
        expert_name="Консультант",
        expert_emoji="👷",
    )
    mock_bot.create_forum_topic.reset_mock()

    # Второй вызов — переиспользует
    topic_id = await manager.get_or_create_topic(
        chat_id=111,
        expert_id="consultant",
        expert_name="Консультант",
        expert_emoji="👷",
    )
    assert topic_id == 42
    mock_bot.create_forum_topic.assert_not_called()


@pytest.mark.asyncio
async def test_reverse_lookup(manager):
    await manager.get_or_create_topic(
        chat_id=111,
        expert_id="consultant",
        expert_name="Консультант",
        expert_emoji="👷",
    )
    expert_id = await manager.get_expert_for_topic(chat_id=111, topic_id=42)
    assert expert_id == "consultant"


@pytest.mark.asyncio
async def test_reverse_lookup_unknown(manager):
    result = await manager.get_expert_for_topic(chat_id=111, topic_id=999)
    assert result is None


@pytest.mark.asyncio
async def test_rename_topic(manager, mock_bot):
    await manager.rename_topic(chat_id=111, topic_id=42, new_name="🏠 Двушка в Бургасе")
    mock_bot.edit_forum_topic.assert_called_once_with(
        chat_id=111,
        message_thread_id=42,
        name="🏠 Двушка в Бургасе",
    )


@pytest.mark.asyncio
async def test_rename_truncates_long_name(manager, mock_bot):
    long_name = "A" * 200
    await manager.rename_topic(chat_id=111, topic_id=42, new_name=long_name)
    call_name = mock_bot.edit_forum_topic.call_args.kwargs["name"]
    assert len(call_name) <= 128


@pytest.mark.asyncio
async def test_invalidate_topic(manager):
    await manager.get_or_create_topic(
        chat_id=111,
        expert_id="consultant",
        expert_name="Консультант",
        expert_emoji="👷",
    )
    await manager.invalidate_topic(chat_id=111, expert_id="consultant")
    result = await manager.get_expert_for_topic(chat_id=111, topic_id=42)
    assert result is None
