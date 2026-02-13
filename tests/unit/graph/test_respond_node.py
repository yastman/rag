"""Tests for respond_node — Telegram message sending with Markdown fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock

from telegram_bot.graph.nodes.respond import respond_node
from telegram_bot.graph.state import make_initial_state


class TestRespondNode:
    async def test_sends_markdown(self):
        message = AsyncMock()
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["response"] = "**Bold** answer"
        state["message"] = message

        result = await respond_node(state)

        message.answer.assert_awaited_once_with(
            "**Bold** answer", parse_mode="Markdown", reply_markup=None
        )
        assert "respond" in result["latency_stages"]

    async def test_fallback_to_plain_text(self):
        message = AsyncMock()
        # First call (Markdown) raises, second call (plain) succeeds
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
