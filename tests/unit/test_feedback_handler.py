"""Tests for feedback callback_query handler (#229)."""

from __future__ import annotations

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
