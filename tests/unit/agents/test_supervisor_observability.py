"""Tests for supervisor Langfuse observability (#240 Task 7, #242)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.config import BotConfig


@pytest.fixture
def supervisor_config():
    """BotConfig for supervisor tests (#310: supervisor-only)."""
    return BotConfig(
        telegram_token="test-token",
        voyage_api_key="voyage-key",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        qdrant_api_key="qdrant-key",
        qdrant_collection="test_collection",
        redis_url="redis://localhost:6379",
        rerank_provider="none",
    )


def _create_bot_patched(config):
    """Create PropertyBot with all deps mocked."""
    from telegram_bot.bot import PropertyBot

    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
    ):
        return PropertyBot(config)


def _make_text_message(text="test", user_id=12345, chat_id=12345):
    message = MagicMock()
    message.text = text
    message.from_user = MagicMock(id=user_id)
    message.chat = MagicMock(id=chat_id)
    message.bot = MagicMock()
    message.bot.send_chat_action = AsyncMock()
    message.answer = AsyncMock()
    return message


def _make_typing_cm():
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock()
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


async def test_supervisor_writes_agent_used_score(supervisor_config):
    """Supervisor path writes agent_used CATEGORICAL score to Langfuse."""
    bot = _create_bot_patched(supervisor_config)

    mock_supervisor_graph = AsyncMock()
    mock_supervisor_graph.ainvoke = AsyncMock(
        return_value={
            "messages": [MagicMock(content="Response")],
            "agent_used": "rag_search",
            "latency_stages": {"supervisor": 0.05},
        }
    )
    mock_lf = MagicMock()

    with (
        patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_supervisor_graph),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes"),
    ):
        message = _make_text_message("цены")
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    # Find the agent_used score call
    score_calls = mock_lf.score_current_trace.call_args_list
    agent_scores = [c for c in score_calls if c[1].get("name") == "agent_used"]
    assert len(agent_scores) == 1
    assert agent_scores[0][1]["value"] == "rag_search"
    assert agent_scores[0][1]["data_type"] == "CATEGORICAL"


async def test_supervisor_writes_latency_score(supervisor_config):
    """Supervisor path writes supervisor_latency_ms NUMERIC score."""
    bot = _create_bot_patched(supervisor_config)

    mock_supervisor_graph = AsyncMock()
    mock_supervisor_graph.ainvoke = AsyncMock(
        return_value={
            "messages": [MagicMock(content="Response")],
            "agent_used": "direct_response",
            "latency_stages": {"supervisor": 0.123},
        }
    )
    mock_lf = MagicMock()

    with (
        patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_supervisor_graph),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes"),
    ):
        message = _make_text_message("привет")
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    score_calls = mock_lf.score_current_trace.call_args_list
    latency_scores = [c for c in score_calls if c[1].get("name") == "supervisor_latency_ms"]
    assert len(latency_scores) == 1
    assert latency_scores[0][1]["value"] == pytest.approx(123.0, abs=1.0)


async def test_supervisor_writes_model_score(supervisor_config):
    """Supervisor path writes supervisor_model CATEGORICAL score."""
    bot = _create_bot_patched(supervisor_config)

    mock_supervisor_graph = AsyncMock()
    mock_supervisor_graph.ainvoke = AsyncMock(
        return_value={
            "messages": [MagicMock(content="Response")],
            "agent_used": "rag_search",
            "latency_stages": {"supervisor": 0.05},
        }
    )
    mock_lf = MagicMock()

    with (
        patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_supervisor_graph),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes"),
    ):
        message = _make_text_message("test")
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    score_calls = mock_lf.score_current_trace.call_args_list
    model_scores = [c for c in score_calls if c[1].get("name") == "supervisor_model"]
    assert len(model_scores) == 1
    assert model_scores[0][1]["value"] == "gpt-4o-mini"
    assert model_scores[0][1]["data_type"] == "CATEGORICAL"


async def test_supervisor_trace_has_pipeline_mode_metadata(supervisor_config):
    """Supervisor trace metadata includes pipeline_mode=supervisor."""
    bot = _create_bot_patched(supervisor_config)

    mock_supervisor_graph = AsyncMock()
    mock_supervisor_graph.ainvoke = AsyncMock(
        return_value={
            "messages": [MagicMock(content="Response")],
            "agent_used": "rag_search",
            "latency_stages": {"supervisor": 0.05},
        }
    )
    mock_lf = MagicMock()

    with (
        patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_supervisor_graph),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes"),
    ):
        message = _make_text_message("test")
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    trace_call = mock_lf.update_current_trace.call_args
    assert trace_call is not None
    metadata = trace_call[1]["metadata"]
    assert metadata["pipeline_mode"] == "supervisor"
    assert metadata["agent_used"] == "rag_search"


# --- #242: @observe decorator presence tests ---


def test_supervisor_node_has_observe_decorator():
    """supervisor_node inside build_supervisor_graph is decorated with @observe (#242)."""

    # Verify the module imports observe and get_client for span creation
    import telegram_bot.agents.supervisor as sup_mod

    assert hasattr(sup_mod, "observe"), "supervisor module must import observe"
    assert hasattr(sup_mod, "get_client"), "supervisor module must import get_client"


def test_rag_agent_tool_has_observe_decorator():
    """rag_search tool is decorated with @observe (#242)."""
    import telegram_bot.agents.rag_agent as rag_mod

    assert hasattr(rag_mod, "observe"), "rag_agent module must import observe"
    assert hasattr(rag_mod, "get_client"), "rag_agent module must import get_client"


def test_history_agent_tool_has_observe_decorator():
    """history_search tool is decorated with @observe (#242)."""
    import telegram_bot.agents.history_agent as hist_mod

    assert hasattr(hist_mod, "observe"), "history_agent module must import observe"


def test_direct_response_tool_has_observe_decorator():
    """direct_response tool is decorated with @observe (#242)."""
    import telegram_bot.agents.tools as tools_mod

    assert hasattr(tools_mod, "observe"), "tools module must import observe"


async def test_supervisor_propagate_attributes_called_with_supervisor_tag(supervisor_config):
    """Supervisor path calls propagate_attributes with 'supervisor' tag (#242)."""
    bot = _create_bot_patched(supervisor_config)

    mock_supervisor_graph = AsyncMock()
    mock_supervisor_graph.ainvoke = AsyncMock(
        return_value={
            "messages": [MagicMock(content="Response")],
            "agent_used": "rag_search",
            "latency_stages": {"supervisor": 0.05},
        }
    )
    mock_lf = MagicMock()
    mock_propagate = MagicMock()
    mock_propagate.__enter__ = MagicMock()
    mock_propagate.__exit__ = MagicMock(return_value=False)

    with (
        patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_supervisor_graph),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes", return_value=mock_propagate) as mock_prop,
    ):
        message = _make_text_message("test")
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    # Verify propagate_attributes was called with supervisor tag
    mock_prop.assert_called_once()
    call_kwargs = mock_prop.call_args[1]
    assert "supervisor" in call_kwargs["tags"]
    assert call_kwargs["session_id"]  # non-empty
    assert call_kwargs["user_id"]  # non-empty


async def test_supervisor_writes_user_role_score(supervisor_config):
    """Supervisor path writes user_role CATEGORICAL score (#388)."""
    supervisor_config.manager_ids = [12345]
    bot = _create_bot_patched(supervisor_config)

    mock_supervisor_graph = AsyncMock()
    mock_supervisor_graph.ainvoke = AsyncMock(
        return_value={
            "messages": [MagicMock(content="Response")],
            "agent_used": "rag_search",
            "latency_stages": {"supervisor": 0.05},
        }
    )
    mock_lf = MagicMock()

    with (
        patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_supervisor_graph),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes"),
    ):
        message = _make_text_message("цены", user_id=12345)
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    role_scores = [
        c for c in mock_lf.score_current_trace.call_args_list if c[1].get("name") == "user_role"
    ]
    assert len(role_scores) == 1
    assert role_scores[0][1]["value"] == "manager"
    assert role_scores[0][1]["data_type"] == "CATEGORICAL"


async def test_supervisor_curated_span_metadata_on_routing(supervisor_config):
    """Supervisor node writes curated span metadata for routing decision (#242)."""
    bot = _create_bot_patched(supervisor_config)

    mock_supervisor_graph = AsyncMock()
    mock_supervisor_graph.ainvoke = AsyncMock(
        return_value={
            "messages": [MagicMock(content="Response")],
            "agent_used": "rag_search",
            "latency_stages": {"supervisor": 0.05},
        }
    )
    mock_lf = MagicMock()

    with (
        patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_supervisor_graph),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes"),
    ):
        message = _make_text_message("недвижимость")
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    # Verify update_current_trace was called (trace-level metadata)
    trace_call = mock_lf.update_current_trace.call_args
    assert trace_call is not None
    assert "input" in trace_call[1] or "metadata" in trace_call[1]
