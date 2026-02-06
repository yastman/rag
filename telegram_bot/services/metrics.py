"""Pipeline metrics for RAG bot instrumentation.

Lightweight in-memory metrics using rolling windows (deque).
No external dependencies — standard library only.
"""

import json
import logging
import statistics
import threading
import time
from collections import deque


logger = logging.getLogger(__name__)

# Rolling window size per stage
_WINDOW_SIZE = 1000


class PipelineMetrics:
    """Singleton pipeline metrics with rolling-window p50/p95 tracking.

    Thread-safe via a simple lock. Stages are created on first use.

    Usage::

        metrics = PipelineMetrics.get()
        metrics.record("embed_dense", 42.5)
        metrics.inc("cache_hit")
        metrics.observe("cache_distance", 0.12)
        stats = metrics.get_stats()
    """

    _instance: "PipelineMetrics | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._timings: dict[str, deque] = {}
        self._counters: dict[str, int] = {}
        self._observations: dict[str, deque] = {}
        self._query_count = 0
        self._start_time = time.monotonic()
        self._mu = threading.Lock()

    @classmethod
    def get(cls) -> "PipelineMetrics":
        """Return the singleton instance (create on first call)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    # --- Recording ---

    def record(self, stage: str, duration_ms: float) -> None:
        """Record a stage timing in milliseconds."""
        with self._mu:
            if stage not in self._timings:
                self._timings[stage] = deque(maxlen=_WINDOW_SIZE)
            self._timings[stage].append(duration_ms)

    def inc(self, counter: str, amount: int = 1) -> None:
        """Increment a named counter."""
        with self._mu:
            self._counters[counter] = self._counters.get(counter, 0) + amount

    def observe(self, name: str, value: float) -> None:
        """Record a named observation (e.g., vector distance)."""
        with self._mu:
            if name not in self._observations:
                self._observations[name] = deque(maxlen=_WINDOW_SIZE)
            self._observations[name].append(value)

    def inc_queries(self) -> int:
        """Increment query counter and return new value."""
        with self._mu:
            self._query_count += 1
            return self._query_count

    # --- Retrieval ---

    def get_stats(self) -> dict:
        """Return current p50/p95 per stage, counters, and observations."""
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
        """Log current stats as structured JSON."""
        stats = self.get_stats()
        logger.info("Pipeline metrics: %s", json.dumps(stats, ensure_ascii=False))

    def format_text(self) -> str:
        """Format stats as human-readable text for /metrics command."""
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
