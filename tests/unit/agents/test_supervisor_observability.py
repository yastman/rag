"""Tests for supervisor Langfuse observability (#240 Task 7, #242, #413)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.config import BotConfig


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Prevent .env leaking CLIENT_DIRECT_PIPELINE_ENABLED into tests."""
    monkeypatch.delenv("CLIENT_DIRECT_PIPELINE_ENABLED", raising=False)
    monkeypatch.delenv("MANAGERS_GROUP_ID", raising=False)


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
        _env_file=None,
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


def _make_mock_agent():
    """Create mock agent with standard return value."""
    mock_agent = AsyncMock()
    mock_agent.ainvoke = AsyncMock(
        return_value={
            "messages": [MagicMock(content="Response")],
        }
    )
    return mock_agent


async def test_supervisor_writes_model_score(supervisor_config):
    """SDK agent path writes supervisor_model CATEGORICAL score."""
    bot = _create_bot_patched(supervisor_config)
    mock_agent = _make_mock_agent()
    mock_lf = MagicMock()

    with (
        patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes"),
        patch("telegram_bot.bot.create_callback_handler", return_value=None),
    ):
        message = _make_text_message("test")
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    score_calls = mock_lf.create_score.call_args_list
    model_scores = [c for c in score_calls if c.kwargs.get("name") == "supervisor_model"]
    assert len(model_scores) == 1
    assert model_scores[0].kwargs["value"] == "gpt-4o-mini"
    assert model_scores[0].kwargs["data_type"] == "CATEGORICAL"


async def test_supervisor_trace_has_pipeline_mode_metadata(supervisor_config):
    """SDK agent trace metadata includes pipeline_mode=sdk_agent."""
    bot = _create_bot_patched(supervisor_config)
    mock_agent = _make_mock_agent()
    mock_lf = MagicMock()

    with (
        patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes"),
        patch("telegram_bot.bot.create_callback_handler", return_value=None),
    ):
        message = _make_text_message("test")
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    trace_calls = mock_lf.update_current_trace.call_args_list
    assert trace_calls, "update_current_trace was never called"
    meta_call = next((c for c in trace_calls if "metadata" in c[1]), None)
    assert meta_call is not None, "no update_current_trace call contains metadata"
    assert meta_call[1]["metadata"]["pipeline_mode"] == "sdk_agent"


# --- #242: @observe decorator presence tests ---


def test_rag_tool_has_observe_decorator():
    """rag_search tool module imports observe (#413)."""
    import telegram_bot.agents.rag_tool as rag_mod

    assert hasattr(rag_mod, "observe"), "rag_tool module must import observe"


def test_history_tool_has_observe_decorator():
    """history_search tool module imports observe (#413)."""
    import telegram_bot.agents.history_tool as hist_mod

    assert hasattr(hist_mod, "observe"), "history_tool module must import observe"


def test_crm_tools_have_observe_decorator():
    """CRM tools module imports observe (#413)."""
    import telegram_bot.agents.crm_tools as crm_mod

    assert hasattr(crm_mod, "observe"), "crm_tools module must import observe"


async def test_supervisor_propagate_attributes_called_with_agent_tag(supervisor_config):
    """SDK agent path calls propagate_attributes with 'agent' tag (#413)."""
    bot = _create_bot_patched(supervisor_config)
    mock_agent = _make_mock_agent()
    mock_lf = MagicMock()
    mock_propagate = MagicMock()
    mock_propagate.__enter__ = MagicMock()
    mock_propagate.__exit__ = MagicMock(return_value=False)

    with (
        patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes", return_value=mock_propagate) as mock_prop,
        patch("telegram_bot.bot.create_callback_handler", return_value=None),
    ):
        message = _make_text_message("test")
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    mock_prop.assert_called_once()
    call_kwargs = mock_prop.call_args[1]
    assert "agent" in call_kwargs["tags"]
    assert call_kwargs["session_id"]  # non-empty
    assert call_kwargs["user_id"]  # non-empty


async def test_supervisor_writes_user_role_score(supervisor_config):
    """Supervisor path writes user_role CATEGORICAL score (#388)."""
    supervisor_config.manager_ids = [12345]
    bot = _create_bot_patched(supervisor_config)

    mock_agent = AsyncMock()
    mock_agent.ainvoke = AsyncMock(
        return_value={
            "messages": [MagicMock(content="Response")],
            "agent_used": "rag_search",
            "latency_stages": {"supervisor": 0.05},
        }
    )
    mock_lf = MagicMock()

    with (
        patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes"),
        patch("telegram_bot.bot.create_callback_handler", return_value=None),
    ):
        message = _make_text_message("цены", user_id=12345)
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    role_scores = [
        c for c in mock_lf.create_score.call_args_list if c.kwargs.get("name") == "user_role"
    ]
    assert len(role_scores) == 1
    assert role_scores[0].kwargs["value"] == "manager"
    assert role_scores[0].kwargs["data_type"] == "CATEGORICAL"


async def test_supervisor_curated_span_metadata_on_routing(supervisor_config):
    """SDK agent path writes curated trace metadata (#413)."""
    bot = _create_bot_patched(supervisor_config)
    mock_agent = _make_mock_agent()
    mock_lf = MagicMock()

    with (
        patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes"),
        patch("telegram_bot.bot.create_callback_handler", return_value=None),
    ):
        message = _make_text_message("недвижимость")
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    trace_calls = mock_lf.update_current_trace.call_args_list
    assert trace_calls, "update_current_trace was never called"
    assert any("input" in c[1] or "metadata" in c[1] for c in trace_calls)


async def test_agent_ainvoke_receives_bot_context(supervisor_config):
    """agent.ainvoke receives BotContext in config.configurable (#413)."""
    bot = _create_bot_patched(supervisor_config)
    mock_agent = _make_mock_agent()
    mock_lf = MagicMock()

    with (
        patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes"),
        patch("telegram_bot.bot.create_callback_handler", return_value=None),
    ):
        message = _make_text_message("test")
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    # Verify agent.ainvoke was called with config containing bot_context
    call_args = mock_agent.ainvoke.call_args
    config = call_args[1].get("config") or call_args[0][1] if len(call_args[0]) > 1 else None
    if config is None:
        # config passed as keyword
        config = call_args[1].get("config")
    assert config is not None
    assert "bot_context" in config["configurable"]
