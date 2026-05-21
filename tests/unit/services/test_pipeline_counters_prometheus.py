"""Tests for SDK-native pipeline event Counter (***REMOVED***1648 slice 3/4).

Slice 3/4 of the observability migration replaces log-as-metric events
with a labeled ``prometheus_client.Counter`` in
``telegram_bot.services.metrics``.

Hot-path events identified during investigation:

  rag_pipeline.py (via ``record_counter_metric``):
    - ``colbert_rerank_attempted``  — ColBERT rerank path taken
    - ``topic_filter_fallback``     — retrieval relaxed from topic filter
    - ``retrieval_zero_docs``       — Qdrant returned no documents
    - ``score_gap_confident``       — grading found a confident score gap

  qdrant.py (via ``record_counter_metric``):
    - ``colbert_rerank_empty``      — ColBERT returned 0 docs
    - ``colbert_fallback_to_rrf``   — fallback from ColBERT to RRF

Context7 baseline (``/prometheus/client_python``):

    Counter(name, documentation, labelnames=('label',))
    counter.labels(label='value').inc()
    counter.labels(label='value').inc(amount)

Counter-level cardinality stays low: a single ``event`` label whose
values are the six event names above (and any future hot-path counters
added in subsequent sprints).

Refs ***REMOVED***1648.
"""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY, Counter

from telegram_bot.services.metrics import (
    PipelineMetrics,
    rag_pipeline_events_total,
    record_pipeline_event,
)


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Fixtures
***REMOVED*** ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_counter_children():
    """Clear Counter label-children between tests.

    The Counter is module-level and registered exactly once with
    ``prometheus_client.REGISTRY``. We drop only per-label children so
    each test starts from zero counts; we never recreate the Counter
    itself (that would raise ``ValueError: Duplicated timeseries``).
    """
    rag_pipeline_events_total.clear()
    PipelineMetrics.reset()
    yield
    rag_pipeline_events_total.clear()
    PipelineMetrics.reset()


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 1. Counter object exists and has the right shape
***REMOVED*** ---------------------------------------------------------------------------


class TestCounterDefinition:
    """Module-level Counter is exported with the right shape."""

    def test_rag_pipeline_counter_exists(self):
        """A module-level Counter named rag_pipeline_events_total is exported."""
        assert isinstance(rag_pipeline_events_total, Counter), (
            "rag_pipeline_events_total must be a prometheus_client.Counter"
        )

    def test_rag_pipeline_counter_metric_name(self):
        """Counter metric name base is rag_pipeline_events (prometheus_client strips _total from _name)."""
        ***REMOVED*** prometheus_client strips the ``_total`` suffix from ``._name``
        ***REMOVED*** but exposes the sample as ``rag_pipeline_events_total``.
        assert rag_pipeline_events_total._name == "rag_pipeline_events", (
            f"Expected '_name' == 'rag_pipeline_events', got '{rag_pipeline_events_total._name}'. "
            "prometheus_client strips the _total suffix from the internal _name attribute."
        )

    def test_rag_pipeline_counter_has_correct_labels(self):
        """Counter must have a single 'event' label (low cardinality)."""
        assert tuple(rag_pipeline_events_total._labelnames) == ("event",), (
            "rag_pipeline_events_total must have exactly one label: 'event'"
        )

    def test_rag_pipeline_counter_uses_default_registry(self):
        """Counter must be in prometheus_client.REGISTRY (no custom registry)."""
        ***REMOVED*** prometheus_client stores the family name without _total suffix in REGISTRY.collect()
        names = {m.name for m in REGISTRY.collect()}
        assert "rag_pipeline_events" in names, (
            "rag_pipeline_events is not in prometheus_client.REGISTRY. "
            "Do not pass a custom CollectorRegistry (see contract test)."
        )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 2. record_pipeline_event() helper
***REMOVED*** ---------------------------------------------------------------------------


class TestRecordPipelineEvent:
    """``record_pipeline_event(event)`` increments the Counter by 1."""

    def test_record_event_increments_counter(self):
        """Calling record_pipeline_event once increments _total by 1."""
        before = (
            REGISTRY.get_sample_value(
                "rag_pipeline_events_total",
                {"event": "cache_hit"},
            )
            or 0.0
        )

        record_pipeline_event("cache_hit")

        after = REGISTRY.get_sample_value(
            "rag_pipeline_events_total",
            {"event": "cache_hit"},
        )
        assert after is not None
        assert after - before == pytest.approx(1.0), (
            "record_pipeline_event('cache_hit') must increment counter by 1"
        )

    def test_multiple_calls_accumulate(self):
        """Counter is monotonically increasing across multiple calls."""
        for _ in range(3):
            record_pipeline_event("retrieval_zero_docs")

        value = REGISTRY.get_sample_value(
            "rag_pipeline_events_total",
            {"event": "retrieval_zero_docs"},
        )
        assert value == pytest.approx(3.0)

    def test_different_events_have_independent_label_children(self):
        """Each event label maps to an independent time series."""
        record_pipeline_event("colbert_rerank_attempted")
        record_pipeline_event("topic_filter_fallback")
        record_pipeline_event("topic_filter_fallback")

        colbert_val = REGISTRY.get_sample_value(
            "rag_pipeline_events_total",
            {"event": "colbert_rerank_attempted"},
        )
        topic_val = REGISTRY.get_sample_value(
            "rag_pipeline_events_total",
            {"event": "topic_filter_fallback"},
        )
        assert colbert_val == pytest.approx(1.0)
        assert topic_val == pytest.approx(2.0)

    def test_known_hot_path_events_can_be_recorded(self):
        """All six hot-path event names from the codebase must be accepted."""
        hot_path_events = [
            "colbert_rerank_attempted",
            "topic_filter_fallback",
            "retrieval_zero_docs",
            "score_gap_confident",
            "colbert_rerank_empty",
            "colbert_fallback_to_rrf",
        ]
        for event in hot_path_events:
            record_pipeline_event(event)  ***REMOVED*** must not raise

        for event in hot_path_events:
            val = REGISTRY.get_sample_value(
                "rag_pipeline_events_total",
                {"event": event},
            )
            assert val == pytest.approx(1.0), (
                f"Expected counter=1 for event '{event}', got {val}"
            )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 3. Backward-compat: PipelineMetrics.inc() still works
***REMOVED*** ---------------------------------------------------------------------------


class TestPipelineMetricsIncBackwardCompat:
    """``PipelineMetrics.get().inc(counter)`` still works and also feeds the Counter.

    Slice 3/4 must not break any existing call-site that goes through the
    deprecated facade. The facade's in-memory ``_counters`` dict is kept
    intact (slice 4/4 deletes it); additionally, each ``inc()`` call now
    also increments ``rag_pipeline_events_total`` so the event is visible
    to Prometheus scraping.
    """

    def test_existing_callers_of_PipelineMetrics_inc_still_work(self):
        """PipelineMetrics.get().inc('cache_hit') does not raise."""
        m = PipelineMetrics.get()
        m.inc("cache_hit")  ***REMOVED*** must not raise
        m.inc("cache_hit", 2)

    def test_PipelineMetrics_inc_also_feeds_prometheus_counter(self):
        """Calling PipelineMetrics.inc('cache_hit') increments rag_pipeline_events_total."""
        m = PipelineMetrics.get()
        m.inc("cache_hit")

        val = REGISTRY.get_sample_value(
            "rag_pipeline_events_total",
            {"event": "cache_hit"},
        )
        assert val is not None and val >= 1.0, (
            "PipelineMetrics.inc() must forward the event to rag_pipeline_events_total"
        )

    def test_PipelineMetrics_inc_with_amount_feeds_counter_once(self):
        """PipelineMetrics.inc('ev', amount=2) increments counter by 2."""
        m = PipelineMetrics.get()
        m.inc("cache_miss", 2)

        val = REGISTRY.get_sample_value(
            "rag_pipeline_events_total",
            {"event": "cache_miss"},
        )
        assert val == pytest.approx(2.0), (
            "PipelineMetrics.inc('cache_miss', 2) must increment counter by 2"
        )
