from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.forum_bridge import ForumBridge


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.create_forum_topic = AsyncMock(
        return_value=MagicMock(message_thread_id=42, name="Test Topic")
    )
    bot.send_message = AsyncMock()
    bot.copy_message = AsyncMock()
    bot.close_forum_topic = AsyncMock()
    return bot


@pytest.fixture
def bridge(mock_bot):
    return ForumBridge(bot=mock_bot, managers_group_id=-100123)


@pytest.mark.asyncio
async def test_create_topic(bridge, mock_bot):
    topic_id = await bridge.create_topic(client_name="Иван", goal="Покупка")
    assert topic_id == 42
    mock_bot.create_forum_topic.assert_called_once_with(
        chat_id=-100123,
        name="Иван — Покупка",
    )


@pytest.mark.asyncio
async def test_create_topic_truncates_long_name(bridge, mock_bot):
    long_name = "А" * 200
    await bridge.create_topic(client_name=long_name, goal="Покупка")
    call_args = mock_bot.create_forum_topic.call_args
    name = call_args.kwargs["name"]
    assert len(name.encode("utf-8")) <= 128


@pytest.mark.asyncio
async def test_post_context_pack(bridge, mock_bot):
    await bridge.post_context_pack(
        topic_id=42,
        client_name="Иван",
        username="ivan",
        locale="ru",
        qualification={"goal": "buy", "budget": "50-100"},
        summary="Искал квартиру в Варне",
        lead_url="https://kommo.com/leads/123",
    )
    mock_bot.send_message.assert_called_once()
    text = mock_bot.send_message.call_args.kwargs["text"]
    assert "Иван" in text
    assert "ivan" in text
    assert "Варне" in text
    assert "/close" in text


@pytest.mark.asyncio
async def test_post_context_pack_no_summary(bridge, mock_bot):
    await bridge.post_context_pack(
        topic_id=42,
        client_name="Иван",
        username=None,
        locale="en",
        qualification={"goal": "rent"},
        summary=None,
        lead_url=None,
    )
    text = mock_bot.send_message.call_args.kwargs["text"]
    assert "AI" not in text  # no summary block
    assert "/close" in text


@pytest.mark.asyncio
async def test_relay_to_topic(bridge, mock_bot):
    await bridge.relay_to_topic(from_chat_id=999, message_id=55, topic_id=42)
    mock_bot.copy_message.assert_called_once_with(
        chat_id=-100123,
        from_chat_id=999,
        message_id=55,
        message_thread_id=42,
    )


@pytest.mark.asyncio
async def test_relay_to_client(bridge, mock_bot):
    await bridge.relay_to_client(topic_id=42, message_id=77, client_chat_id=999)
    mock_bot.copy_message.assert_called_once_with(
        chat_id=999,
        from_chat_id=-100123,
        message_id=77,
    )


@pytest.mark.asyncio
async def test_close_topic(bridge, mock_bot):
    await bridge.close_topic(topic_id=42)
    mock_bot.close_forum_topic.assert_called_once_with(
        chat_id=-100123,
        message_thread_id=42,
    )
