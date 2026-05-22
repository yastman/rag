"""Tests for rewrite_node — LLM query reformulation.

These are the canonical unit tests for rewrite_node.
Note: tests/unit/graph/test_agentic_nodes.py::TestRewriteNode has partial overlap —
pruning deferred to a follow-up PR.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from telegram_bot.graph.nodes.rewrite import rewrite_node
from telegram_bot.graph.state import make_initial_state


def _make_runtime(llm=None) -> Runtime:
    """Create a Runtime with GraphContext for rewrite_node tests."""
    return Runtime(context={"llm": llm})


def _state_with_query(query: str = "original query") -> dict:
    """Create minimal state with a human message."""
    state = make_initial_state(user_id=1, session_id="s1", query=query)
    state["messages"] = [HumanMessage(content=query)]
    state["rewrite_count"] = 0
    state["llm_call_count"] = 0
    return state


class TestRewriteNodeSuccess:
    """rewrite_node happy path — successful LLM rewrite."""

    async def test_rewrites_query(self):
        state = _state_with_query("квартиры в несебр")

        mock_llm = MagicMock()
        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.return_value = ("квартиры в Несебре купить", True, "gpt-4o-mini")
            result = await rewrite_node(state, _make_runtime(llm=mock_llm))

        assert result["messages"][0].content == "квартиры в Несебре купить"
        assert result["rewrite_effective"] is True

    async def test_increments_rewrite_count(self):
        state = _state_with_query()
        state["rewrite_count"] = 0

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.return_value = ("rewritten", True, "gpt-4o-mini")
            result = await rewrite_node(state, _make_runtime(llm=MagicMock()))

        assert result["rewrite_count"] == 1

    async def test_increments_rewrite_count_on_subsequent_calls(self):
        """rewrite_count accumulates across multiple rewrites."""
        state = _state_with_query()
        state["rewrite_count"] = 1  # already rewritten once

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.return_value = ("rewritten again", True, "gpt-4o-mini")
            result = await rewrite_node(state, _make_runtime(llm=MagicMock()))

        assert result["rewrite_count"] == 2

    async def test_resets_query_embedding(self):
        """After rewrite, query_embedding must be None to force re-embedding."""
        state = _state_with_query()
        state["query_embedding"] = [0.1] * 1024  # stale from previous retrieval

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.return_value = ("new query", True, "gpt-4o-mini")
            result = await rewrite_node(state, _make_runtime(llm=MagicMock()))

        assert result["query_embedding"] is None

    async def test_resets_sparse_embedding(self):
        """After rewrite, sparse_embedding must be None to force re-embedding."""
        state = _state_with_query()
        state["sparse_embedding"] = {"indices": [1, 2], "values": [0.5, 0.3]}

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.return_value = ("new query", True, "gpt-4o-mini")
            result = await rewrite_node(state, _make_runtime(llm=MagicMock()))

        assert result["sparse_embedding"] is None

    async def test_stores_rewrite_model(self):
        state = _state_with_query()

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.return_value = ("rewritten", True, "cerebras/glm-4.7")
            result = await rewrite_node(state, _make_runtime(llm=MagicMock()))

        assert result["rewrite_provider_model"] == "cerebras/glm-4.7"

    async def test_increments_llm_call_count(self):
        state = _state_with_query()
        state["llm_call_count"] = 1

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.return_value = ("rewritten", True, "gpt-4o-mini")
            result = await rewrite_node(state, _make_runtime(llm=MagicMock()))

        assert result["llm_call_count"] == 2

    async def test_passes_original_query_to_llm(self):
        """LLM receives the most recent message content."""
        state = _state_with_query("apartments sea view")

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.return_value = ("sea view apartments buy", True, "gpt-4o-mini")
            await rewrite_node(state, _make_runtime(llm=MagicMock()))

        call_args = mock_rewrite.call_args
        assert call_args[0][0] == "apartments sea view"


class TestRewriteNodeFallback:
    """rewrite_node fallback when LLM fails."""

    async def test_llm_exception_keeps_original_query(self):
        """On LLM failure, original query is preserved."""
        state = _state_with_query("original query unchanged")

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.side_effect = RuntimeError("LLM service down")
            with patch("telegram_bot.graph.nodes.rewrite.get_client") as mock_get_client:
                mock_get_client.return_value = MagicMock()
                result = await rewrite_node(state, _make_runtime(llm=MagicMock()))

        assert result["messages"][0].content == "original query unchanged"
        assert result["rewrite_effective"] is False

    async def test_llm_exception_sets_fallback_model(self):
        """On LLM failure, rewrite_provider_model is set to 'fallback'."""
        state = _state_with_query()

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.side_effect = Exception("timeout")
            with patch("telegram_bot.graph.nodes.rewrite.get_client") as mock_get_client:
                mock_get_client.return_value = MagicMock()
                result = await rewrite_node(state, _make_runtime(llm=MagicMock()))

        assert result["rewrite_provider_model"] == "fallback"

    async def test_llm_exception_still_increments_rewrite_count(self):
        """Even on failure, rewrite_count increments (attempt counts)."""
        state = _state_with_query()
        state["rewrite_count"] = 0

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.side_effect = RuntimeError("timeout")
            with patch("telegram_bot.graph.nodes.rewrite.get_client") as mock_get_client:
                mock_get_client.return_value = MagicMock()
                result = await rewrite_node(state, _make_runtime(llm=MagicMock()))

        assert result["rewrite_count"] == 1

    async def test_llm_exception_logs_error_span(self):
        """On LLM failure, error is recorded via langfuse span."""
        state = _state_with_query()

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.side_effect = RuntimeError("LLM unavailable")
            with patch("telegram_bot.graph.nodes.rewrite.get_client") as mock_get_client:
                mock_lf = MagicMock()
                mock_get_client.return_value = mock_lf
                await rewrite_node(state, _make_runtime(llm=MagicMock()))

        mock_lf.update_current_span.assert_called_once()
        call_kwargs = mock_lf.update_current_span.call_args[1]
        assert call_kwargs.get("level") == "ERROR"

    async def test_fallback_resets_embeddings(self):
        """On LLM failure, embeddings are still reset to force re-embedding on next retrieve.

        Even though the query text is unchanged (original preserved), embeddings are cleared
        so the retrieve node re-embeds on the next loop iteration.
        """
        state = _state_with_query()
        state["query_embedding"] = [0.1] * 1024
        state["sparse_embedding"] = {"indices": [1], "values": [0.5]}

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.side_effect = RuntimeError("timeout")
            with patch("telegram_bot.graph.nodes.rewrite.get_client") as mock_get_client:
                mock_get_client.return_value = MagicMock()
                result = await rewrite_node(state, _make_runtime(llm=MagicMock()))

        assert result["query_embedding"] is None
        assert result["sparse_embedding"] is None


class TestRewriteNodeNoLlmInContext:
    """rewrite_node when llm is not in runtime context — falls back to config."""

    async def test_no_llm_uses_config_create_llm(self):
        """When llm=None in context, node creates LLM from GraphConfig."""
        state = _state_with_query("test")

        mock_llm = MagicMock()
        mock_config = MagicMock()
        mock_config.create_llm.return_value = mock_llm

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = mock_config
            with patch(
                "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
            ) as mock_rewrite:
                mock_rewrite.return_value = ("rewritten", True, "gpt-4o-mini")
                result = await rewrite_node(state, _make_runtime(llm=None))

        mock_config.create_llm.assert_called_once()
        assert result["rewrite_count"] == 1


class TestRewriteNodeMaxRetries:
    """rewrite_node behavior at max retry boundary."""

    async def test_multiple_rewrites_accumulate_count(self):
        """Simulate max_rewrite_attempts=2: rewrite_count reaches limit."""
        state = _state_with_query("query")
        state["rewrite_count"] = 0

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.return_value = ("rewrite 1", True, "gpt-4o-mini")
            result1 = await rewrite_node(state, _make_runtime(llm=MagicMock()))

        assert result1["rewrite_count"] == 1

        # Second rewrite attempt
        state["rewrite_count"] = result1["rewrite_count"]
        state["messages"] = result1["messages"]

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.return_value = ("rewrite 2", True, "gpt-4o-mini")
            result2 = await rewrite_node(state, _make_runtime(llm=MagicMock()))

        assert result2["rewrite_count"] == 2

    async def test_ineffective_rewrite_sets_effective_false(self):
        """LLM returns effective=False when rewrite produces no improvement."""
        state = _state_with_query("already optimal query")

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            # LLM decides rewrite wasn't effective
            mock_rewrite.return_value = ("already optimal query", False, "gpt-4o-mini")
            result = await rewrite_node(state, _make_runtime(llm=MagicMock()))

        assert result["rewrite_effective"] is False
        assert result["rewrite_count"] == 1


class TestRewriteNodeQueryExtraction:
    """rewrite_node extracts query from messages correctly."""

    async def test_query_from_human_message_object(self):
        state = make_initial_state(user_id=1, session_id="s1", query="original")
        state["messages"] = [HumanMessage(content="query via message object")]
        state["rewrite_count"] = 0

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.return_value = ("rewritten", True, "gpt-4o-mini")
            await rewrite_node(state, _make_runtime(llm=MagicMock()))

        call_args = mock_rewrite.call_args
        assert call_args[0][0] == "query via message object"

    async def test_query_from_dict_message(self):
        state = make_initial_state(user_id=1, session_id="s1", query="original")
        state["messages"] = [{"role": "user", "content": "dict-style query"}]
        state["rewrite_count"] = 0

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.return_value = ("rewritten", True, "gpt-4o-mini")
            await rewrite_node(state, _make_runtime(llm=MagicMock()))

        call_args = mock_rewrite.call_args
        assert call_args[0][0] == "dict-style query"


class TestRewriteNodeLatency:
    """rewrite_node latency tracking."""

    async def test_latency_stages_set(self):
        state = _state_with_query()
        state["latency_stages"] = {"retrieve": 0.1, "grade": 0.02}

        with patch(
            "telegram_bot.graph.nodes.rewrite.rewrite_query_via_llm", new_callable=AsyncMock
        ) as mock_rewrite:
            mock_rewrite.return_value = ("rewritten", True, "gpt-4o-mini")
            result = await rewrite_node(state, _make_runtime(llm=MagicMock()))

        assert "rewrite" in result["latency_stages"]
        assert result["latency_stages"]["retrieve"] == 0.1  # existing preserved
        assert result["latency_stages"]["rewrite"] > 0
