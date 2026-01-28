"""Tests for BaselineManager."""

from datetime import datetime
from unittest.mock import Mock

from tests.baseline.manager import BaselineManager, BaselineSnapshot


class TestBaselineSnapshot:
    """Test BaselineSnapshot dataclass."""

    def test_create_snapshot(self):
        """Should create snapshot with all fields."""
        snapshot = BaselineSnapshot(
            timestamp=datetime(2026, 1, 28, 12, 0, 0),
            tag="smoke-v1.0.0",
            session_id="session-123",
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=350.0,
            full_rag_latency_p95_ms=2500.0,
            total_cost_usd=0.0523,
            llm_tokens_input=12000,
            llm_tokens_output=3000,
            llm_calls=150,
            voyage_embed_calls=150,
            voyage_rerank_calls=75,
            cache_hit_rate=0.65,
            cache_hits=98,
            cache_misses=52,
        )

        assert snapshot.tag == "smoke-v1.0.0"
        assert snapshot.llm_latency_p95_ms == 350.0
        assert snapshot.cache_hit_rate == 0.65


class TestBaselineManager:
    """Test BaselineManager functionality."""

    def test_compare_passes_within_thresholds(self):
        """Should pass when metrics within thresholds."""
        collector = Mock()
        manager = BaselineManager(collector=collector)

        baseline = BaselineSnapshot(
            timestamp=datetime(2026, 1, 27),
            tag="baseline",
            session_id="s1",
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=350.0,
            full_rag_latency_p95_ms=2500.0,
            total_cost_usd=0.05,
            llm_tokens_input=10000,
            llm_tokens_output=2500,
            llm_calls=100,
            voyage_embed_calls=100,
            voyage_rerank_calls=50,
            cache_hit_rate=0.60,
            cache_hits=60,
            cache_misses=40,
        )

        current = BaselineSnapshot(
            timestamp=datetime(2026, 1, 28),
            tag="current",
            session_id="s2",
            llm_latency_p50_ms=160.0,  # +6% OK
            llm_latency_p95_ms=380.0,  # +8% OK (threshold 20%)
            full_rag_latency_p95_ms=2700.0,  # +8% OK
            total_cost_usd=0.052,  # +4% OK (threshold 10%)
            llm_tokens_input=10500,
            llm_tokens_output=2600,
            llm_calls=102,  # +2% OK
            voyage_embed_calls=105,
            voyage_rerank_calls=52,
            cache_hit_rate=0.58,  # -2% OK (threshold 10%)
            cache_hits=58,
            cache_misses=42,
        )

        passed, regressions = manager.compare(current, baseline)

        assert passed is True
        assert len(regressions) == 0

    def test_compare_fails_latency_regression(self):
        """Should fail when latency exceeds threshold."""
        collector = Mock()
        manager = BaselineManager(collector=collector)

        baseline = BaselineSnapshot(
            timestamp=datetime(2026, 1, 27),
            tag="baseline",
            session_id="s1",
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=350.0,
            full_rag_latency_p95_ms=2500.0,
            total_cost_usd=0.05,
            llm_tokens_input=10000,
            llm_tokens_output=2500,
            llm_calls=100,
            voyage_embed_calls=100,
            voyage_rerank_calls=50,
            cache_hit_rate=0.60,
            cache_hits=60,
            cache_misses=40,
        )

        current = BaselineSnapshot(
            timestamp=datetime(2026, 1, 28),
            tag="current",
            session_id="s2",
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=500.0,  # +43% FAIL (threshold 20%)
            full_rag_latency_p95_ms=2500.0,
            total_cost_usd=0.05,
            llm_tokens_input=10000,
            llm_tokens_output=2500,
            llm_calls=100,
            voyage_embed_calls=100,
            voyage_rerank_calls=50,
            cache_hit_rate=0.60,
            cache_hits=60,
            cache_misses=40,
        )

        passed, regressions = manager.compare(current, baseline)

        assert passed is False
        assert len(regressions) == 1
        assert "latency" in regressions[0].lower()

    def test_compare_fails_cache_drop(self):
        """Should fail when cache hit rate drops significantly."""
        collector = Mock()
        manager = BaselineManager(collector=collector)

        baseline = BaselineSnapshot(
            timestamp=datetime(2026, 1, 27),
            tag="baseline",
            session_id="s1",
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=350.0,
            full_rag_latency_p95_ms=2500.0,
            total_cost_usd=0.05,
            llm_tokens_input=10000,
            llm_tokens_output=2500,
            llm_calls=100,
            voyage_embed_calls=100,
            voyage_rerank_calls=50,
            cache_hit_rate=0.70,
            cache_hits=70,
            cache_misses=30,
        )

        current = BaselineSnapshot(
            timestamp=datetime(2026, 1, 28),
            tag="current",
            session_id="s2",
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=350.0,
            full_rag_latency_p95_ms=2500.0,
            total_cost_usd=0.05,
            llm_tokens_input=10000,
            llm_tokens_output=2500,
            llm_calls=100,
            voyage_embed_calls=100,
            voyage_rerank_calls=50,
            cache_hit_rate=0.45,  # -25% FAIL (threshold 10%)
            cache_hits=45,
            cache_misses=55,
        )

        passed, regressions = manager.compare(current, baseline)

        assert passed is False
        assert any("cache" in r.lower() for r in regressions)
