"""Pipeline metrics for the RAG bot — SDK-native via prometheus_client (canonical home, #2047).

Moved from ``telegram_bot/services/metrics.py`` as part of the
reverse-layering fix tracked under #1948 / #2047 / #2049. The legacy
``telegram_bot.services.metrics`` module is kept as a thin re-export so
existing imports across the test suite, ``telegram_bot/`` internals,
and external consumers continue to work without churn.

This module is the canonical observability surface for RAG pipeline
latency and event counts. It exports:

* ``pipeline_latency_seconds`` — a module-level
  :class:`prometheus_client.Histogram` with a single ``stage`` label
  (matching the legacy stage keys: ``retrieve``, ``rerank``,
  ``generate``). Registered with the default ``prometheus_client.REGISTRY``
  so the ASGI ``/metrics`` mount (#1648 slice 4/4) can scrape it
  without any extra wiring.

* ``record_pipeline_latency(stage, seconds)`` — the canonical SDK-native
  latency recording API.

* ``rag_pipeline_events_total`` — a module-level
  :class:`prometheus_client.Counter` with a single ``event`` label,
  replacing log-as-metric events previously emitted in
  ``rag_pipeline.py`` and ``qdrant.py``.

* ``record_pipeline_event(event, amount)`` — the canonical SDK-native
  event recording API.

* ``PipelineMetrics`` — slim singleton facade. Provides ``record(stage, ms)``
  (delegates to :func:`record_pipeline_latency` after ms→s conversion) and
  ``inc(counter, amount)`` (delegates to :func:`record_pipeline_event`).
  Existing call-sites continue to work; the deprecated rolling-window
  surface (``get_stats`` / ``format_text`` / ``log_summary`` / ``observe`` /
  ``inc_queries``) was removed in #2058 once the admin ``/metrics``
  Telegram command switched to ``prometheus_client.generate_latest``.

Context7 baseline (``/prometheus/client_python``):

  * ``Histogram(name, documentation, labelnames=(...,))`` — registered
    against ``prometheus_client.REGISTRY`` by default.
  * ``Counter(name, documentation, labelnames=(...,))`` — registered
    against ``prometheus_client.REGISTRY`` by default.
  * ``Counter.labels(event="name").inc()`` increments the counter.

Content was rephrased for compliance with licensing restrictions.

Refs #1648 #2058.
"""

from __future__ import annotations

import logging
import threading

from prometheus_client import Counter, Histogram


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SDK-native module-level Histogram (#1648 slice 2/4).
# ---------------------------------------------------------------------------

# We pin the name with the ``_seconds`` suffix per Prometheus naming
# guidelines and rely on the package-wide default REGISTRY (no custom
# ``CollectorRegistry`` — see contract test in
# ``tests/contract/test_no_custom_metrics_registry_contract.py``).
pipeline_latency_seconds: Histogram = Histogram(
    "pipeline_latency_seconds",
    "RAG pipeline stage latency in seconds (retrieve, rerank, generate, ...).",
    labelnames=("stage",),
    # Default buckets are intentionally not overridden: they cover
    # web/RPC latencies (5 ms .. 10 s) which match the observed
    # distribution of every existing pipeline stage.
)

# ---------------------------------------------------------------------------
# SDK-native module-level Counter (#1648 slice 3/4).
# ---------------------------------------------------------------------------

# Single ``event`` label keeps cardinality low.  Known event values:
#   colbert_rerank_attempted, topic_filter_fallback, retrieval_zero_docs,
#   score_gap_confident   (from rag_pipeline.py)
#   colbert_rerank_empty, colbert_fallback_to_rrf   (from qdrant.py)
#   cache_hit, cache_miss   (from graph/nodes/cache.py)
#
# Context7 baseline (``/prometheus/client_python``):
#   Counter(name, documentation, labelnames=('label',))
#   counter.labels(label='value').inc()
#
# Content was rephrased for compliance with licensing restrictions.
# Refs #1648.
rag_pipeline_events_total: Counter = Counter(
    "rag_pipeline_events_total",
    "RAG pipeline event counter (cache_hit, cache_miss, colbert_rerank_attempted, etc.).",
    labelnames=("event",),
)


def record_pipeline_event(event: str, amount: int = 1) -> None:
    """Record one pipeline event by incrementing the labeled Counter.

    This is the SDK-native API. New call-sites must use this directly;
    existing ``PipelineMetrics.get().inc(name)`` call-sites are
    backward-compatible because the facade delegates here.

    Args:
        event: Event label value (e.g. ``"colbert_rerank_attempted"``,
            ``"retrieval_zero_docs"``).  Cardinality must stay low.
        amount: Increment amount (default 1, must be positive to record).
    """
    if amount <= 0:
        return
    rag_pipeline_events_total.labels(event=event).inc(amount)


def record_pipeline_latency(stage: str, seconds: float) -> None:
    """Record one pipeline-stage latency observation in seconds.

    This is the SDK-native API. New call-sites must use this directly;
    existing ``PipelineMetrics.get().record(stage, ms)`` call-sites
    continue to work because the facade routes through here after
    ms→s conversion.

    Args:
        stage: Pipeline stage label (e.g. ``"retrieve"``, ``"rerank"``,
            ``"generate"``). Cardinality must stay low.
        seconds: Observed latency in seconds.
    """
    pipeline_latency_seconds.labels(stage=stage).observe(seconds)


# ---------------------------------------------------------------------------
# Backward-compat facade — preserves existing call-sites unchanged.
# ---------------------------------------------------------------------------


def record_counter_metric(name: str, value: int = 1) -> None:
    """Record a named counter metric through the bot metrics registry.

    Legacy compatibility shim (#2056). Existing call-sites that still
    import ``record_counter_metric`` route through here and are forwarded
    to :func:`record_pipeline_event` so the SDK-native Counter receives
    the increment.
    """
    if value <= 0:
        return
    record_pipeline_event(name, value)


class PipelineMetrics:
    """Singleton facade over the SDK-native Histogram/Counter surfaces.

    Slim version (#2058): the rolling-window p50/p95 in-memory tracker
    was removed once the admin ``/metrics`` Telegram command migrated
    to ``prometheus_client.generate_latest``. Only the ``record`` and
    ``inc`` methods remain so existing call-sites keep working.

    Thread-safe singleton via :meth:`get`.

    Usage::

        metrics = PipelineMetrics.get()
        metrics.record("rerank", 42.5)  # ms; observes pipeline_latency_seconds
        record_pipeline_latency("rerank", 0.0425)  # SDK-native, in seconds
    """

    _instance: PipelineMetrics | None = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> PipelineMetrics:
        """Return the singleton instance (create on first call)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing).

        Note: this only resets the singleton facade. The SDK-native
        :data:`pipeline_latency_seconds` Histogram and
        :data:`rag_pipeline_events_total` Counter are module-level and
        persist across resets; tests that need clean Prometheus state
        must call ``pipeline_latency_seconds.clear()`` and
        ``rag_pipeline_events_total.clear()``.
        """
        with cls._lock:
            cls._instance = None

    def record(self, stage: str, duration_ms: float) -> None:
        """Record a stage timing in milliseconds.

        Routes the observation to the SDK-native Histogram after ms→s
        conversion. ``stage`` cardinality must stay low (one of the
        small set of pipeline stage names).
        """
        record_pipeline_latency(stage, duration_ms / 1000.0)

    def inc(self, counter: str, amount: int = 1) -> None:
        """Increment a named counter via the SDK-native Counter.

        ``counter`` cardinality must stay low (one of the small set
        of known event names — see ``rag_pipeline_events_total``).
        """
        record_pipeline_event(counter, amount)


__all__ = [
    "PipelineMetrics",
    "pipeline_latency_seconds",
    "rag_pipeline_events_total",
    "record_counter_metric",
    "record_pipeline_event",
    "record_pipeline_latency",
]
