from unittest.mock import AsyncMock, MagicMock

import pytest


def test_bot_bridge_singleton():
    """BotBridge should be accessible via get/set."""
    from mini_app.bot_bridge import BotBridge, get_bot_bridge, set_bot_bridge

    bridge = BotBridge(bot=MagicMock(), topic_service=MagicMock(), rag_fn=AsyncMock())
    set_bot_bridge(bridge)
    assert get_bot_bridge() is bridge


@pytest.mark.asyncio
async def test_ensure_topic_delegates_to_service():
    """ensure_topic should call topic_service.get_or_create_thread."""
    from mini_app.bot_bridge import BotBridge

    topic_svc = AsyncMock()
    topic_svc.get_or_create_thread.return_value = 42
    bot_mock = MagicMock()

    bridge = BotBridge(bot=bot_mock, topic_service=topic_svc, rag_fn=AsyncMock())
    result = await bridge.ensure_topic(
        chat_id=123,
        user_id=123,
        expert_id="consultant",
        topic_name="👷 Консультант",
    )
    assert result == 42
    topic_svc.get_or_create_thread.assert_called_once()
