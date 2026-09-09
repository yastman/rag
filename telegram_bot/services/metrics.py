"""Pipeline metrics for the RAG bot — back-compat re-export.

The canonical implementation moved to :mod:`src.runtime.services.metrics`
as part of the reverse-layering fix (#2047 / #2049). This module remains
so that existing ``from telegram_bot.services.metrics import …`` imports
across ``telegram_bot/``, ``tests/``, and the rest of the repo continue
to work unchanged.

The legacy ``record_counter_metric`` shim and ``PipelineMetrics`` singleton
proxy were removed with the no-op scoring surface (#3331); only the retained
canonical event/latency helpers are re-exported here.
"""

from src.runtime.services.metrics import (
    record_pipeline_event,
    record_pipeline_latency,
)


__all__ = [
    "record_pipeline_event",
    "record_pipeline_latency",
]
