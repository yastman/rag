# tests/unit/services/test_pipeline_metrics.py
"""Tests for PipelineMetrics: rolling-window p50/p95 tracking."""

import pytest

from telegram_bot.services.metrics import PipelineMetrics


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset singleton before and after each test."""
    PipelineMetrics.reset()
    yield
    PipelineMetrics.reset()


class TestSingleton:
    """Test PipelineMetrics singleton pattern."""

    def test_get_returns_same_instance(self):
        """get() always returns the same instance."""
        m1 = PipelineMetrics.get()
        m2 = PipelineMetrics.get()
        assert m1 is m2

    def test_reset_creates_new_instance(self):
        """reset() clears the singleton so get() creates a new one."""
        m1 = PipelineMetrics.get()
        PipelineMetrics.reset()
        m2 = PipelineMetrics.get()
        assert m1 is not m2


class TestRecord:
    """Test record() timing storage."""

    def test_record_single_value(self):
        """Single record appears in stats."""
        m = PipelineMetrics.get()
        m.record("embed_dense", 42.5)
        stats = m.get_stats()
        assert "embed_dense" in stats["timings"]
        assert stats["timings"]["embed_dense"]["count"] == 1
        assert stats["timings"]["embed_dense"]["last"] == 42.5

    def test_record_multiple_values(self):
        """Multiple records tracked with correct count."""
        m = PipelineMetrics.get()
        for i in range(10):
            m.record("rerank", float(i))
        stats = m.get_stats()
        assert stats["timings"]["rerank"]["count"] == 10

    def test_record_different_stages(self):
        """Different stages tracked independently."""
        m = PipelineMetrics.get()
        m.record("embed", 10.0)
        m.record("search", 20.0)
        stats = m.get_stats()
        assert "embed" in stats["timings"]
        assert "search" in stats["timings"]

    def test_single_value_p50_p95_equal(self):
        """With one value, p50 and p95 are the same."""
        m = PipelineMetrics.get()
        m.record("stage", 100.0)
        stats = m.get_stats()
        t = stats["timings"]["stage"]
        assert t["p50"] == t["p95"] == 100.0


class TestInc:
    """Test inc() counter."""

    def test_inc_default(self):
        """inc() increments by 1 by default."""
        m = PipelineMetrics.get()
        m.inc("cache_hit")
        m.inc("cache_hit")
        stats = m.get_stats()
        assert stats["counters"]["cache_hit"] == 2

    def test_inc_custom_amount(self):
        """inc() supports custom amount."""
        m = PipelineMetrics.get()
        m.inc("tokens", 150)
        m.inc("tokens", 200)
        stats = m.get_stats()
        assert stats["counters"]["tokens"] == 350

    def test_inc_new_counter_starts_at_zero(self):
        """New counter starts from 0 + amount."""
        m = PipelineMetrics.get()
        m.inc("new_counter", 5)
        stats = m.get_stats()
        assert stats["counters"]["new_counter"] == 5


class TestObserve:
    """Test observe() named observations."""

    def test_observe_single(self):
        """Single observation appears in stats."""
        m = PipelineMetrics.get()
        m.observe("cache_distance", 0.12)
        stats = m.get_stats()
        assert "cache_distance" in stats["observations"]
        obs = stats["observations"]["cache_distance"]
        assert obs["count"] == 1
        assert obs["last"] == 0.12

    def test_observe_multiple_values(self):
        """Multiple observations tracked correctly."""
        m = PipelineMetrics.get()
        for v in [0.1, 0.2, 0.3, 0.4, 0.5]:
            m.observe("distance", v)
        stats = m.get_stats()
        assert stats["observations"]["distance"]["count"] == 5
        assert stats["observations"]["distance"]["last"] == 0.5

    def test_observe_rounds_to_4_decimals(self):
        """Observations are rounded to 4 decimal places."""
        m = PipelineMetrics.get()
        m.observe("score", 0.123456789)
        stats = m.get_stats()
        assert stats["observations"]["score"]["p50"] == 0.1235


class TestIncQueries:
    """Test inc_queries() counter."""

    def test_inc_queries_returns_new_count(self):
        """inc_queries returns the new query count."""
        m = PipelineMetrics.get()
        assert m.inc_queries() == 1
        assert m.inc_queries() == 2
        assert m.inc_queries() == 3

    def test_inc_queries_reflected_in_stats(self):
        """Query count shows in get_stats()."""
        m = PipelineMetrics.get()
        m.inc_queries()
        m.inc_queries()
        stats = m.get_stats()
        assert stats["query_count"] == 2


class TestGetStats:
    """Test get_stats() comprehensive output."""

    def test_empty_stats(self):
        """Fresh metrics return valid empty structure."""
        m = PipelineMetrics.get()
        stats = m.get_stats()
        assert stats["query_count"] == 0
        assert stats["uptime_s"] >= 0
        assert stats["timings"] == {}
        assert stats["counters"] == {}
        assert stats["observations"] == {}

    def test_p50_p95_with_enough_values(self):
        """With enough values, p50 and p95 are calculated correctly."""
        m = PipelineMetrics.get()
        # Record 100 values: 1..100
        for i in range(1, 101):
            m.record("latency", float(i))
        stats = m.get_stats()
        t = stats["timings"]["latency"]
        assert t["count"] == 100
        # p50 should be around 50, p95 around 95
        assert 45 <= t["p50"] <= 55
        assert 90 <= t["p95"] <= 100


class TestFormatText:
    """Test format_text() human-readable output."""

    def test_empty_format(self):
        """Empty metrics produce header only."""
        m = PipelineMetrics.get()
        text = m.format_text()
        assert "Pipeline Metrics" in text
        assert "n=0" in text

    def test_format_with_data(self):
        """Format includes timings, counters, observations."""
        m = PipelineMetrics.get()
        m.inc_queries()
        m.record("embed", 42.0)
        m.inc("cache_hit")
        m.observe("distance", 0.15)
        text = m.format_text()
        assert "embed" in text
        assert "cache_hit" in text
        assert "distance" in text
        assert "n=1" in text


class TestLogSummary:
    """Test log_summary() structured logging."""

    def test_logs_json(self, caplog):
        """log_summary outputs JSON to logger."""
        import logging

        m = PipelineMetrics.get()
        m.inc_queries()
        m.record("test_stage", 10.0)
        with caplog.at_level(logging.INFO, logger="telegram_bot.services.metrics"):
            m.log_summary()
        assert "Pipeline metrics" in caplog.text
        assert "query_count" in caplog.text
