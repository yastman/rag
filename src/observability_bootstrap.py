"""Bootstrap helpers for Langfuse runtime initialization."""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse


def is_endpoint_reachable(url: str, *, timeout: float = 2.0) -> bool:
    """Return True if host:port from *url* accepts TCP connection."""
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def disable_otel_exporter(*, shutdown: bool = True) -> None:
    """Disable Langfuse/OTel export path and optionally shutdown active provider.

    Use ``shutdown=False`` to avoid noisy exporter shutdown tracebacks when local
    Langfuse endpoint is explicitly unreachable.
    """
    os.environ["LANGFUSE_TRACING_ENABLED"] = "false"
    os.environ["OTEL_SDK_DISABLED"] = "true"
    os.environ["OTEL_TRACES_EXPORTER"] = "none"
    os.environ["OTEL_METRICS_EXPORTER"] = "none"
    os.environ["OTEL_LOGS_EXPORTER"] = "none"
    # DEPS-OBS1 removes direct OpenTelemetry imports from the monolith.
    # The env flags above are enough to prevent exporter work; any SDK-owned
    # provider shutdown is left to the SDK/client that created it.
    _ = shutdown
