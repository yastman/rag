"""Tests for feedback callback_query handler (#229, #277, #755)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.feedback import parse_feedback_callback


class TestParseFeedbackIntegration:
    def test_parses_like_callback(self):
        parsed = parse_feedback_callback("fb:1:abc123def456789012345678901234")
        assert parsed is not None
        value, trace_id, reason = parsed
        assert value == 1.0
        assert trace_id == "abc123def456789012345678901234"
        assert reason is None

    def test_invalid_callback_ignored(self):
        assert parse_feedback_callback("not_feedback") is None

    def test_done_callback_returns_none(self):
        assert parse_feedback_callback("fb:done") is None


class TestBuildDislikeReasonKeyboard:
    """Tests for the 6-button dislike reason keyboard (#755)."""

    def test_returns_3_rows_of_2_buttons(self):
        from telegram_bot.feedback import build_dislike_reason_keyboard

        kb = build_dislike_reason_keyboard("trace123abc")
        assert len(kb.inline_keyboard) == 3
        for row in kb.inline_keyboard:
            assert len(row) == 2

    def test_callback_data_starts_with_fbr(self):
        from telegram_bot.feedback import build_dislike_reason_keyboard

        kb = build_dislike_reason_keyboard("trace123abc")
        for row in kb.inline_keyboard:
            for btn in row:
                assert btn.callback_data is not None
                assert btn.callback_data.startswith("fbr:")

    def test_all_6_reason_codes_present(self):
        from telegram_bot.feedback import build_dislike_reason_keyboard

        kb = build_dislike_reason_keyboard("trace123abc")
        codes = set()
        for row in kb.inline_keyboard:
            for btn in row:
                # format: fbr:{code}:{trace_id}
                parts = (btn.callback_data or "").split(":")
                codes.add(parts[1])
        assert codes == {"wt", "mi", "bs", "ha", "ic", "fm"}

    def test_trace_id_encoded_in_callback(self):
        from telegram_bot.feedback import build_dislike_reason_keyboard

        trace_id = "my_trace_xyz"
        kb = build_dislike_reason_keyboard(trace_id)
        for row in kb.inline_keyboard:
            for btn in row:
                assert trace_id in (btn.callback_data or "")

    def test_callback_within_64_bytes(self):
        from telegram_bot.feedback import build_dislike_reason_keyboard

        trace_id = "a" * 32  # max W3C Trace Context
        kb = build_dislike_reason_keyboard(trace_id)
        for row in kb.inline_keyboard:
            for btn in row:
                assert len((btn.callback_data or "").encode()) <= 64


class TestParseFeedbackCallbackReasonPath:
    """Tests for 3-tuple return and reason path parsing (#755)."""

    def test_like_returns_3_tuple_with_none_reason(self):
        from telegram_bot.feedback import parse_feedback_callback

        result = parse_feedback_callback("fb:1:abc123")
        assert result == (1.0, "abc123", None)

    def test_dislike_returns_3_tuple_with_none_reason(self):
        from telegram_bot.feedback import parse_feedback_callback

        result = parse_feedback_callback("fb:0:abc123")
        assert result == (0.0, "abc123", None)

    def test_parses_reason_wrong_topic(self):
        from telegram_bot.feedback import parse_feedback_callback

        result = parse_feedback_callback("fb:r:wt:abc123")
        assert result == (0.0, "abc123", "wrong_topic")

    def test_parses_reason_missing_info(self):
        from telegram_bot.feedback import parse_feedback_callback

        result = parse_feedback_callback("fb:r:mi:abc123")
        assert result == (0.0, "abc123", "missing_info")

    def test_parses_reason_bad_sources(self):
        from telegram_bot.feedback import parse_feedback_callback

        result = parse_feedback_callback("fb:r:bs:abc123")
        assert result == (0.0, "abc123", "bad_sources")

    def test_parses_reason_hallucination(self):
        from telegram_bot.feedback import parse_feedback_callback

        result = parse_feedback_callback("fb:r:ha:abc123")
        assert result == (0.0, "abc123", "hallucination")

    def test_parses_reason_incomplete(self):
        from telegram_bot.feedback import parse_feedback_callback

        result = parse_feedback_callback("fb:r:ic:abc123")
        assert result == (0.0, "abc123", "incomplete")

    def test_parses_reason_formatting(self):
        from telegram_bot.feedback import parse_feedback_callback

        result = parse_feedback_callback("fb:r:fm:abc123")
        assert result == (0.0, "abc123", "formatting")

    def test_invalid_reason_code_returns_none(self):
        from telegram_bot.feedback import parse_feedback_callback

        assert parse_feedback_callback("fb:r:xx:abc123") is None

    def test_missing_trace_in_reason_returns_none(self):
        from telegram_bot.feedback import parse_feedback_callback

        assert parse_feedback_callback("fb:r:wt:") is None

    def test_invalid_prefix_returns_none(self):
        from telegram_bot.feedback import parse_feedback_callback

        assert parse_feedback_callback("other:data") is None

    def test_invalid_value_returns_none(self):
        from telegram_bot.feedback import parse_feedback_callback

        assert parse_feedback_callback("fb:x:abc123") is None

    def test_missing_trace_id_returns_none(self):
        from telegram_bot.feedback import parse_feedback_callback

        assert parse_feedback_callback("fb:1:") is None


class TestHandleFeedback2Step:
    """Tests for the 2-step dislike flow (#755)."""

    async def test_dislike_shows_reason_keyboard(self):
        """fb:0:trace → show reason keyboard, no score written."""
        callback = AsyncMock()
        callback.data = "fb:0:trace123abc"
        callback.from_user = MagicMock()
        callback.from_user.id = 42
        callback.message = AsyncMock()

        from telegram_bot.bot import PropertyBot

        bot_instance = MagicMock(spec=PropertyBot)
        bot_instance.handle_feedback = PropertyBot.handle_feedback.__get__(
            bot_instance, PropertyBot
        )
        await bot_instance.handle_feedback(callback)

        callback.message.edit_reply_markup.assert_awaited_once()
        called_markup = callback.message.edit_reply_markup.call_args.kwargs["reply_markup"]
        # Reason keyboard: 3 rows x 2 buttons
        assert len(called_markup.inline_keyboard) == 3

    async def test_dislike_answers_callback(self):
        """fb:0:trace → callback.answer() is called."""
        callback = AsyncMock()
        callback.data = "fb:0:trace123abc"
        callback.from_user = MagicMock()
        callback.from_user.id = 42
        callback.message = AsyncMock()

        from telegram_bot.bot import PropertyBot

        bot_instance = MagicMock(spec=PropertyBot)
        bot_instance.handle_feedback = PropertyBot.handle_feedback.__get__(
            bot_instance, PropertyBot
        )
        await bot_instance.handle_feedback(callback)

        callback.answer.assert_awaited_once()

    async def test_reason_selected_shows_confirmation_keyboard(self):
        """fb:r:*:trace → edit_reply_markup with 1-button confirmation."""
        callback = AsyncMock()
        callback.data = "fb:r:fm:trace123abc"
        callback.from_user = MagicMock()
        callback.from_user.id = 42
        callback.message = AsyncMock()

        from telegram_bot.bot import PropertyBot

        bot_instance = MagicMock(spec=PropertyBot)
        bot_instance.handle_feedback = PropertyBot.handle_feedback.__get__(
            bot_instance, PropertyBot
        )
        await bot_instance.handle_feedback(callback)

        callback.message.edit_reply_markup.assert_awaited_once()
        called_markup = callback.message.edit_reply_markup.call_args.kwargs["reply_markup"]
        # Confirmation: 1 row x 1 button
        assert len(called_markup.inline_keyboard) == 1

    async def test_reason_selected_answers_thanks(self):
        """fb:r:*:trace → callback.answer called with thanks message."""
        callback = AsyncMock()
        callback.data = "fb:r:ic:trace123abc"
        callback.from_user = MagicMock()
        callback.from_user.id = 42
        callback.message = AsyncMock()

        from telegram_bot.bot import PropertyBot

        bot_instance = MagicMock(spec=PropertyBot)
        bot_instance.handle_feedback = PropertyBot.handle_feedback.__get__(
            bot_instance, PropertyBot
        )
        await bot_instance.handle_feedback(callback)

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

    async def test_suppresses_edit_exception(self):
        from telegram_bot.bot import PropertyBot

        message = AsyncMock()
        message.edit_reply_markup.side_effect = Exception("Telegram API error")
        bot = object.__new__(PropertyBot)

        with patch("telegram_bot.bot.asyncio.sleep", new=AsyncMock()):
            # Should not raise
            await bot._clear_feedback_confirmation_later(message, delay_s=1.0)
