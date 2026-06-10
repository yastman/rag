"""Pipeline metric events for the RAG bot — back-compat re-export.

The canonical implementation moved to :mod:`src.runtime.services.metrics`
as part of the reverse-layering fix (#2047 / #2049). This module remains
so that existing ``from telegram_bot.services.metrics import …`` imports
across ``telegram_bot/``, ``tests/``, and the rest of the repo continue
to work unchanged.
"""

from src.runtime.services.metrics import (
    PipelineMetrics,
    record_counter_metric,
    record_pipeline_event,
    record_pipeline_latency,
)


__all__ = [
    "PipelineMetrics",
    "record_counter_metric",
    "record_pipeline_event",
    "record_pipeline_latency",
]
