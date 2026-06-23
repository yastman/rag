"""Tests for SDK-native pipeline latency Histogram (#1648 slice 2/4).

This module asserts the SDK-native observability migration:

  * A module-level ``prometheus_client.Histogram`` named
    ``pipeline_latency_seconds`` is exported from
    ``telegram_bot.services.metrics``.
  * It uses the default ``prometheus_client.REGISTRY`` (no custom registry).
  * It carries a single ``stage`` label so cardinality matches the
    pipeline stage keys (``retrieve``, ``rerank``, ``generate``).
  * The new public function ``record_pipeline_latency(stage, seconds)``
    delegates to ``Histogram.observe(seconds)`` for the matching label.
  * The slim ``PipelineMetrics.get().record(stage, duration_ms)``
    facade continues to work but routes through the Histogram (after
    ms→s conversion).

The deprecated rolling-window p50/p95 surface
(``get_stats`` / ``format_text`` / ``log_summary`` / ``observe`` /
``inc_queries``) was removed in #2058 once the admin ``/metrics``
Telegram command migrated to ``prometheus_client.generate_latest``.

Refs #1648 #2058.
"""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY, Histogram

from telegram_bot.services.metrics import (
    PipelineMetrics,
    pipeline_latency_seconds,
    record_pipeline_latency,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_histogram_children():
    """Clear histogram label-children between tests.

    The Histogram object itself is module-level and registered exactly
    once with ``prometheus_client.REGISTRY``. We do NOT recreate it
    (that would raise a ``ValueError: Duplicated timeseries``). Instead
    we drop all per-label children so each test starts from zero counts.
    """
    pipeline_latency_seconds.clear()
    PipelineMetrics.reset()
    yield
    pipeline_latency_seconds.clear()
    PipelineMetrics.reset()


# ---------------------------------------------------------------------------
# Module-level Histogram
# ---------------------------------------------------------------------------


class TestHistogramDefinition:
    """Module-level Histogram exists with the right shape."""

    def test_pipeline_latency_seconds_is_histogram_instance(self):
        assert isinstance(pipeline_latency_seconds, Histogram), (
            "pipeline_latency_seconds must be a prometheus_client.Histogram"
        )

    def test_metric_name_uses_seconds_unit_suffix(self):
        # prometheus_client stores the registered name on ``_name``.
        # The on-the-wire name (with optional namespace/subsystem) must
        # end in ``_seconds`` so Prometheus recognises the unit.
        assert pipeline_latency_seconds._name.endswith("pipeline_latency_seconds")

    def test_labelnames_are_stage_only(self):
        # Cardinality = exactly one label, matching the legacy
        # rolling-window keys (retrieve, rerank, generate).
        assert tuple(pipeline_latency_seconds._labelnames) == ("stage",)

    def test_uses_default_registry(self):
        # The Histogram must be registered with prometheus_client.REGISTRY,
        # the package-wide default. No custom CollectorRegistry.
        # Walk the registry and assert our metric is present.
        names = {m.name for m in REGISTRY.collect()}
        assert "pipeline_latency_seconds" in names


# ---------------------------------------------------------------------------
# record_pipeline_latency()
# ---------------------------------------------------------------------------


class TestRecordPipelineLatency:
    """Public ``record_pipeline_latency(stage, seconds)`` calls Histogram.observe."""

    def test_observation_increments_count(self):
        before = (
            REGISTRY.get_sample_value("pipeline_latency_seconds_count", {"stage": "rerank"}) or 0
        )

        record_pipeline_latency("rerank", 0.042)

        after = REGISTRY.get_sample_value("pipeline_latency_seconds_count", {"stage": "rerank"})
        assert after is not None
        assert after - before == pytest.approx(1.0)

    def test_observation_accumulates_sum(self):
        record_pipeline_latency("retrieve", 0.1)
        record_pipeline_latency("retrieve", 0.2)
        record_pipeline_latency("retrieve", 0.3)

        sum_value = REGISTRY.get_sample_value("pipeline_latency_seconds_sum", {"stage": "retrieve"})
        count_value = REGISTRY.get_sample_value(
            "pipeline_latency_seconds_count", {"stage": "retrieve"}
        )

        assert count_value == pytest.approx(3.0)
        assert sum_value == pytest.approx(0.6)

    def test_different_stages_have_independent_label_children(self):
        record_pipeline_latency("retrieve", 0.05)
        record_pipeline_latency("rerank", 0.1)
        record_pipeline_latency("generate", 1.2)

        for stage, seconds in (("retrieve", 0.05), ("rerank", 0.1), ("generate", 1.2)):
            assert REGISTRY.get_sample_value(
                "pipeline_latency_seconds_count", {"stage": stage}
            ) == pytest.approx(1.0)
            assert REGISTRY.get_sample_value(
                "pipeline_latency_seconds_sum", {"stage": stage}
            ) == pytest.approx(seconds)

    def test_observation_falls_into_expected_bucket(self):
        # 0.05s should fall into the ≤0.05 bucket (one of the default buckets).
        record_pipeline_latency("retrieve", 0.05)

        # The bucket-le label is rendered as a string in the sample tuple.
        bucket_value = REGISTRY.get_sample_value(
            "pipeline_latency_seconds_bucket",
            {"stage": "retrieve", "le": "0.05"},
        )
        assert bucket_value == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Backward-compat facade — PipelineMetrics.record()
# ---------------------------------------------------------------------------


class TestPipelineMetricsRecordFacade:
    """``PipelineMetrics.get().record(stage, ms)`` ALSO observes into the Histogram.

    This preserves the API surface of the existing five call-sites in
    graph nodes (rerank.py, retrieve.py, generate_response.py, cache.py,
    bot.py) while routing observations through the SDK-native Histogram.
    """

    def test_facade_record_observes_into_histogram(self):
        before = (
            REGISTRY.get_sample_value("pipeline_latency_seconds_count", {"stage": "rerank"}) or 0
        )

        # Existing call-sites pass milliseconds; the facade must convert.
        PipelineMetrics.get().record("rerank", 42.0)

        after = REGISTRY.get_sample_value("pipeline_latency_seconds_count", {"stage": "rerank"})
        assert after - before == pytest.approx(1.0)

    def test_facade_record_converts_ms_to_seconds(self):
        # 42 ms → 0.042 s should be observed.
        PipelineMetrics.get().record("retrieve", 42.0)

        sum_value = REGISTRY.get_sample_value("pipeline_latency_seconds_sum", {"stage": "retrieve"})
        assert sum_value == pytest.approx(0.042, abs=1e-6)

    def test_facade_handles_each_known_pipeline_stage(self):
        # Cardinality contract: each existing rolling-window stage must be
        # representable as a Histogram label without error.
        for stage in ("retrieve", "rerank", "generate"):
            PipelineMetrics.get().record(stage, 100.0)

        for stage in ("retrieve", "rerank", "generate"):
            assert REGISTRY.get_sample_value(
                "pipeline_latency_seconds_count", {"stage": stage}
            ) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Deprecation of rolling p50/p95 surface
# ---------------------------------------------------------------------------


class TestRollingP50P95Removed:
    """The legacy rolling-window p50/p95 surface was removed in #2058.

    Once the admin ``/metrics`` Telegram command migrated to
    ``prometheus_client.generate_latest`` (slice 1/2 of #2058), the
    in-memory rolling-window methods became dead code. Slice 2/2
    deletes them entirely; this test pins the surface so a regression
    that re-adds them shows up in code review.
    """

    @pytest.mark.parametrize(
        "method",
        [
            "get_stats",
            "format_text",
            "log_summary",
            "observe",
            "inc_queries",
        ],
    )
    def test_deprecated_rolling_window_method_is_absent(self, method: str) -> None:
        m = PipelineMetrics.get()
        assert not hasattr(m, method), (
            f"PipelineMetrics.{method} was removed in #2058. "
            "Use the SDK-native pipeline_latency_seconds Histogram or "
            "rag_pipeline_events_total Counter instead, or scrape the "
            "Prometheus registry via prometheus_client.generate_latest()."
        )
