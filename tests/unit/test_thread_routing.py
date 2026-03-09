"""Verify thread-aware routing resolves expert_id from message_thread_id."""

import pytest


@pytest.mark.asyncio
async def test_supervisor_thread_id_with_thread():
    """Thread ID should include message_thread_id when present."""
    from telegram_bot.bot import _supervisor_thread_id

    # Without thread
    assert _supervisor_thread_id(123) == "tg_123"

    # With thread
    assert _supervisor_thread_id(123, thread_id=42) == "tg_123:42"


@pytest.mark.asyncio
async def test_supervisor_thread_id_without_thread():
    """Thread ID stays tg_{chat_id} when no thread."""
    from telegram_bot.bot import _supervisor_thread_id

    assert _supervisor_thread_id(456) == "tg_456"
    assert _supervisor_thread_id(456, thread_id=None) == "tg_456"
