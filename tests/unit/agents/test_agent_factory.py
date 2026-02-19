"""Tests for create_bot_agent factory (#413)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


def test_create_bot_agent_returns_compiled_graph():
    """create_bot_agent returns a compiled graph with .ainvoke method."""
    from telegram_bot.agents.agent import create_bot_agent

    mock_agent = MagicMock()
    with patch("telegram_bot.agents.agent.create_agent", return_value=mock_agent) as mock_ca:
        agent = create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[MagicMock()],
            checkpointer=AsyncMock(),
        )
        mock_ca.assert_called_once()
        assert agent is mock_agent


def test_create_bot_agent_passes_context_schema():
    """create_bot_agent passes BotContext as context_schema."""
    from telegram_bot.agents.agent import create_bot_agent
    from telegram_bot.agents.context import BotContext

    with patch("telegram_bot.agents.agent.create_agent") as mock_ca:
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=None,
        )
        call_kwargs = mock_ca.call_args[1]
        assert call_kwargs["context_schema"] is BotContext


def test_create_bot_agent_passes_system_prompt():
    """create_bot_agent includes system_prompt with tool descriptions."""
    from telegram_bot.agents.agent import create_bot_agent

    with patch("telegram_bot.agents.agent.create_agent") as mock_ca:
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=None,
            system_prompt="Custom prompt",
        )
        call_kwargs = mock_ca.call_args[1]
        assert "Custom prompt" in call_kwargs["system_prompt"]


def test_create_bot_agent_interpolates_language_in_default_prompt():
    """Default prompt must interpolate {language} placeholder."""
    from telegram_bot.agents.agent import create_bot_agent

    with (
        patch("telegram_bot.agents.agent.create_agent") as mock_ca,
        patch("telegram_bot.agents.agent.get_prompt", return_value="Prompt on английском языке"),
    ):
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=None,
            language="английском языке",
        )
        prompt = mock_ca.call_args[1]["system_prompt"]
        assert "английском языке" in prompt
        assert "{{language}}" not in prompt


def test_create_bot_agent_passes_checkpointer():
    """create_bot_agent passes checkpointer for conversation persistence."""
    from telegram_bot.agents.agent import create_bot_agent

    mock_cp = AsyncMock()
    with patch("telegram_bot.agents.agent.create_agent") as mock_ca:
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=mock_cp,
        )
        call_kwargs = mock_ca.call_args[1]
        assert call_kwargs["checkpointer"] is mock_cp


def test_create_bot_agent_uses_langfuse_prompt_manager_by_default():
    """Default system prompt should be resolved via prompt manager."""
    from telegram_bot.agents.agent import create_bot_agent

    with (
        patch("telegram_bot.agents.agent.create_agent"),
        patch("telegram_bot.agents.agent.get_prompt", return_value="resolved prompt") as mock_get,
    ):
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=None,
            language="русском языке",
        )

    mock_get.assert_called_once()
    call_kwargs = mock_get.call_args.kwargs
    assert mock_get.call_args.args[0] == "supervisor_agent"
    assert call_kwargs["variables"] == {"language": "русском языке"}
    assert "rag_search" in call_kwargs["fallback"]


def test_create_bot_agent_custom_prompt_bypasses_prompt_manager():
    """Explicit system_prompt should skip prompt manager lookup."""
    from telegram_bot.agents.agent import create_bot_agent

    with (
        patch("telegram_bot.agents.agent.create_agent"),
        patch("telegram_bot.agents.agent.get_prompt") as mock_get,
    ):
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=None,
            system_prompt="Manual prompt",
        )

    mock_get.assert_not_called()


def test_default_system_prompt_contains_safety_instructions():
    """DEFAULT_SYSTEM_PROMPT must include safety/refusal instructions (#439)."""
    from telegram_bot.agents.agent import DEFAULT_SYSTEM_PROMPT

    # Must refuse prompt injection attempts
    assert "НЕ выполняй" in DEFAULT_SYSTEM_PROMPT
    # Must refuse system prompt leaks
    assert "НЕ раскрывай" in DEFAULT_SYSTEM_PROMPT
    # Must have a safety section
    assert "Безопасность" in DEFAULT_SYSTEM_PROMPT
    # Must enforce rag_search for property questions
    assert "rag_search" in DEFAULT_SYSTEM_PROMPT


# --- #519: Sliding-window history trimmer ---


def test_create_bot_agent_passes_history_trimmer_middleware():
    """create_bot_agent injects a before_model history-trimmer when checkpointer set (#519)."""
    from langchain.agents.middleware import AgentMiddleware

    from telegram_bot.agents.agent import create_bot_agent

    with patch("telegram_bot.agents.agent.create_agent") as mock_ca:
        create_bot_agent(
            model="openai/gpt-4o-mini",
            tools=[],
            checkpointer=MagicMock(),  # non-None checkpointer
            max_history_messages=10,
        )
        call_kwargs = mock_ca.call_args[1]
        middleware = call_kwargs.get("middleware", [])
        assert len(middleware) == 1, "Exactly one middleware expected (history trimmer)"
        assert isinstance(middleware[0], AgentMiddleware)
        assert callable(middleware[0].before_model)


def test_create_bot_agent_no_middleware_without_checkpointer():
    """create_bot_agent skips history-trimmer middleware when checkpointer=None (#519)."""
    from telegram_bot.agents.agent import create_bot_agent

    with patch("telegram_bot.agents.agent.create_agent") as mock_ca:
        create_bot_agent(
            model="openai/gpt-4o-mini",
            tools=[],
            checkpointer=None,
            max_history_messages=10,
        )
        call_kwargs = mock_ca.call_args[1]
        middleware = call_kwargs.get("middleware", [])
        assert len(middleware) == 0, "No middleware expected without checkpointer"


def test_create_bot_agent_default_max_history_messages():
    """create_bot_agent defaults to max_history_messages=15 (#519)."""
    from telegram_bot.agents.agent import create_bot_agent

    with patch("telegram_bot.agents.agent.create_agent") as mock_ca:
        create_bot_agent(
            model="openai/gpt-4o-mini",
            tools=[],
            checkpointer=MagicMock(),  # non-None to get middleware
        )
        call_kwargs = mock_ca.call_args[1]
        # Middleware must still be present with default window
        assert len(call_kwargs.get("middleware", [])) == 1


def test_history_trimmer_noop_when_within_limit():
    """_create_history_trimmer returns None when messages <= max_messages (#519)."""
    from unittest.mock import MagicMock

    from langchain_core.messages import AIMessage, HumanMessage

    from telegram_bot.agents.agent import _create_history_trimmer

    trimmer = _create_history_trimmer(max_messages=10)
    state = {
        "messages": [
            HumanMessage(content="hi", id="h1"),
            AIMessage(content="hello", id="a1"),
        ]
    }
    result = trimmer.before_model(state, MagicMock())
    assert result is None, "Should be a no-op when history is short"


def test_history_trimmer_removes_old_messages_when_over_limit():
    """_create_history_trimmer returns RemoveMessage for oldest messages (#519)."""
    from unittest.mock import MagicMock

    from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage

    from telegram_bot.agents.agent import _create_history_trimmer

    trimmer = _create_history_trimmer(max_messages=4)

    # Build 6 messages: 3 turns (H, AI) — oldest turn should be removed
    messages = [
        HumanMessage(content="q1", id="h1"),
        AIMessage(content="a1", id="a1"),
        HumanMessage(content="q2", id="h2"),
        AIMessage(content="a2", id="a2"),
        HumanMessage(content="q3", id="h3"),
        AIMessage(content="a3", id="a3"),
    ]
    state = {"messages": messages}
    result = trimmer.before_model(state, MagicMock())

    assert result is not None, "Should return a state update"
    assert "messages" in result
    remove_msgs = result["messages"]
    assert all(isinstance(m, RemoveMessage) for m in remove_msgs)

    # Oldest 2 messages should be removed (keep last 4 starting on human)
    removed_ids = {m.id for m in remove_msgs}
    assert "h1" in removed_ids
    assert "a1" in removed_ids
    # Kept messages should not be in remove list
    assert "h2" not in removed_ids
    assert "h3" not in removed_ids
    assert "a3" not in removed_ids


def test_history_trimmer_respects_start_on_human():
    """Trimmer never starts window on a non-human message (#519)."""
    from unittest.mock import MagicMock

    from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage

    from telegram_bot.agents.agent import _create_history_trimmer

    # 5 messages, max=3 — naive cut would start on AIMessage
    # start_on="human" must push window start to the next HumanMessage
    trimmer = _create_history_trimmer(max_messages=3)
    messages = [
        HumanMessage(content="q1", id="h1"),
        AIMessage(content="a1", id="a1"),
        HumanMessage(content="q2", id="h2"),
        AIMessage(content="a2", id="a2"),
        HumanMessage(content="q3", id="h3"),
    ]
    state = {"messages": messages}
    result = trimmer.before_model(state, MagicMock())

    assert result is not None
    removed_ids = {m.id for m in result["messages"] if isinstance(m, RemoveMessage)}
    # Window must start on h2 or later — both h2, a2, h3 should be kept
    assert "h2" not in removed_ids and "a2" not in removed_ids and "h3" not in removed_ids
    # First kept message must be a HumanMessage (start_on constraint)
    kept = [m for m in messages if m.id not in removed_ids]
    assert isinstance(kept[0], HumanMessage), f"Window starts on {type(kept[0])}"


def test_history_trimmer_noop_when_no_human_message_fits_window():
    """Trimmer returns None when trim_messages produces an empty window (#519)."""
    from unittest.mock import MagicMock

    from langchain_core.messages import AIMessage

    from telegram_bot.agents.agent import _create_history_trimmer

    # 5 consecutive AI messages — start_on="human" finds no valid boundary,
    # so trim_messages returns []. The trimmer must not wipe the whole state.
    trimmer = _create_history_trimmer(max_messages=2)
    messages = [AIMessage(content=f"a{i}", id=f"a{i}") for i in range(5)]
    state = {"messages": messages}
    result = trimmer.before_model(state, MagicMock())
    assert result is None, "Should be a no-op rather than wiping all messages"
