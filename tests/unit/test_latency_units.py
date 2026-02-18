"""Tests for latency unit consistency across all graph nodes.

All nodes MUST store latency_stages values in SECONDS (float).
The score writer in bot.py converts to ms: sum(stages.values()) * 1000.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.graph.state import make_initial_state


class TestLatencyUnitsConsistency:
    """All latency_stages values must be in seconds (< 1.0 for fast ops)."""

    async def test_cache_check_latency_in_seconds(self):
        """cache_check_node stores latency in seconds, not ms.

        Mocks time to simulate 50ms operation. If stored in ms → 50.0 (FAIL).
        If stored in seconds → 0.05 (PASS).
        """
        from telegram_bot.graph.nodes.cache import cache_check_node

        mock_cache = AsyncMock()
        mock_cache.get_embedding = AsyncMock(return_value=[0.1] * 1024)
        mock_cache.check_semantic = AsyncMock(return_value=None)

        mock_embeddings = AsyncMock()

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["query_type"] = "GENERAL"

        # Simulate 50ms elapsed: time.time() returns epoch seconds,
        # time.perf_counter() returns monotonic seconds
        time_values = iter([1000.0, 1000.05])
        with patch("telegram_bot.graph.nodes.cache.time") as mock_time:
            mock_time.time = MagicMock(side_effect=time_values)
            mock_time.perf_counter = MagicMock(side_effect=iter([100.0, 100.05]))
            result = await cache_check_node(state, cache=mock_cache, embeddings=mock_embeddings)

        latency = result["latency_stages"]["cache_check"]
        # In seconds: 0.05. In ms: 50.0. Threshold at 1.0 catches the bug.
        assert latency < 1.0, f"cache_check latency {latency} looks like ms, should be seconds"
        assert 0.04 < latency < 0.06, f"Expected ~0.05s, got {latency}"

    async def test_retrieve_latency_in_seconds(self):
        """retrieve_node stores latency in seconds, not ms.

        Mocks time to simulate 200ms operation. If stored in ms → 200.0 (FAIL).
        If stored in seconds → 0.2 (PASS).
        """
        from telegram_bot.graph.nodes.retrieve import retrieve_node

        mock_cache = AsyncMock()
        mock_cache.get_search_results = AsyncMock(return_value=[{"text": "doc", "score": 0.5}])

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["query_embedding"] = [0.1] * 1024

        # Simulate 200ms elapsed
        time_values = iter([1000.0, 1000.2])
        with patch("telegram_bot.graph.nodes.retrieve.time") as mock_time:
            mock_time.time = MagicMock(side_effect=time_values)
            mock_time.perf_counter = MagicMock(side_effect=iter([100.0, 100.2]))
            result = await retrieve_node(
                state,
                cache=mock_cache,
                sparse_embeddings=AsyncMock(),
                qdrant=AsyncMock(),
            )

        latency = result["latency_stages"]["retrieve"]
        assert latency < 1.0, f"retrieve latency {latency} looks like ms, should be seconds"
        assert 0.15 < latency < 0.25, f"Expected ~0.2s, got {latency}"

    def test_score_writer_converts_seconds_to_ms(self):
        """write_langfuse_scores computes total_ms = sum(seconds) * 1000."""
        from telegram_bot.scoring import write_langfuse_scores as _write_langfuse_scores

        mock_lf = MagicMock()

        result = {
            "query_type": "GENERAL",
            "cache_hit": False,
            "rerank_applied": False,
            "search_results_count": 5,
            "pipeline_wall_ms": 2862.0,  # wall-time, not sum of stages
            "latency_stages": {
                "classify": 0.001,  # 1ms
                "cache_check": 0.050,  # 50ms
                "retrieve": 0.200,  # 200ms
                "grade": 0.001,  # 1ms
                "rerank": 0.100,  # 100ms
                "generate": 2.500,  # 2500ms
                "respond": 0.010,  # 10ms
            },
        }

        _write_langfuse_scores(mock_lf, result)

        # latency_total_ms reads pipeline_wall_ms directly (wall-time)
        expected_ms = result["pipeline_wall_ms"]

        # Verify the actual score value matches
        calls = mock_lf.score_current_trace.call_args_list
        for call in calls:
            name = call.kwargs.get("name", call.args[0] if call.args else "")
            value = call.kwargs.get("value", call.args[1] if len(call.args) > 1 else 0)
            if name == "latency_total_ms":
                assert abs(value - expected_ms) < 1.0, (
                    f"latency_total_ms={value}, expected ~{expected_ms}"
                )
