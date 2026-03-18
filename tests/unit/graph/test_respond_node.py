"""Tests for respond_node — Telegram message sending with Markdown fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock

from telegram_bot.graph.nodes.respond import format_sources, respond_node
from telegram_bot.graph.state import make_initial_state


_SAMPLE_DOCS = [
    {
        "text": "Квартира в Несебре",
        "score": 0.92,
        "metadata": {"title": "Апартамент Несебр", "city": "Несебр", "price": 65000},
    },
    {
        "text": "Студия в Равде",
        "score": 0.87,
        "metadata": {"title": "Студия с видом", "city": "Равда", "price": 35000},
    },
]


class TestRespondNode:
    async def test_sends_html(self):
        message = AsyncMock()
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = "**Bold** answer"
        state["message"] = message

        result = await respond_node(state)

        message.answer.assert_awaited_once_with(
            "**Bold** answer", parse_mode="HTML", reply_markup=None
        )
        assert "respond" in result["latency_stages"]

    async def test_fallback_to_plain_text(self):
        message = AsyncMock()
        # First call (HTML) raises, second call (plain) succeeds
        message.answer.side_effect = [Exception("parse error"), None]
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = "bad *markdown"
        state["message"] = message

        result = await respond_node(state)

        assert message.answer.await_count == 2
        # Second call should be plain text (no parse_mode)
        message.answer.assert_awaited_with("bad *markdown", reply_markup=None)
        assert "respond" in result["latency_stages"]

    async def test_empty_response_gets_default(self):
        message = AsyncMock()
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = ""
        state["message"] = message

        await respond_node(state)

        sent_text = message.answer.call_args[0][0]
        assert "Извините" in sent_text

    async def test_no_message_object(self):
        """respond_node should not crash if message is not in state."""
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = "answer"
        # No "message" key in state

        result = await respond_node(state)

        assert "respond" in result["latency_stages"]

    async def test_preserves_existing_latency_stages(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = "ok"
        state["latency_stages"] = {"classify": 0.01}

        result = await respond_node(state)

        assert result["latency_stages"]["classify"] == 0.01
        assert "respond" in result["latency_stages"]

    async def test_skips_sending_when_response_sent(self):
        """respond_node skips message.answer when response_sent=True (streaming)."""
        message = AsyncMock()
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = "Already streamed"
        state["message"] = message
        state["response_sent"] = True

        result = await respond_node(state)

        message.answer.assert_not_called()
        assert "respond" in result["latency_stages"]


class TestRespondNodeSavesAssistantMessage:
    async def test_returns_assistant_message_in_messages(self):
        """respond_node adds assistant response to messages for checkpointer."""
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = "Ответ бота."
        state["response_sent"] = True

        result = await respond_node(state)

        assert "messages" in result
        msg = result["messages"][0]
        assert msg["role"] == "assistant"
        assert msg["content"] == "Ответ бота."

    async def test_assistant_message_with_default_response(self):
        """respond_node adds default message when response is empty."""
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = ""

        result = await respond_node(state)

        assert "messages" in result
        msg = result["messages"][0]
        assert msg["role"] == "assistant"
        assert "Извините" in msg["content"]


class TestRespondNodeFeedbackButtons:
    async def test_sends_with_feedback_keyboard(self):
        """respond_node attaches feedback buttons when trace_id present."""
        message = AsyncMock()
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = "Answer text"
        state["message"] = message
        state["trace_id"] = "abc123def456"

        await respond_node(state)

        call_kwargs = message.answer.call_args
        assert call_kwargs.kwargs.get("reply_markup") is not None

    async def test_no_buttons_when_trace_id_empty(self):
        """respond_node sends without buttons when trace_id is empty."""
        message = AsyncMock()
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = "Answer text"
        state["message"] = message
        # trace_id is "" by default

        await respond_node(state)

        call_kwargs = message.answer.call_args
        assert call_kwargs.kwargs.get("reply_markup") is None

    async def test_no_buttons_for_chitchat(self):
        """CHITCHAT responses don't get feedback buttons even with trace_id (#277)."""
        message = AsyncMock()
        state = make_initial_state(user_id=1, session_id="s", query="Привет")
        state["response"] = "Привет! 👋"
        state["message"] = message
        state["trace_id"] = "abc123def456"
        state["query_type"] = "CHITCHAT"

        await respond_node(state)

        call_kwargs = message.answer.call_args
        assert call_kwargs.kwargs.get("reply_markup") is None

    async def test_no_buttons_for_off_topic(self):
        """OFF_TOPIC responses don't get feedback buttons even with trace_id (#277)."""
        message = AsyncMock()
        state = make_initial_state(user_id=1, session_id="s", query="рецепт борща")
        state["response"] = "Я отвечаю только на вопросы о недвижимости."
        state["message"] = message
        state["trace_id"] = "abc123def456"
        state["query_type"] = "OFF_TOPIC"

        await respond_node(state)

        call_kwargs = message.answer.call_args
        assert call_kwargs.kwargs.get("reply_markup") is None

    async def test_streaming_adds_reply_markup_via_edit(self):
        """When response_sent=True, respond_node edits markup on streamed message."""
        message = AsyncMock()
        message.bot = AsyncMock()
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = "Streamed answer"
        state["message"] = message
        state["response_sent"] = True
        state["trace_id"] = "trace123"
        state["sent_message"] = {"chat_id": 12345, "message_id": 77}

        await respond_node(state)

        message.answer.assert_not_called()
        message.bot.edit_message_reply_markup.assert_awaited_once()


class TestFormatSources:
    """Test format_sources() output format (#225)."""

    def test_formats_sources_with_city(self):
        result = format_sources(_SAMPLE_DOCS)
        assert "<b>Источники:</b>" in result
        assert "[1] Апартамент Несебр — Несебр" in result
        assert "[2] Студия с видом — Равда" in result
        assert "0.92" in result
        assert "0.87" in result

    def test_empty_documents(self):
        assert format_sources([]) == ""

    def test_max_sources_cap(self):
        docs = [
            {"text": f"Doc {i}", "score": 0.5, "metadata": {"title": f"Doc {i}"}} for i in range(10)
        ]
        result = format_sources(docs, max_sources=3)
        assert "[3] Doc 2" in result
        assert "[4]" not in result

    def test_missing_city(self):
        docs = [{"text": "t", "score": 0.5, "metadata": {"title": "NoCity"}}]
        result = format_sources(docs)
        assert "NoCity" in result
        assert " — " not in result  # no city separator


class TestRespondNodeSourceAttribution:
    """Test source attribution in respond_node (#225)."""

    async def test_sources_appended_non_streaming(self):
        """Non-streaming: sources appended to response text before sending."""
        message = AsyncMock()
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = "Answer text"
        state["message"] = message
        state["documents"] = _SAMPLE_DOCS
        state["query_type"] = "GENERAL"
        state["show_sources"] = True

        result = await respond_node(state)

        sent_text = message.answer.call_args[0][0]
        assert "Answer text" in sent_text
        assert "<b>Источники:</b>" in sent_text
        assert "Апартамент Несебр" in sent_text
        assert result["sources_count"] == 2

    async def test_sources_appended_streaming(self):
        """Streaming: sources appended via edit_message_text."""
        message = AsyncMock()
        message.bot = AsyncMock()
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = "Streamed answer"
        state["message"] = message
        state["response_sent"] = True
        state["sent_message"] = {"chat_id": 12345, "message_id": 77}
        state["documents"] = _SAMPLE_DOCS
        state["query_type"] = "GENERAL"
        state["show_sources"] = True

        result = await respond_node(state)

        message.bot.edit_message_text.assert_awaited_once()
        edit_kwargs = message.bot.edit_message_text.call_args.kwargs
        assert "Streamed answer" in edit_kwargs["text"]
        assert "<b>Источники:</b>" in edit_kwargs["text"]
        assert result["sources_count"] == 2

    async def test_no_sources_for_chitchat(self):
        """CHITCHAT queries should not have sources appended even when enabled."""
        message = AsyncMock()
        state = make_initial_state(user_id=1, session_id="s", query="Привет")
        state["response"] = "Привет!"
        state["message"] = message
        state["documents"] = _SAMPLE_DOCS
        state["query_type"] = "CHITCHAT"
        state["show_sources"] = True

        result = await respond_node(state)

        sent_text = message.answer.call_args[0][0]
        assert "Источники" not in sent_text
        assert result["sources_count"] == 0

    async def test_no_sources_when_disabled(self):
        """show_sources=False should suppress source attribution."""
        message = AsyncMock()
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = "Answer"
        state["message"] = message
        state["documents"] = _SAMPLE_DOCS
        state["show_sources"] = False

        result = await respond_node(state)

        sent_text = message.answer.call_args[0][0]
        assert "Источники" not in sent_text
        assert result["sources_count"] == 0

    async def test_no_sources_when_no_documents(self):
        """No documents means no source attribution."""
        message = AsyncMock()
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = "Answer"
        state["message"] = message
        # documents is [] by default

        result = await respond_node(state)

        sent_text = message.answer.call_args[0][0]
        assert "Источники" not in sent_text
        assert result["sources_count"] == 0

    async def test_streaming_sources_fallback_to_buttons_only(self):
        """If edit_message_text fails, still try to attach feedback buttons."""
        message = AsyncMock()
        message.bot = AsyncMock()
        message.bot.edit_message_text = AsyncMock(side_effect=Exception("edit fail"))
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = "Streamed"
        state["message"] = message
        state["response_sent"] = True
        state["trace_id"] = "trace123"
        state["sent_message"] = {"chat_id": 12345, "message_id": 77}
        state["documents"] = _SAMPLE_DOCS
        state["query_type"] = "GENERAL"
        state["show_sources"] = True

        await respond_node(state)

        # edit_message_text was attempted (2 calls: Markdown + plain)
        assert message.bot.edit_message_text.await_count == 2
        # Fallback: edit_message_reply_markup for buttons
        message.bot.edit_message_reply_markup.assert_awaited_once()
