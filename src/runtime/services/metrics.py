"""Pipeline metric events for the RAG bot via structured JSON logs.

DEPS-OBS3 removes the monolith's in-process Prometheus registry.  The two
helpers here emit low-cardinality product events through
:func:`src.utils.product_events.log_event`.  External scraping/aggregation
can consume the JSON logs instead of importing a process-local metrics
registry.  The legacy ``record_counter_metric`` shim and ``PipelineMetrics``
singleton proxy were removed in #3331; call these functions directly.
"""

from __future__ import annotations

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


__all__ = [
    "record_pipeline_event",
    "record_pipeline_latency",
]
