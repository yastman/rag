"""Pipeline metrics for the RAG bot — SDK-native via prometheus_client.

This module is the canonical observability surface for RAG pipeline
latency. It exports:

* ``pipeline_latency_seconds`` — a module-level
  :class:`prometheus_client.Histogram` with a single ``stage`` label
  (matching the legacy rolling-window keys: ``retrieve``, ``rerank``,
  ``generate``). Registered with the default ``prometheus_client.REGISTRY``
  so the planned ASGI ``/metrics`` mount in slice 4/4 can scrape it
  without any extra wiring.

* ``record_pipeline_latency(stage, seconds)`` — the canonical SDK-native
  recording API. New code must use this.

* ``PipelineMetrics`` — the legacy facade kept for backward
  compatibility (slice 2/4 of #1648). Existing call-sites
  ``PipelineMetrics.get().record(stage, ms)`` keep working unchanged;
  internally they now ALSO observe into the Histogram (after ms→s
  conversion). The rolling p50/p95 / counter / observation surface
  remains for the bot's admin ``/metrics`` Telegram command, but
  ``get_stats()`` / ``format_text()`` emit ``DeprecationWarning`` —
  slice 4/4 deletes that surface entirely.

Context7 baseline (``/prometheus/client_python``):

  * ``Histogram(name, documentation, labelnames=(...,))`` — registered
    against ``prometheus_client.REGISTRY`` by default.
  * ``Histogram.labels(stage="rerank").observe(seconds)`` records into
    the bucket containing ``seconds``, plus the ``_count`` and ``_sum``
    series.
  * Default buckets ``(.005, .01, .025, .05, .075, .1, .25, .5, .75,
    1.0, 2.5, 5.0, 7.5, 10.0, +Inf)`` are tuned for web/RPC latencies
    and cover the RAG pipeline stages well (retrieve ≈ 50–500 ms,
    rerank ≈ 50–500 ms, generate ≈ 0.5–5 s). We adopt them as-is to
    avoid premature bucket tuning; revisit per slice 4/4 once we have
    real Prometheus dashboards.

Content was rephrased for compliance with licensing restrictions.

Refs #1648.
"""

from __future__ import annotations

import json
import logging
import statistics
import threading
import time
import warnings
from collections import deque

from prometheus_client import Histogram


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
    # distribution of every existing pipeline stage. Slice 4/4 will
    # revisit bucket tuning once dashboards are in place.
)

# Rolling window size per stage — only used by the deprecated facade.
_WINDOW_SIZE = 1000

_DEPRECATION_MSG = (
    "PipelineMetrics rolling p50/p95 surface is deprecated; "
    "use prometheus_client Histogram pipeline_latency_seconds (#1648 slice 2/4). "
    "This surface is removed in slice 4/4 (ASGI /metrics mount)."
)


def record_pipeline_latency(stage: str, seconds: float) -> None:
    """Record one pipeline-stage latency observation in seconds.

    This is the SDK-native API. New call-sites must use this; existing
    ``PipelineMetrics.get().record(stage, ms)`` call-sites continue to
    work because the facade routes through here after ms→s conversion.

    Args:
        stage: Pipeline stage label (e.g. ``"retrieve"``, ``"rerank"``,
            ``"generate"``). Cardinality must stay low.
        seconds: Observed latency in seconds.
    """
    pipeline_latency_seconds.labels(stage=stage).observe(seconds)


# ---------------------------------------------------------------------------
# Backward-compat facade — preserves existing call-sites unchanged.
# ---------------------------------------------------------------------------


class PipelineMetrics:
    """Singleton pipeline metrics — backward-compat facade.

    Slice 2/4 of #1648: ``record(stage, ms)`` now ALSO observes into
    the SDK-native :data:`pipeline_latency_seconds` Histogram. The
    in-memory rolling window is retained so the bot's admin ``/metrics``
    Telegram command (which calls :meth:`format_text`) keeps working;
    the rolling-window surface is marked deprecated and is deleted in
    slice 4/4.

    Counter and observation surfaces (:meth:`inc` / :meth:`observe`)
    are out of scope for this slice — they migrate in slice 3/4
    (log-as-metric → ``prometheus_client.Counter``).

    Thread-safe via a simple lock. Stages are created on first use.

    Usage::

        metrics = PipelineMetrics.get()
        metrics.record("rerank", 42.5)  # ms; also feeds Histogram
        record_pipeline_latency("rerank", 0.0425)  # SDK-native, in seconds
    """

    _instance: PipelineMetrics | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._timings: dict[str, deque] = {}
        self._counters: dict[str, int] = {}
        self._observations: dict[str, deque] = {}
        self._query_count = 0
        self._start_time = time.monotonic()
        self._mu = threading.Lock()

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

        Note: this only resets the deprecated rolling-window facade.
        The SDK-native :data:`pipeline_latency_seconds` Histogram is
        module-level and persists across resets; tests that need a
        clean Histogram must call ``pipeline_latency_seconds.clear()``.
        """
        with cls._lock:
            cls._instance = None

    # --- Recording ---

    def record(self, stage: str, duration_ms: float) -> None:
        """Record a stage timing in milliseconds.

        Routes the observation through both surfaces:

        * SDK-native: ``pipeline_latency_seconds.labels(stage=stage).observe(duration_ms / 1000)``.
        * Legacy rolling-window: appended to the per-stage deque so
          :meth:`format_text` keeps producing output for the admin
          ``/metrics`` command. Slice 4/4 of #1648 deletes the legacy
          path.
        """
        # SDK-native side: convert ms → seconds and observe. Done first
        # so a programming error in the facade dict does not lose the
        # Prometheus signal.
        record_pipeline_latency(stage, duration_ms / 1000.0)

        # Legacy rolling-window side (deprecated, see slice 4/4).
        with self._mu:
            if stage not in self._timings:
                self._timings[stage] = deque(maxlen=_WINDOW_SIZE)
            self._timings[stage].append(duration_ms)

    def inc(self, counter: str, amount: int = 1) -> None:
        """Increment a named counter.

        Out of scope for slice 2/4. Slice 3/4 of #1648 migrates this
        surface to :class:`prometheus_client.Counter`.
        """
        with self._mu:
            self._counters[counter] = self._counters.get(counter, 0) + amount

    def observe(self, name: str, value: float) -> None:
        """Record a named observation (e.g. vector distance).

        Out of scope for slice 2/4 — this surface tracks similarity
        scores, not latency. It will be reviewed in a future slice.
        """
        with self._mu:
            if name not in self._observations:
                self._observations[name] = deque(maxlen=_WINDOW_SIZE)
            self._observations[name].append(value)

    def inc_queries(self) -> int:
        """Increment query counter and return the new value."""
        with self._mu:
            self._query_count += 1
            return self._query_count

    # --- Retrieval (DEPRECATED) ---

    def get_stats(self) -> dict:
        """Return current p50/p95 per stage, counters, and observations.

        .. deprecated:: #1648 slice 2/4
            The rolling p50/p95 surface is deprecated. Use the
            SDK-native :data:`pipeline_latency_seconds` Histogram
            directly. Slice 4/4 of #1648 (ASGI ``/metrics`` mount)
            removes this method; the Telegram admin ``/metrics``
            command will be reworked to render Histogram data instead.
        """
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        with self._mu:
            result: dict = {
                "query_count": self._query_count,
                "uptime_s": int(time.monotonic() - self._start_time),
                "timings": {},
                "counters": dict(self._counters),
                "observations": {},
            }

            for stage, values in self._timings.items():
                if len(values) >= 2:
                    quantiles = statistics.quantiles(values, n=100)
                    result["timings"][stage] = {
                        "p50": round(quantiles[49], 1),
                        "p95": round(quantiles[94], 1),
                        "count": len(values),
                        "last": round(values[-1], 1),
                    }
                elif len(values) == 1:
                    result["timings"][stage] = {
                        "p50": round(values[0], 1),
                        "p95": round(values[0], 1),
                        "count": 1,
                        "last": round(values[0], 1),
                    }

            for name, values in self._observations.items():
                if len(values) >= 2:
                    quantiles = statistics.quantiles(values, n=100)
                    result["observations"][name] = {
                        "p50": round(quantiles[49], 4),
                        "p95": round(quantiles[94], 4),
                        "count": len(values),
                        "last": round(values[-1], 4),
                    }
                elif len(values) == 1:
                    result["observations"][name] = {
                        "p50": round(values[0], 4),
                        "p95": round(values[0], 4),
                        "count": 1,
                        "last": round(values[0], 4),
                    }

            return result

    def log_summary(self) -> None:
        """Log current stats as structured JSON.

        .. deprecated:: #1648 slice 2/4
            Same migration path as :meth:`get_stats`.
        """
        # Suppress the DeprecationWarning chain triggered by the inner
        # get_stats() call so log_summary() — invoked from many places
        # in the bot today — does not flood logs with deprecation
        # frames. The warning still fires when callers reach for the
        # data directly via get_stats() / format_text().
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            stats = self.get_stats()
        logger.info("Pipeline metrics: %s", json.dumps(stats, ensure_ascii=False))

    def format_text(self) -> str:
        """Format stats as human-readable text for the admin ``/metrics`` command.

        .. deprecated:: #1648 slice 2/4
            Same migration path as :meth:`get_stats`. Slice 4/4
            replaces this with a Prometheus exposition view.
        """
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            stats = self.get_stats()
        lines = [
            f"Pipeline Metrics (n={stats['query_count']}, uptime={stats['uptime_s']}s)",
            "",
        ]

        if stats["timings"]:
            lines.append("Timings (ms):")
            for stage, t in sorted(stats["timings"].items()):
                lines.append(
                    f"  {stage:<20s}  p50={t['p50']:>7.1f}  p95={t['p95']:>7.1f}  n={t['count']}"
                )
            lines.append("")

        if stats["counters"]:
            lines.append("Counters:")
            for name, val in sorted(stats["counters"].items()):
                lines.append(f"  {name:<20s}  {val}")
            lines.append("")

        if stats["observations"]:
            lines.append("Observations:")
            for name, o in sorted(stats["observations"].items()):
                lines.append(
                    f"  {name:<20s}  p50={o['p50']:>7.4f}  p95={o['p95']:>7.4f}  n={o['count']}"
                )

        return "\n".join(lines)


__all__ = [
    "PipelineMetrics",
    "pipeline_latency_seconds",
    "record_pipeline_latency",
]
