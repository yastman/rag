"""Observability bootstrap helpers — endpoint reachability and OTel export control.

Langfuse SDK removed (#2844, #2969). These helpers manipulate OTel env vars
and check endpoint reachability — no Langfuse SDK dependency required.

Kept as a stable seam so callers (and tests) can import them without pulling
in the full observability stack.
"""

from __future__ import annotations

import logging
import os
import socket
import urllib.parse


logger = logging.getLogger(__name__)


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

    When *shutdown* is False the call skips any provider.shutdown() call —
    use this in early-startup paths where a provider may not yet exist.
    """
    os.environ["LANGFUSE_TRACING_ENABLED"] = "false"
    os.environ["OTEL_SDK_DISABLED"] = "true"
    os.environ["OTEL_TRACES_EXPORTER"] = "none"
    os.environ["OTEL_METRICS_EXPORTER"] = "none"
    os.environ["OTEL_LOGS_EXPORTER"] = "none"

    if not shutdown:
        return

    # ponytail: attempt graceful SDK shutdown; ignore if OTel not installed or
    # provider is not an SDK provider (ceiling: only SdkTracerProvider has shutdown).
    try:
        import opentelemetry.trace as _trace
        from opentelemetry.sdk.trace import TracerProvider as _SdkTracerProvider

        provider = _trace.get_tracer_provider()
        if isinstance(provider, _SdkTracerProvider):
            provider.shutdown()
    except Exception as exc:  # best-effort shutdown — ignore failures
        logger.debug("OTel provider shutdown skipped: %s", exc)


__all__ = [
    "disable_otel_exporter",
    "is_endpoint_reachable",
]
