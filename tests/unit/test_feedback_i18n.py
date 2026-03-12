"""Tests for i18n support in build_feedback_keyboard (#866)."""

from __future__ import annotations


class _MockI18n:
    def get(self, key: str, **kwargs):
        return {
            "feedback-useful": "👍 Helpful",
            "feedback-not-helpful": "👎 Not helpful",
        }.get(key, key)


class TestBuildFeedbackKeyboardI18n:
    def test_uses_i18n_labels_when_provided(self):
        """build_feedback_keyboard uses i18n keys when i18n is provided."""
        from telegram_bot.feedback import build_feedback_keyboard

        kb = build_feedback_keyboard("abc123", i18n=_MockI18n())
        like_btn, dislike_btn = kb.inline_keyboard[0]
        assert like_btn.text == "👍 Helpful"
        assert dislike_btn.text == "👎 Not helpful"

    def test_falls_back_without_i18n(self):
        """build_feedback_keyboard falls back to default text when no i18n."""
        from telegram_bot.feedback import build_feedback_keyboard

        kb = build_feedback_keyboard("abc123")
        like_btn, dislike_btn = kb.inline_keyboard[0]
        assert "Полезно" in like_btn.text
        assert "Не помогло" in dislike_btn.text

    def test_i18n_none_falls_back(self):
        """build_feedback_keyboard falls back when i18n=None."""
        from telegram_bot.feedback import build_feedback_keyboard

        kb = build_feedback_keyboard("abc123", i18n=None)
        like_btn, dislike_btn = kb.inline_keyboard[0]
        assert "Полезно" in like_btn.text
        assert "Не помогло" in dislike_btn.text
