"""Tests for feedback callback_query handler (#229, #277)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.feedback import parse_feedback_callback


class TestParseFeedbackIntegration:
    async def test_parses_like_callback(self):
        parsed = parse_feedback_callback("fb:1:abc123def456789012345678901234")
        assert parsed is not None
        value, trace_id = parsed
        assert value == 1.0
        assert trace_id == "abc123def456789012345678901234"

    async def test_invalid_callback_ignored(self):
        assert parse_feedback_callback("not_feedback") is None

    async def test_done_callback_returns_none(self):
        assert parse_feedback_callback("fb:done") is None


class TestHandleFeedbackLangfuse:
    """Tests for handle_feedback writing scores via get_langfuse_client (#277)."""

    async def test_creates_score_with_idempotency_id(self):
        """get_langfuse_client().create_score() called with correct args including id."""
        mock_lf = MagicMock()
        callback = AsyncMock()
        callback.data = "fb:1:trace123abc"
        callback.from_user = MagicMock()
        callback.from_user.id = 42
        callback.message = AsyncMock()

        from telegram_bot import bot as bot_module
        from telegram_bot.bot import PropertyBot

        with patch.object(bot_module, "get_langfuse_client", return_value=mock_lf):
            bot_instance = MagicMock(spec=PropertyBot)
            bot_instance.handle_feedback = PropertyBot.handle_feedback.__get__(
                bot_instance, PropertyBot
            )
            await bot_instance.handle_feedback(callback)

        mock_lf.create_score.assert_called_once_with(
            trace_id="trace123abc",
            name="user_feedback",
            value=1.0,
            data_type="NUMERIC",
            comment="user_id:42",
            score_id="trace123abc-user_feedback",
        )
        mock_lf.flush.assert_not_called()
        callback.answer.assert_awaited_once_with("Спасибо за отзыв!")

    async def test_no_score_when_langfuse_disabled(self):
        """Feedback score NOT written when get_langfuse_client returns None."""
        callback = AsyncMock()
        callback.data = "fb:1:trace123abc"
        callback.from_user = MagicMock()
        callback.from_user.id = 42
        callback.message = AsyncMock()

        from telegram_bot import bot as bot_module
        from telegram_bot.bot import PropertyBot

        with patch.object(bot_module, "get_langfuse_client", return_value=None):
            bot_instance = MagicMock(spec=PropertyBot)
            bot_instance.handle_feedback = PropertyBot.handle_feedback.__get__(
                bot_instance, PropertyBot
            )
            await bot_instance.handle_feedback(callback)

        # Should complete without error — no create_score call
        callback.answer.assert_awaited_once_with("Спасибо за отзыв!")


class TestFeedbackConfirmationCleanup:
    async def test_clears_confirmation_markup_after_delay(self):
        from telegram_bot.bot import PropertyBot

        message = AsyncMock()
        bot = object.__new__(PropertyBot)

        with patch("telegram_bot.bot.asyncio.sleep", new=AsyncMock()) as mocked_sleep:
            await bot._clear_feedback_confirmation_later(message, delay_s=3.0)

        mocked_sleep.assert_awaited_once_with(3.0)
        message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
