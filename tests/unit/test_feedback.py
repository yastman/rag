"""Tests for user feedback utilities (#229)."""


class TestBuildFeedbackKeyboard:
    def test_returns_inline_keyboard_markup(self):
        from telegram_bot.feedback import build_feedback_keyboard

        kb = build_feedback_keyboard("abc123def456")
        assert len(kb.inline_keyboard) == 1
        assert len(kb.inline_keyboard[0]) == 2

    def test_button_callback_data_format(self):
        from telegram_bot.callback_data import FeedbackCB
        from telegram_bot.feedback import build_feedback_keyboard

        kb = build_feedback_keyboard("abc123def456")
        like_btn, dislike_btn = kb.inline_keyboard[0]
        assert like_btn.callback_data == FeedbackCB(action="like", trace_id="abc123def456").pack()
        assert (
            dislike_btn.callback_data
            == FeedbackCB(action="dislike", trace_id="abc123def456").pack()
        )

    def test_button_labels(self):
        from telegram_bot.feedback import build_feedback_keyboard

        kb = build_feedback_keyboard("abc123def456")
        like_btn, dislike_btn = kb.inline_keyboard[0]
        assert "Полезно" in like_btn.text
        assert "Не помогло" in dislike_btn.text

    def test_callback_data_within_64_bytes(self):
        from telegram_bot.feedback import build_feedback_keyboard

        trace_id = "a" * 32  # max W3C Trace Context
        kb = build_feedback_keyboard(trace_id)
        for btn in kb.inline_keyboard[0]:
            assert len(btn.callback_data.encode()) <= 64


class TestParseFeedbackCallback:
    def test_parses_like(self):
        from telegram_bot.feedback import parse_feedback_callback

        assert parse_feedback_callback("fb:1:abc123def456") == (1.0, "abc123def456", None)

    def test_parses_dislike(self):
        from telegram_bot.feedback import parse_feedback_callback

        assert parse_feedback_callback("fb:0:abc123def456") == (0.0, "abc123def456", None)

    def test_invalid_prefix_returns_none(self):
        from telegram_bot.feedback import parse_feedback_callback

        assert parse_feedback_callback("other:data") is None

    def test_invalid_value_returns_none(self):
        from telegram_bot.feedback import parse_feedback_callback

        assert parse_feedback_callback("fb:x:abc123") is None

    def test_missing_trace_id_returns_none(self):
        from telegram_bot.feedback import parse_feedback_callback

        assert parse_feedback_callback("fb:1:") is None


class TestBuildFeedbackConfirmation:
    def test_like_confirmation(self):
        from telegram_bot.feedback import build_feedback_confirmation

        kb = build_feedback_confirmation(liked=True)
        assert len(kb.inline_keyboard) == 1
        btn = kb.inline_keyboard[0][0]
        assert "Спасибо" in btn.text

    def test_dislike_confirmation(self):
        from telegram_bot.feedback import build_feedback_confirmation

        kb = build_feedback_confirmation(liked=False)
        btn = kb.inline_keyboard[0][0]
        assert "Спасибо" in btn.text
