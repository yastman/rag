"""Verify that topic creation and reverse lookup share the same key space.

The TopicManager uses chat_id-based keys.  The reverse lookup in handle_query
must also use chat_id so it can find entries written by TopicManager.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.crm.topic_manager import TopicManager


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
def mock_bot():
    bot = AsyncMock()
    bot.create_forum_topic = AsyncMock(return_value=MagicMock(message_thread_id=42))
    return bot


@pytest.mark.asyncio
async def test_create_then_reverse_lookup_uses_chat_id_keyspace(mock_bot, mock_redis):
    """Data written by get_or_create_topic must be readable by get_expert_for_topic
    using the same chat_id — both operations use the chat_id key space."""
    manager = TopicManager(bot=mock_bot, redis=mock_redis)
    chat_id = 999

    await manager.get_or_create_topic(
        chat_id=chat_id,
        expert_id="consultant",
        expert_name="Консультант",
        expert_emoji="👷",
    )

    # Reverse lookup must use chat_id (not user_id) to find the stored expert
    result = await manager.get_expert_for_topic(chat_id=chat_id, topic_id=42)
    assert result == "consultant", (
        "get_expert_for_topic must use the same chat_id key space as get_or_create_topic"
    )


@pytest.mark.asyncio
async def test_topic_manager_keys_use_chat_id_prefix(mock_bot, mock_redis):
    """TopicManager keys must be prefixed with 'topic:{chat_id}', not 'topics:{user_id}'."""
    manager = TopicManager(bot=mock_bot, redis=mock_redis)

    await manager.get_or_create_topic(
        chat_id=111,
        expert_id="investor",
        expert_name="Инвестор",
        expert_emoji="💼",
    )

    set_calls = [call.args[0] for call in mock_redis.set.call_args_list]
    # Forward key must use chat_id-based prefix
    assert any(k.startswith("topic:111:") for k in set_calls), (
        f"Expected forward key 'topic:111:...', got keys: {set_calls}"
    )
    # Reverse key must use chat_id-based prefix
    assert any(k.startswith("topic_rev:111:") for k in set_calls), (
        f"Expected reverse key 'topic_rev:111:...', got keys: {set_calls}"
    )
    # Must NOT use the old TopicService 'topics:{user_id}' key space
    assert not any(k.startswith("topics:") for k in set_calls), (
        f"Keys must not use old 'topics:' prefix: {set_calls}"
    )
