"""Behavior tests for Telegram presentation formatting (single delivery path).

The supported bot path renders answers with ``format_answer_html`` and
``format_sources_html`` and delivers them with ``send_html_messages``.
These tests pin the Telegram-safe HTML output contract directly (#3341).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from telegram_bot.services.generation.telegram_formatting import (
    format_answer_html,
    format_sources_html,
    send_html_messages,
)


class TestFormatAnswerHtml:
    def test_escapes_unsafe_user_and_model_html(self):
        out = format_answer_html("<b>Привет</b> & <script>x</script>")
        assert out == "&lt;b&gt;Привет&lt;/b&gt; &amp; &lt;script&gt;x&lt;/script&gt;"

    def test_empty_text_renders_empty_string(self):
        assert format_answer_html("") == ""
        assert format_answer_html("   \n\t ") == ""

    def test_plain_paragraphs_preserved(self):
        text = "Первый абзац.\n\nВторой абзац."
        assert format_answer_html(text) == text

    def test_long_answer_wraps_details_in_expandable_blockquote(self):
        lead = [f"Абзац {i} " + "текст " * 130 for i in range(2)]
        tail = ["<тег> три", "хвост четыре"]
        out = format_answer_html("\n\n".join(lead + tail))
        assert out.startswith("\n\n".join(part.strip() for part in lead))
        assert "<blockquote expandable>" in out
        assert out.endswith("</blockquote>")
        assert "&lt;тег&gt; три" in out.split("<blockquote expandable>", 1)[1]


class TestFormatSourcesHtml:
    def test_no_documents_renders_empty_string(self):
        assert format_sources_html([]) == ""

    def test_renders_labels_and_escapes_unsafe_fields(self):
        docs = [
            {"metadata": {"title": "<Договор> & акт", "city": "<Казань>"}, "score": 0.87},
            {"metadata": {"title": "Инструкция"}, "score": "0.50"},
        ]
        out = format_sources_html(docs)
        assert out.startswith("\n\n📎 <b>Источники:</b>\n<blockquote>")
        assert "[1] &lt;Договор&gt; &amp; акт — &lt;Казань&gt; (рел: 0.87)" in out
        assert "[2] Инструкция (рел: 0.50)" in out
        assert "<blockquote expandable>" not in out
        assert out.endswith("</blockquote>")

    def test_caps_sources_at_max_and_expands_long_blocks(self):
        docs = [{"metadata": {"title": f"Документ {i}"}, "score": 0.1} for i in range(1, 9)]
        out = format_sources_html(docs, max_sources=3)
        assert "[3] Документ 3" in out
        assert "[4]" not in out
        assert "<blockquote expandable>" in out
        assert out.endswith("</blockquote>")


class TestSendHtmlMessages:
    async def test_sends_and_returns_true(self):
        message = MagicMock()
        message.answer = AsyncMock()
        result = await send_html_messages(message, "Hello")
        assert result is True

    async def test_empty_text_returns_false(self):
        message = MagicMock()
        result = await send_html_messages(message, "")
        assert result is False
