"""Unit tests for sdk_agent streaming path — issue #952.

Tests that:
 - _astream_agent_response forwards tokens via send_message_draft
 - _ainvoke_supervisor_with_recovery routes to streaming when enabled
 - Fallback to ainvoke works correctly
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _make_ai_chunk(text: str) -> Any:
    """Minimal AIMessageChunk-like object for final response tokens."""
    chunk = MagicMock()
    chunk.content = text
    chunk.tool_calls = []
    return chunk


def _make_tool_chunk() -> Any:
    """AIMessageChunk representing a tool-call decision (should NOT be drafted)."""
    chunk = MagicMock()
    chunk.content = ""
    chunk.tool_calls = [{"name": "rag_search", "args": {}}]
    return chunk


async def _astream_with_tokens(payload: Any, config: Any = None, stream_mode: Any = None):
    """Mock agent.astream() — tool chunk then text tokens then final state."""
    tokens = ["Привет", ", ", "мир", "!"]
    yield ("messages", (_make_tool_chunk(), {"langgraph_node": "agent"}))
    for token in tokens:
        yield ("messages", (_make_ai_chunk(token), {"langgraph_node": "agent"}))
    last_msg = MagicMock()
    last_msg.content = "Привет, мир!"
    yield ("values", {"messages": [last_msg]})


def _make_message(chat_id: int = 12345) -> Any:
    """Return a minimal aiogram Message mock."""
    mock_bot = AsyncMock()
    mock_bot.send_message_draft = AsyncMock(return_value=None)
    msg = MagicMock()
    msg.bot = mock_bot
    msg.chat = MagicMock()
    msg.chat.id = chat_id
    return msg


class _MinimalBot:
    """Bare stub — acts as 'self' when calling unbound PropertyBot methods."""


# --------------------------------------------------------------------------- #
# _astream_agent_response tests                                                #
# --------------------------------------------------------------------------- #


async def test_astream_agent_response_sends_drafts():
    """Tokens from the final AI response are forwarded via send_message_draft."""
    from telegram_bot.bot import PropertyBot

    instance = _MinimalBot()
    message = _make_message()

    mock_agent = MagicMock()
    mock_agent.astream = _astream_with_tokens

    rag_result_store: dict[str, Any] = {}
    payload = {"messages": [{"role": "user", "content": "hi"}]}
    config: dict[str, Any] = {}

    result = await PropertyBot._astream_agent_response(
        instance,  # type: ignore[arg-type]
        agent=mock_agent,
        payload=payload,
        config=config,
        message=message,
        forum_thread_id=None,
        rag_result_store=rag_result_store,
    )

    assert message.bot.send_message_draft.called, (
        "send_message_draft should be called for text token chunks"
    )
    assert "messages" in result
    assert "agent_ttft_ms" in rag_result_store
    assert rag_result_store["agent_ttft_ms"] > 0


async def test_astream_agent_response_ignores_tool_chunks():
    """Tool-call chunks must NOT trigger send_message_draft."""
    from telegram_bot.bot import PropertyBot

    instance = _MinimalBot()
    message = _make_message()

    async def _tool_only(payload: Any, config: Any = None, stream_mode: Any = None):
        yield ("messages", (_make_tool_chunk(), {"langgraph_node": "agent"}))
        last_msg = MagicMock()
        last_msg.content = "Done"
        yield ("values", {"messages": [last_msg]})

    mock_agent = MagicMock()
    mock_agent.astream = _tool_only

    await PropertyBot._astream_agent_response(
        instance,  # type: ignore[arg-type]
        agent=mock_agent,
        payload={},
        config={},
        message=message,
        forum_thread_id=None,
        rag_result_store={},
    )

    message.bot.send_message_draft.assert_not_called()


async def test_astream_agent_response_returns_final_state():
    """Final result comes from the last 'values' event, not from a separate ainvoke."""
    from telegram_bot.bot import PropertyBot

    instance = _MinimalBot()
    message = _make_message()

    sentinel = MagicMock()
    sentinel.content = "sentinel"

    async def _astream_sentinel(payload: Any, config: Any = None, stream_mode: Any = None):
        yield ("messages", (_make_ai_chunk("sentinel"), {"langgraph_node": "agent"}))
        yield ("values", {"messages": [sentinel], "custom_field": "check_me"})

    mock_agent = MagicMock()
    mock_agent.astream = _astream_sentinel

    result = await PropertyBot._astream_agent_response(
        instance,  # type: ignore[arg-type]
        agent=mock_agent,
        payload={},
        config={},
        message=message,
        forum_thread_id=None,
        rag_result_store={},
    )

    assert result.get("custom_field") == "check_me"


# --------------------------------------------------------------------------- #
# _ainvoke_supervisor_with_recovery routing tests                              #
# --------------------------------------------------------------------------- #


def _make_bot_instance(streaming_enabled: bool = True) -> Any:
    """Return a mock bot instance with real routing method."""
    bot_instance = MagicMock()
    bot_instance.config.streaming_enabled = streaming_enabled
    bot_instance._agent_checkpointer = None
    return bot_instance


async def test_ainvoke_supervisor_routes_to_streaming_when_enabled():
    """When streaming enabled and message provided, _astream_agent_response is called."""
    from telegram_bot.bot import PropertyBot

    bot_instance = _make_bot_instance(streaming_enabled=True)
    final_state = {"messages": [MagicMock(content="streamed")]}
    bot_instance._astream_agent_response = AsyncMock(return_value=final_state)

    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value={"messages": []})
    message = _make_message()

    result = await PropertyBot._ainvoke_supervisor_with_recovery(
        bot_instance,
        agent=mock_agent,
        tools=[],
        role="client",
        user_text="Hi",
        chat_id=message.chat.id,
        callbacks=[],
        bot_context=MagicMock(),
        rag_result_store={},
        forum_thread_id=None,
        message=message,
    )

    bot_instance._astream_agent_response.assert_called_once()
    mock_agent.ainvoke.assert_not_called()
    assert result == final_state


async def test_ainvoke_supervisor_uses_ainvoke_when_streaming_disabled():
    """When streaming disabled, ainvoke is used even if message is provided."""
    from telegram_bot.bot import PropertyBot

    bot_instance = _make_bot_instance(streaming_enabled=False)
    bot_instance._astream_agent_response = AsyncMock()

    final_state = {"messages": [MagicMock(content="full")]}
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value=final_state)
    message = _make_message()

    result = await PropertyBot._ainvoke_supervisor_with_recovery(
        bot_instance,
        agent=mock_agent,
        tools=[],
        role="client",
        user_text="Hi",
        chat_id=message.chat.id,
        callbacks=[],
        bot_context=MagicMock(),
        rag_result_store={},
        forum_thread_id=None,
        message=message,
    )

    bot_instance._astream_agent_response.assert_not_called()
    mock_agent.ainvoke.assert_called_once()
    assert result == final_state


async def test_ainvoke_supervisor_uses_ainvoke_without_message():
    """When message=None, ainvoke is used regardless of streaming config."""
    from telegram_bot.bot import PropertyBot

    bot_instance = _make_bot_instance(streaming_enabled=True)
    bot_instance._astream_agent_response = AsyncMock()

    final_state = {"messages": [MagicMock(content="full")]}
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value=final_state)

    result = await PropertyBot._ainvoke_supervisor_with_recovery(
        bot_instance,
        agent=mock_agent,
        tools=[],
        role="client",
        user_text="Hi",
        chat_id=111,
        callbacks=[],
        bot_context=MagicMock(),
        rag_result_store={},
        forum_thread_id=None,
        message=None,
    )

    bot_instance._astream_agent_response.assert_not_called()
    mock_agent.ainvoke.assert_called_once()
    assert result == final_state


async def test_ainvoke_supervisor_falls_back_on_stream_error():
    """If _astream_agent_response raises, ainvoke is used as fallback."""
    from telegram_bot.bot import PropertyBot

    bot_instance = _make_bot_instance(streaming_enabled=True)
    bot_instance._astream_agent_response = AsyncMock(side_effect=RuntimeError("stream broken"))

    final_state = {"messages": [MagicMock(content="fallback")]}
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value=final_state)
    message = _make_message()

    result = await PropertyBot._ainvoke_supervisor_with_recovery(
        bot_instance,
        agent=mock_agent,
        tools=[],
        role="client",
        user_text="Hi",
        chat_id=message.chat.id,
        callbacks=[],
        bot_context=MagicMock(),
        rag_result_store={},
        forum_thread_id=None,
        message=message,
    )

    mock_agent.ainvoke.assert_called_once()
    assert result == final_state
