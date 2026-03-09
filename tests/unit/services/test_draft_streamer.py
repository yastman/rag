from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_draft_streamer_sends_drafts():
    """DraftStreamer should call send_message_draft for each chunk."""
    from telegram_bot.services.draft_streamer import DraftStreamer

    bot = AsyncMock()
    streamer = DraftStreamer(bot=bot, chat_id=123, thread_id=42)

    await streamer.send_chunk("Hello ")
    await streamer.send_chunk("Hello world")

    assert bot.send_message_draft.call_count == 2
    # Verify thread_id is passed
    for call in bot.send_message_draft.call_args_list:
        assert call.kwargs["message_thread_id"] == 42
        assert call.kwargs["chat_id"] == 123


@pytest.mark.asyncio
async def test_draft_streamer_finalize():
    """finalize() should send final message and not draft."""
    from telegram_bot.services.draft_streamer import DraftStreamer

    bot = AsyncMock()
    streamer = DraftStreamer(bot=bot, chat_id=123, thread_id=None)

    await streamer.send_chunk("Hello world")
    await streamer.finalize("Hello world", parse_mode="HTML")

    bot.send_message.assert_called_once()
    call_kwargs = bot.send_message.call_args.kwargs
    assert call_kwargs["text"] == "Hello world"
    assert call_kwargs["parse_mode"] == "HTML"
