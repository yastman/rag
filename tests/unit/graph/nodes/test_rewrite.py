"""Unit tests for rewrite_node."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from telegram_bot.graph.nodes.rewrite import rewrite_node


@pytest.mark.asyncio
async def test_rewrite_node_rewrites_query_successfully() -> None:
    runtime = SimpleNamespace(context={"llm": object()})
    state = {
        "messages": [HumanMessage(content="orig query")],
        "rewrite_count": 1,
        "llm_call_count": 4,
        "latency_stages": {},
    }

    with patch(
        "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm",
        AsyncMock(return_value=("rewritten query", True, "gpt-4o-mini")),
    ):
        result = await rewrite_node(state, runtime)

    assert result["messages"][0].content == "rewritten query"
    assert result["rewrite_count"] == 2
    assert result["rewrite_effective"] is True
    assert result["rewrite_provider_model"] == "gpt-4o-mini"
    assert result["query_embedding"] is None
    assert result["sparse_embedding"] is None
    assert result["llm_call_count"] == 5


@pytest.mark.asyncio
async def test_rewrite_node_uses_fallback_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = SimpleNamespace(context={"llm": None})
    state = {
        "messages": [{"content": "need rewrite"}],
        "rewrite_count": 0,
        "llm_call_count": 0,
        "latency_stages": {},
    }
    mock_lf = MagicMock()
    fake_config = SimpleNamespace(create_llm=lambda: object())

    monkeypatch.setattr("telegram_bot.graph.config.GraphConfig.from_env", lambda: fake_config)

    with (
        patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm",
            AsyncMock(side_effect=RuntimeError("LLM down")),
        ),
        patch("telegram_bot.graph.nodes.rewrite.get_client", return_value=mock_lf),
    ):
        result = await rewrite_node(state, runtime)

    assert result["messages"][0].content == "need rewrite"
    assert result["rewrite_count"] == 1
    assert result["rewrite_effective"] is False
    assert result["rewrite_provider_model"] == "fallback"
    mock_lf.update_current_span.assert_called_once()
