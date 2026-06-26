"""Bootstrap helpers for tracing runtime initialization.

Re-exports from src.observability.bootstrap for backward compatibility.
"""

from src.observability.bootstrap import disable_otel_exporter, is_endpoint_reachable


__all__ = ["disable_otel_exporter", "is_endpoint_reachable"]
