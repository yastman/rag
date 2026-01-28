"""Tests for LangfuseMetricsCollector."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from tests.baseline.collector import LangfuseMetricsCollector


class TestLangfuseMetricsCollector:
    """Test LangfuseMetricsCollector functionality."""

    def test_init_creates_client(self):
        """Should initialize Langfuse client with credentials."""
        with patch("tests.baseline.collector.Langfuse") as mock_langfuse:
            LangfuseMetricsCollector(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
            )
            mock_langfuse.assert_called_once_with(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
            )

    def test_get_daily_metrics_calls_api(self):
        """Should call Langfuse daily metrics API."""
        with patch("tests.baseline.collector.Langfuse") as mock_langfuse:
            mock_client = MagicMock()
            mock_langfuse.return_value = mock_client
            mock_client.api.metrics_daily.get.return_value = {"data": []}

            collector = LangfuseMetricsCollector(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
            )

            from_ts = datetime(2026, 1, 28, 0, 0, 0)
            to_ts = datetime(2026, 1, 28, 23, 59, 59)

            result = collector.get_daily_metrics(from_ts, to_ts)

            mock_client.api.metrics_daily.get.assert_called_once()
            assert result == {"data": []}

    def test_get_latency_metrics_uses_v2_api(self):
        """Should use v2 metrics API for latency percentiles."""
        with patch("tests.baseline.collector.Langfuse") as mock_langfuse:
            mock_client = MagicMock()
            mock_langfuse.return_value = mock_client
            mock_client.api.metrics_v_2.get.return_value = {"data": []}

            collector = LangfuseMetricsCollector(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
            )

            from_ts = datetime(2026, 1, 28, 0, 0, 0)
            to_ts = datetime(2026, 1, 28, 23, 59, 59)

            collector.get_latency_metrics(from_ts, to_ts)

            mock_client.api.metrics_v_2.get.assert_called_once()

    def test_get_trace_count_filters_by_name(self):
        """Should filter traces by name."""
        with patch("tests.baseline.collector.Langfuse") as mock_langfuse:
            mock_client = MagicMock()
            mock_langfuse.return_value = mock_client
            mock_client.api.metrics.metrics.return_value = MagicMock(
                data=[{"name": "smoke-test", "count_count": "42"}]
            )

            collector = LangfuseMetricsCollector(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
            )

            count = collector.get_trace_count(
                from_ts=datetime(2026, 1, 28),
                to_ts=datetime(2026, 1, 29),
                trace_name="smoke-test",
            )

            assert count == 42
