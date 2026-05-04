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


# --- parse_qual_callback ---


def test_parse_qual_callback_valid():
    """parse_qual_callback returns tuple for valid qual callback."""
    from telegram_bot.handlers.handoff import parse_qual_callback

    result = parse_qual_callback("qual:goal:search")
    assert result == ("goal", "search")


def test_parse_qual_callback_invalid_format():
    """parse_qual_callback returns None for wrong segment count."""
    from telegram_bot.handlers.handoff import parse_qual_callback

    result = parse_qual_callback("qual:goal")
    assert result is None


def test_parse_qual_callback_wrong_prefix():
    """parse_qual_callback returns None for non-qual prefix."""
    from telegram_bot.handlers.handoff import parse_qual_callback

    result = parse_qual_callback("other:goal:search")
    assert result is None


# --- start_qualification ---


@pytest.mark.asyncio
async def test_start_qualification_active_fsm_guard():
    """start_qualification returns early when FSM state is already active."""
    from telegram_bot.handlers.handoff import HandoffStates, start_qualification

    state = AsyncMock()
    state.get_state = AsyncMock(return_value=HandoffStates.active)

    message = AsyncMock(spec=["answer"])
    message.answer = AsyncMock()

    await start_qualification(message, state=state)

    message.answer.assert_awaited_once_with("Вы уже на связи с менеджером, ожидайте ответа 💬")


@pytest.mark.asyncio
async def test_start_qualification_with_goal():
    """start_qualification starts HandoffSG.contact when goal is provided."""
    from telegram_bot.handlers.handoff import start_qualification

    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)

    dialog_manager = AsyncMock()

    message = MagicMock()

    await start_qualification(message, state=state, dialog_manager=dialog_manager, goal="services")

    dialog_manager.start.assert_awaited_once()
    call_args = dialog_manager.start.call_args
    assert call_args.kwargs["data"] == {"goal": "services"}


@pytest.mark.asyncio
async def test_start_qualification_without_goal():
    """start_qualification starts HandoffSG.goal when no goal is provided."""
    from telegram_bot.dialogs.states import HandoffSG
    from telegram_bot.handlers.handoff import start_qualification

    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)

    dialog_manager = AsyncMock()

    message = MagicMock()

    await start_qualification(message, state=state, dialog_manager=dialog_manager)

    dialog_manager.start.assert_awaited_once()
    call_args = dialog_manager.start.call_args
    assert call_args.args[0] is HandoffSG.goal


@pytest.mark.asyncio
async def test_start_qualification_fallback_without_dialog_manager():
    """start_qualification sends plain text when dialog_manager is None."""
    from telegram_bot.handlers.handoff import start_qualification

    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)

    message = AsyncMock(spec=["answer"])
    message.answer = AsyncMock()

    await start_qualification(message, state=state, dialog_manager=None)

    message.answer.assert_awaited_once_with("📋 Какая тема вас интересует?")
