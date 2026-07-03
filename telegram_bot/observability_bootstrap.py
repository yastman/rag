"""Backward-compat shim — canonical implementation lives in src.observability.bootstrap.

Langfuse SDK removed (#2844, #2969). Re-exports bootstrap helpers so callers
that import ``telegram_bot.observability_bootstrap`` continue to work.
"""

from src.observability.bootstrap import (
    disable_otel_exporter as disable_otel_exporter,
)
from src.observability.bootstrap import (
    is_endpoint_reachable as is_endpoint_reachable,
)


__all__ = [
    "disable_otel_exporter",
    "is_endpoint_reachable",
]
