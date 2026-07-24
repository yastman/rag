"""Tests for handle_feedback (CallbackData + legacy paths) and handle_hitl_callback."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.config import BotConfig
from tests.unit._bot_config_factory import make_bot_config as _make_config


def _create_bot(config: BotConfig | None = None):
    if config is None:
        config = _make_config()
    with (
        patch("telegram_bot.bot.Bot"),
        patch("src.runtime.integrations.cache.CacheLayerManager"),
        patch("src.runtime.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("src.runtime.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("src.runtime.services.qdrant.QdrantService"),
        patch("src.runtime.graph.config.GraphConfig.create_llm"),
        patch("src.runtime.graph.config.GraphConfig.create_supervisor_llm"),
    ):
        from telegram_bot.bot import PropertyBot

        return PropertyBot(config)


def _make_callback(data="fb:done"):
    callback = MagicMock()
    callback.data = data
    callback.from_user = MagicMock(id=42)
    callback.message = MagicMock()
    callback.message.chat = MagicMock(id=100)
    callback.message.bot = MagicMock()
    callback.message.bot.send_message = AsyncMock()
    callback.message.edit_reply_markup = AsyncMock()
    callback.answer = AsyncMock()
    return callback


# ---------------------------------------------------------------------------
# TestHandleFeedback
# ---------------------------------------------------------------------------


class TestHandleFeedback:
    """Tests for handle_feedback with CallbackData and legacy string paths."""

    async def test_callback_data_done_answers_and_returns(self):
        """FeedbackCB action='done' answers callback and returns immediately."""
        bot = _create_bot()
        callback = _make_callback()

        callback_data = MagicMock()
        callback_data.action = "done"
        callback_data.trace_id = ""

        await bot.handle_feedback(callback, callback_data=callback_data)

        callback.answer.assert_awaited_once_with()

    async def test_callback_data_dislike_shows_reason_keyboard(self):
        """FeedbackCB action='dislike' shows the reason keyboard."""
        bot = _create_bot()
        callback = _make_callback()

        callback_data = MagicMock()
        callback_data.action = "dislike"
        callback_data.trace_id = "trace123"

        await bot.handle_feedback(callback, callback_data=callback_data)

        callback.answer.assert_awaited_once_with()
        callback.message.edit_reply_markup.assert_awaited_once()
        # Verify the keyboard passed is a dislike reason keyboard (3 rows)
        markup = callback.message.edit_reply_markup.call_args.kwargs["reply_markup"]
        assert len(markup.inline_keyboard) == 3

    async def test_callback_data_like_answers_and_confirms(self):
        """FeedbackCB action='like' answers thanks and shows confirmation keyboard."""
        bot = _create_bot()
        callback = _make_callback()

        callback_data = MagicMock()
        callback_data.action = "like"
        callback_data.trace_id = "trace123"

        await bot.handle_feedback(callback, callback_data=callback_data)

        callback.answer.assert_awaited_once_with("Спасибо за отзыв!")
        callback.message.edit_reply_markup.assert_awaited_once()

    async def test_legacy_fb_done_answers_and_returns(self):
        """Legacy 'fb:done' data answers and returns without score writing."""
        bot = _create_bot()
        callback = _make_callback(data="fb:done")

        await bot.handle_feedback(callback, callback_data=None)

        callback.answer.assert_awaited_once_with()

    async def test_legacy_fb_dislike_no_reason_shows_keyboard(self):
        """Legacy 'fb:0:traceid' without reason shows reason keyboard."""
        bot = _create_bot()
        callback = _make_callback(data="fb:0:trace123abc")

        await bot.handle_feedback(callback, callback_data=None)

        callback.answer.assert_awaited_once_with()
        callback.message.edit_reply_markup.assert_awaited_once()
        markup = callback.message.edit_reply_markup.call_args.kwargs["reply_markup"]
        # Dislike reason keyboard has 3 rows of 2 buttons
        assert len(markup.inline_keyboard) == 3


# ---------------------------------------------------------------------------
# TestHandleHitlCallback
class TestHandleHitlCallback:
    """handle_hitl_callback is now a no-op stub that answers Устарело (#2843)."""

    @pytest.mark.asyncio
    async def test_handle_hitl_callback_answers_ustarelo(self) -> None:
        callback = AsyncMock()
        state = AsyncMock()
        bot = _create_bot()
        await bot.handle_hitl_callback(callback, state)
        callback.answer.assert_awaited_once_with("Устарело")
