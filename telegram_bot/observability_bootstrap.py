"""Bootstrap helpers for Langfuse runtime initialization.

Re-exports from src.observability_bootstrap for backward compatibility.
"""

from src.observability_bootstrap import disable_otel_exporter, is_endpoint_reachable


__all__ = ["disable_otel_exporter", "is_endpoint_reachable"]
