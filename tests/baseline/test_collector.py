"""Tests for LangfuseMetricsCollector."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

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


class TestCollectSessionMetrics:
    """Tests for per-trace session metrics computation."""

    def _make_collector(self, mock_langfuse_cls):
        """Helper: create collector with mocked Langfuse client."""
        mock_client = MagicMock()
        mock_langfuse_cls.return_value = mock_client
        collector = LangfuseMetricsCollector(
            public_key="pk-test",
            secret_key="sk-test",
            host="http://localhost:3001",
        )
        return collector, mock_client

    def _make_trace(self, trace_id="t1", session_id="s1", metadata=None, total_cost=0.05):
        """Helper: create mock trace object."""
        trace = MagicMock()
        trace.id = trace_id
        trace.session_id = session_id
        trace.metadata = metadata or {}
        trace.total_cost = total_cost
        return trace

    def _make_observation(
        self,
        obs_type="GENERATION",
        start_time=None,
        end_time=None,
        cost=0.01,
        input_tokens=100,
        output_tokens=50,
        model="gpt-4o",
    ):
        """Helper: create mock observation object."""
        obs = MagicMock()
        obs.type = obs_type
        obs.start_time = start_time or datetime(2026, 2, 12, 10, 0, 0, tzinfo=UTC)
        obs.end_time = end_time or datetime(2026, 2, 12, 10, 0, 1, 500000, tzinfo=UTC)
        obs.calculated_total_cost = cost
        obs.model = model
        usage = MagicMock()
        usage.input = input_tokens
        usage.output = output_tokens
        obs.usage = usage
        return obs

    @patch("tests.baseline.collector.Langfuse")
    def test_computes_metrics_from_traces_and_observations(self, mock_langfuse_cls):
        """Should compute p50/p95/cost/tokens from observation-level data."""
        collector, mock_client = self._make_collector(mock_langfuse_cls)

        # 2 traces, each with 1 generation observation
        traces = [
            self._make_trace("t1", "ci-abc-job-1", metadata={"cache_hit": False}),
            self._make_trace("t2", "ci-abc-job-1", metadata={"cache_hit": True}),
        ]
        traces_page = MagicMock()
        traces_page.data = traces
        traces_page.meta = MagicMock()
        traces_page.meta.next_page = None
        mock_client.api.trace.list.return_value = traces_page

        # Observations: 1s and 2s latency
        obs1 = self._make_observation(
            start_time=datetime(2026, 2, 12, 10, 0, 0, tzinfo=UTC),
            end_time=datetime(2026, 2, 12, 10, 0, 1, tzinfo=UTC),
            cost=0.01,
            input_tokens=100,
            output_tokens=50,
        )
        obs2 = self._make_observation(
            start_time=datetime(2026, 2, 12, 10, 1, 0, tzinfo=UTC),
            end_time=datetime(2026, 2, 12, 10, 1, 2, tzinfo=UTC),
            cost=0.02,
            input_tokens=200,
            output_tokens=80,
        )
        obs_page1 = MagicMock()
        obs_page1.data = [obs1]
        obs_page2 = MagicMock()
        obs_page2.data = [obs2]
        mock_client.api.observations.list.side_effect = [obs_page1, obs_page2]

        result = collector.collect_session_metrics(session_id="ci-abc-job-1")

        assert result.llm_calls == 2
        assert result.total_cost_usd == pytest.approx(0.03)
        assert result.llm_tokens_input == 300
        assert result.llm_tokens_output == 130
        # p50 of [1000, 2000] = 1500ms, p95 ≈ 1950ms
        assert result.llm_latency_p50_ms == pytest.approx(1500.0)
        assert result.llm_latency_p95_ms > 1800.0
        # 1 hit, 1 miss → 50%
        assert result.cache_hit_rate == pytest.approx(0.5)
        assert result.cache_hits == 1
        assert result.cache_misses == 1
        assert result.trace_count == 2

    @patch("tests.baseline.collector.Langfuse")
    def test_handles_none_end_time(self, mock_langfuse_cls):
        """Should skip observations with None end_time for latency."""
        collector, mock_client = self._make_collector(mock_langfuse_cls)

        traces = [self._make_trace("t1", "s1", metadata={"cache_hit": False})]
        traces_page = MagicMock()
        traces_page.data = traces
        traces_page.meta = MagicMock()
        traces_page.meta.next_page = None
        mock_client.api.trace.list.return_value = traces_page

        # One observation with None end_time
        obs = self._make_observation(cost=0.01, input_tokens=100, output_tokens=50)
        obs.end_time = None
        obs_page = MagicMock()
        obs_page.data = [obs]
        mock_client.api.observations.list.return_value = obs_page

        result = collector.collect_session_metrics(session_id="s1")

        # Latency should be 0 (no valid observations)
        assert result.llm_latency_p50_ms == 0.0
        assert result.llm_latency_p95_ms == 0.0
        # Cost/tokens still counted
        assert result.total_cost_usd == pytest.approx(0.01)
        assert result.llm_tokens_input == 100

    @patch("tests.baseline.collector.Langfuse")
    def test_handles_none_cost_and_usage(self, mock_langfuse_cls):
        """Should treat None cost as 0 and None usage as 0 tokens."""
        collector, mock_client = self._make_collector(mock_langfuse_cls)

        traces = [self._make_trace("t1", "s1", metadata={})]
        traces_page = MagicMock()
        traces_page.data = traces
        traces_page.meta = MagicMock()
        traces_page.meta.next_page = None
        mock_client.api.trace.list.return_value = traces_page

        obs = self._make_observation()
        obs.calculated_total_cost = None
        obs.usage = None
        obs_page = MagicMock()
        obs_page.data = [obs]
        mock_client.api.observations.list.return_value = obs_page

        result = collector.collect_session_metrics(session_id="s1")

        assert result.total_cost_usd == 0.0
        assert result.llm_tokens_input == 0
        assert result.llm_tokens_output == 0

    @patch("tests.baseline.collector.Langfuse")
    def test_empty_traces_returns_zero_metrics(self, mock_langfuse_cls):
        """Should return zero metrics when no traces found."""
        collector, mock_client = self._make_collector(mock_langfuse_cls)

        traces_page = MagicMock()
        traces_page.data = []
        traces_page.meta = MagicMock()
        traces_page.meta.next_page = None
        mock_client.api.trace.list.return_value = traces_page

        result = collector.collect_session_metrics(session_id="nonexistent")

        assert result.trace_count == 0
        assert result.llm_calls == 0
        assert result.total_cost_usd == 0.0
        assert result.llm_latency_p50_ms == 0.0
        assert result.cache_hit_rate == 0.0

    @patch("tests.baseline.collector.Langfuse")
    def test_filters_by_tag(self, mock_langfuse_cls):
        """Should pass tags to trace.list when filtering by tag."""
        collector, mock_client = self._make_collector(mock_langfuse_cls)

        traces_page = MagicMock()
        traces_page.data = []
        traces_page.meta = MagicMock()
        traces_page.meta.next_page = None
        mock_client.api.trace.list.return_value = traces_page

        collector.collect_session_metrics(tag="main-latest")

        mock_client.api.trace.list.assert_called_once()
        call_kwargs = mock_client.api.trace.list.call_args
        assert call_kwargs.kwargs.get("tags") == ["main-latest"]

    @patch("tests.baseline.collector.Langfuse")
    def test_requires_session_or_tag(self, mock_langfuse_cls):
        """Should raise ValueError when neither session_id nor tag provided."""
        collector, _mock_client = self._make_collector(mock_langfuse_cls)

        with pytest.raises(ValueError, match="session_id or tag"):
            collector.collect_session_metrics()
