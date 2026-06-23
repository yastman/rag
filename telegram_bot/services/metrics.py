"""Pipeline metrics for the RAG bot — back-compat re-export.

The canonical implementation moved to :mod:`src.runtime.services.metrics`
as part of the reverse-layering fix (#2047 / #2049). This module remains
so that existing ``from telegram_bot.services.metrics import …`` imports
across ``telegram_bot/``, ``tests/``, and the rest of the repo continue
to work unchanged.
"""

from src.runtime.services.metrics import (
    PipelineMetrics,
    pipeline_latency_seconds,
    rag_pipeline_events_total,
    record_counter_metric,
    record_pipeline_event,
    record_pipeline_latency,
)


__all__ = [
    "PipelineMetrics",
    "pipeline_latency_seconds",
    "rag_pipeline_events_total",
    "record_counter_metric",
    "record_pipeline_event",
    "record_pipeline_latency",
]
