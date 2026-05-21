"""Tests for handle_feedback (CallbackData + legacy paths) and handle_hitl_callback."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from telegram_bot.config import BotConfig


def _make_config(**overrides) -> BotConfig:
    defaults = dict(
        telegram_token="test-token",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        redis_url="redis://localhost:6379",
        rerank_provider="none",
    )
    defaults.update(overrides)
    return BotConfig(_env_file=None, **defaults)


def _create_bot(config: BotConfig | None = None):
    if config is None:
        config = _make_config()
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
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

    async def test_callback_data_like_writes_score(self):
        """FeedbackCB action='like' writes positive score to Langfuse."""
        bot = _create_bot()
        callback = _make_callback()

        callback_data = MagicMock()
        callback_data.action = "like"
        callback_data.trace_id = "trace123"

        mock_lf = MagicMock()

        from telegram_bot import bot as bot_module

        with patch.object(bot_module, "get_langfuse_client", return_value=mock_lf):
            await bot.handle_feedback(callback, callback_data=callback_data)

        callback.answer.assert_awaited_once_with("Спасибо за отзыв!")
        mock_lf.create_score.assert_called_once_with(
            trace_id="trace123",
            name="user_feedback",
            value=1.0,
            data_type="NUMERIC",
            comment="user_id:42",
            score_id="trace123-user_feedback",
        )

    async def test_legacy_fb_done_answers_and_returns(self):
        """Legacy 'fb:done' data answers and returns without score writing."""
        bot = _create_bot()
        callback = _make_callback(data="fb:done")

        from telegram_bot import bot as bot_module

        mock_lf = MagicMock()
        with patch.object(bot_module, "get_langfuse_client", return_value=mock_lf):
            await bot.handle_feedback(callback, callback_data=None)

        callback.answer.assert_awaited_once_with()
        mock_lf.create_score.assert_not_called()

    async def test_legacy_fb_like_writes_positive_score(self):
        """Legacy 'fb:1:traceid' writes positive score."""
        bot = _create_bot()
        callback = _make_callback(data="fb:1:trace123abc")

        mock_lf = MagicMock()

        from telegram_bot import bot as bot_module

        with patch.object(bot_module, "get_langfuse_client", return_value=mock_lf):
            await bot.handle_feedback(callback, callback_data=None)

        callback.answer.assert_awaited_once_with("Спасибо за отзыв!")
        mock_lf.create_score.assert_called_once_with(
            trace_id="trace123abc",
            name="user_feedback",
            value=1.0,
            data_type="NUMERIC",
            comment="user_id:42",
            score_id="trace123abc-user_feedback",
        )

    async def test_legacy_fb_dislike_no_reason_shows_keyboard(self):
        """Legacy 'fb:0:traceid' without reason shows reason keyboard."""
        bot = _create_bot()
        callback = _make_callback(data="fb:0:trace123abc")

        from telegram_bot import bot as bot_module

        mock_lf = MagicMock()
        with patch.object(bot_module, "get_langfuse_client", return_value=mock_lf):
            await bot.handle_feedback(callback, callback_data=None)

        # Score should NOT be written (shows reason keyboard instead)
        mock_lf.create_score.assert_not_called()
        callback.answer.assert_awaited_once_with()
        callback.message.edit_reply_markup.assert_awaited_once()
        markup = callback.message.edit_reply_markup.call_args.kwargs["reply_markup"]
        # Dislike reason keyboard has 3 rows of 2 buttons
        assert len(markup.inline_keyboard) == 3


# ---------------------------------------------------------------------------
# TestHandleHitlCallback
# ---------------------------------------------------------------------------


class TestHandleHitlCallback:
    """Tests for handle_hitl_callback (approve/cancel button handling)."""

    async def test_approve_answers_accepted(self):
        """hitl:approve answers 'Принято', removes keyboard, and invokes agent."""
        bot = _create_bot()
        callback = _make_callback(data="hitl:approve")

        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(
            return_value={"messages": [MagicMock(content="Approved action completed")]}
        )

        bot._resolve_user_role = AsyncMock(return_value="client")
        bot._agent_checkpointer = MagicMock()

        with (
            patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.create_callback_handler", return_value=None),
        ):
            mock_prop.return_value.__enter__ = MagicMock(return_value=None)
            mock_prop.return_value.__exit__ = MagicMock(return_value=False)
            mock_lf = MagicMock()
            mock_get_client.return_value = mock_lf

            await bot.handle_hitl_callback(callback)

        callback.answer.assert_awaited_once_with("Принято")
        callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        mock_agent.ainvoke.assert_awaited_once()

    async def test_cancel_answers_cancelled(self):
        """hitl:cancel answers 'Отменено', removes keyboard, and invokes agent."""
        bot = _create_bot()
        callback = _make_callback(data="hitl:cancel")

        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(
            return_value={"messages": [MagicMock(content="Cancelled")]}
        )

        bot._resolve_user_role = AsyncMock(return_value="client")
        bot._agent_checkpointer = MagicMock()

        with (
            patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.create_callback_handler", return_value=None),
        ):
            mock_prop.return_value.__enter__ = MagicMock(return_value=None)
            mock_prop.return_value.__exit__ = MagicMock(return_value=False)
            mock_lf = MagicMock()
            mock_get_client.return_value = mock_lf

            await bot.handle_hitl_callback(callback)

        callback.answer.assert_awaited_once_with("Отменено")
        callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        mock_agent.ainvoke.assert_awaited_once()

    async def test_missing_from_user_answers_and_returns(self):
        """Missing from_user gracefully answers callback without error."""
        bot = _create_bot()
        callback = _make_callback(data="hitl:approve")
        callback.from_user = None

        await bot.handle_hitl_callback(callback)

        callback.answer.assert_awaited_once_with()

    async def test_missing_message_answers_and_returns(self):
        """Missing message gracefully answers callback without error."""
        bot = _create_bot()
        callback = _make_callback(data="hitl:approve")
        callback.message = None

        await bot.handle_hitl_callback(callback)

        callback.answer.assert_awaited_once_with()
