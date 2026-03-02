"""Integration test: full handoff flow with mocked services."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.forum_bridge import ForumBridge
from telegram_bot.services.handoff_state import HandoffData, HandoffState


@pytest.mark.asyncio
async def test_full_handoff_flow(mock_redis):
    """Test: qualification → topic creation → relay → close."""
    # Setup
    state = HandoffState(mock_redis, ttl_hours=24)
    bot = AsyncMock()
    bot.create_forum_topic = AsyncMock(return_value=MagicMock(message_thread_id=42))
    bot.send_message = AsyncMock()
    bot.copy_message = AsyncMock()
    bot.close_forum_topic = AsyncMock()
    bridge = ForumBridge(bot=bot, managers_group_id=-100)

    # 1. Create topic + set state
    topic_id = await bridge.create_topic(client_name="Иван", goal="Покупка")
    data = HandoffData(
        client_id=999,
        topic_id=topic_id,
        mode="human_waiting",
        qualification={"goal": "buy", "budget": "mid"},
    )
    await state.set(data)

    # 2. Verify state
    stored = await state.get_by_client(999)
    assert stored.mode == "human_waiting"
    assert stored.topic_id == 42

    # 3. Relay client message to topic
    await bridge.relay_to_topic(from_chat_id=999, message_id=10, topic_id=42)
    bot.copy_message.assert_called()

    # 4. Manager joins — mode transition
    await state.update_mode(999, "human")
    stored = await state.get_by_client(999)
    assert stored.mode == "human"
    assert stored.manager_joined_at is not None

    # 5. Close handoff
    await bridge.close_topic(topic_id=42)
    await state.delete(999)
    assert await state.get_by_client(999) is None
    assert await state.get_by_topic(42) is None


@pytest.fixture
def mock_redis():
    import fakeredis.aioredis

    return fakeredis.aioredis.FakeRedis(decode_responses=True)
