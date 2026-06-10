"""Pipeline metric events for the RAG bot via structured JSON logs.

DEPS-OBS3 removes the monolith's in-process Prometheus registry.  The public
helpers remain as a compatibility surface for existing call sites, but they now
emit low-cardinality product events through :func:`src.utils.product_events.log_event`.
External scraping/aggregation can consume the JSON logs instead of importing a
process-local metrics registry.
"""

from __future__ import annotations

import threading

from src.utils.product_events import log_event


def record_pipeline_event(event: str, amount: int = 1, *, request_id: str = "") -> None:
    """Record a low-cardinality pipeline counter as a structured log event."""
    if amount <= 0:
        return
    log_event(
        "pipeline_counter",
        request_id=request_id,
        metric_name=event,
        metric_value=amount,
        count=amount,
    )


def record_pipeline_latency(stage: str, seconds: float, *, request_id: str = "") -> None:
    """Record a pipeline-stage latency observation as a structured log event."""
    latency_ms = seconds * 1000.0
    log_event(
        "pipeline_latency",
        request_id=request_id,
        stage=stage,
        metric_name=f"pipeline.{stage}.latency_ms",
        metric_value=latency_ms,
        latency_ms=latency_ms,
    )


def record_counter_metric(name: str, value: int = 1, *, request_id: str = "") -> None:
    """Backward-compatible counter helper routed to structured logs."""
    record_pipeline_event(name, value, request_id=request_id)


class PipelineMetrics:
    """Singleton facade preserving existing ``record``/``inc`` call sites."""

    _instance: PipelineMetrics | None = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> PipelineMetrics:
        """Return the singleton instance, creating it on first use."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton facade for tests."""
        with cls._lock:
            cls._instance = None

    def record(self, stage: str, duration_ms: float, *, request_id: str = "") -> None:
        """Record a stage timing in milliseconds."""
        record_pipeline_latency(stage, duration_ms / 1000.0, request_id=request_id)

    def inc(self, counter: str, amount: int = 1, *, request_id: str = "") -> None:
        """Increment a named counter as a structured log event."""
        record_pipeline_event(counter, amount, request_id=request_id)


__all__ = [
    "PipelineMetrics",
    "record_counter_metric",
    "record_pipeline_event",
    "record_pipeline_latency",
]
