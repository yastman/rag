"""Observability bootstrap helpers — endpoint reachability and OTel export control.

Langfuse SDK removed (#2844, #2969). These helpers manipulate OTel env vars
and check endpoint reachability — no Langfuse SDK dependency required.

Kept as a stable seam so callers (and tests) can import them without pulling
in the full observability stack.
"""

from __future__ import annotations

import os
import socket
import urllib.parse


def is_endpoint_reachable(url: str, *, timeout: float = 2.0) -> bool:
    """Return True if host:port from *url* accepts a TCP connection within *timeout*.

    Only performs a raw socket connect — no HTTP request is made.
    Returns False on any connection or parsing error.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def disable_otel_exporter(*, shutdown: bool = True) -> None:
    """Disable OTel export by setting environment flags.

    Sets OTEL_SDK_DISABLED=true and clears all exporter env vars so no
    spans/metrics/logs are sent. Safe to call at any point before or after
    the OTel SDK initialises (env vars are read lazily by most exporters).

    The *shutdown* parameter is kept for API compatibility but is now a no-op:
    the monolith never constructs an SDK TracerProvider (Langfuse/OTel removed),
    so there is nothing to shut down.
    """
    os.environ["OTEL_SDK_DISABLED"] = "true"
    os.environ["OTEL_TRACES_EXPORTER"] = "none"
    os.environ["OTEL_METRICS_EXPORTER"] = "none"
    os.environ["OTEL_LOGS_EXPORTER"] = "none"


__all__ = [
    "disable_otel_exporter",
    "is_endpoint_reachable",
]
