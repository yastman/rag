# tests/unit/test_bot_scores.py
"""Tests for Langfuse score writing in handle_query."""

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


@pytest.fixture
def mock_config():
    """Create mock bot config."""
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


def _create_bot(mock_config):
    """Create PropertyBot with all deps mocked."""
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3Embeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
    ):
        bot = PropertyBot(mock_config)
    return bot  # noqa: RET504


def _make_message(text="квартиры до 100000 евро", user_id=123456789, chat_id=987654321):
    """Create mock Telegram message."""
    message = MagicMock()
    message.text = text
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.chat = MagicMock()
    message.chat.id = chat_id
    message.bot = MagicMock()
    message.bot.send_chat_action = AsyncMock()
    message.answer = AsyncMock()
    return message


# Typical graph result for a full RAG pipeline (cache miss, search, rerank, generate)
FULL_PIPELINE_RESULT = {
    "response": "Вот квартиры до 100000 евро...",
    "query_type": "STRUCTURED",
    "cache_hit": False,
    "cached_response": None,
    "search_results_count": 5,
    "rerank_applied": True,
    "documents_relevant": True,
    "embeddings_cache_hit": False,
    "search_cache_hit": False,
    "grade_confidence": 0.85,
    "pipeline_wall_ms": 862.0,
    "latency_stages": {
        "classify": 0.001,
        "cache_check": 0.050,
        "retrieve": 0.200,
        "grade": 0.001,
        "rerank": 0.100,
        "generate": 0.500,
        "respond": 0.010,
    },
}

# Cache hit result (short-circuit)
CACHE_HIT_RESULT = {
    "response": "Cached answer here",
    "query_type": "GENERAL",
    "cache_hit": True,
    "cached_response": "Cached answer here",
    "search_results_count": 0,
    "rerank_applied": False,
    "documents_relevant": False,
    "latency_stages": {
        "classify": 0.001,
        "cache_check": 0.020,
        "respond": 0.005,
    },
}

# Chitchat result (no RAG at all)
CHITCHAT_RESULT = {
    "response": "Привет! 👋 Я помогу найти недвижимость.",
    "query_type": "CHITCHAT",
    "cache_hit": False,
    "search_results_count": 0,
    "rerank_applied": False,
    "latency_stages": {"classify": 0.001, "respond": 0.005},
}


class TestScoreWriting:
    """Test that Langfuse scores are written after graph.ainvoke."""

    async def _run_handle_query(self, mock_config, graph_result, mock_lf_client):
        """Helper: run handle_query with mocked graph and Langfuse client."""
        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=graph_result)

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf_client),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm
            # propagate_attributes is a context manager
            mock_prop.return_value.__enter__ = MagicMock()
            mock_prop.return_value.__exit__ = MagicMock()

            await bot.handle_query(_make_message())

        return mock_lf_client

    @pytest.mark.asyncio
    async def test_scores_written_full_pipeline(self, mock_config):
        """All 12 scores should be written after a full pipeline run."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await self._run_handle_query(mock_config, FULL_PIPELINE_RESULT, mock_lf)

        # Extract all score names from calls
        score_calls = mock_lf.score_current_trace.call_args_list
        score_names = [call.kwargs["name"] for call in score_calls]

        expected_names = [
            "query_type",
            "latency_total_ms",
            "semantic_cache_hit",
            "embeddings_cache_hit",
            "search_cache_hit",
            "rerank_applied",
            "rerank_cache_hit",
            "results_count",
            "no_results",
            "llm_used",
            "confidence_score",
            "hyde_used",
        ]
        assert sorted(score_names) == sorted(expected_names)
        assert mock_lf.score_current_trace.call_count == 12

    @pytest.mark.asyncio
    async def test_score_values_full_pipeline(self, mock_config):
        """Score values should match the graph result state."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await self._run_handle_query(mock_config, FULL_PIPELINE_RESULT, mock_lf)

        scores = {
            call.kwargs["name"]: call.kwargs["value"]
            for call in mock_lf.score_current_trace.call_args_list
        }
        # query_type: STRUCTURED → 2
        assert scores["query_type"] == 2.0
        # cache miss
        assert scores["semantic_cache_hit"] == 0.0
        # rerank applied
        assert scores["rerank_applied"] == 1.0
        # 5 results
        assert scores["results_count"] == 5.0
        # not empty
        assert scores["no_results"] == 0.0
        # generate in latency_stages → LLM used
        assert scores["llm_used"] == 1.0
        # latency_total_ms = pipeline_wall_ms (wall-time, not sum of stages)
        assert abs(scores["latency_total_ms"] - FULL_PIPELINE_RESULT["pipeline_wall_ms"]) < 0.01
        # embeddings/search cache misses, confidence from grade
        assert scores["embeddings_cache_hit"] == 0.0
        assert scores["search_cache_hit"] == 0.0
        assert scores["confidence_score"] == 0.85

    @pytest.mark.asyncio
    async def test_score_values_cache_hit(self, mock_config):
        """Cache hit should set semantic_cache_hit=1.0, llm_used=0.0."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await self._run_handle_query(mock_config, CACHE_HIT_RESULT, mock_lf)

        scores = {
            call.kwargs["name"]: call.kwargs["value"]
            for call in mock_lf.score_current_trace.call_args_list
        }
        assert scores["semantic_cache_hit"] == 1.0
        assert scores["llm_used"] == 0.0
        assert scores["rerank_applied"] == 0.0
        assert scores["results_count"] == 0.0

    @pytest.mark.asyncio
    async def test_score_values_chitchat(self, mock_config):
        """Chitchat should set query_type=0, no LLM, no results."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await self._run_handle_query(mock_config, CHITCHAT_RESULT, mock_lf)

        scores = {
            call.kwargs["name"]: call.kwargs["value"]
            for call in mock_lf.score_current_trace.call_args_list
        }
        # CHITCHAT → 0
        assert scores["query_type"] == 0.0
        assert scores["llm_used"] == 0.0
        assert scores["results_count"] == 0.0
        assert scores["no_results"] == 1.0

    @pytest.mark.asyncio
    async def test_scores_written_even_on_null_client(self, mock_config):
        """When Langfuse disabled, _NullLangfuseClient.score_current_trace is called (no-op)."""
        from telegram_bot.observability import _NullLangfuseClient

        mock_lf = _NullLangfuseClient()

        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=FULL_PIPELINE_RESULT)

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm
            mock_prop.return_value.__enter__ = MagicMock()
            mock_prop.return_value.__exit__ = MagicMock()

            # Should not raise — NullClient silently ignores
            await bot.handle_query(_make_message())
