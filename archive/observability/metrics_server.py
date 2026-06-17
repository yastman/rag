"""Metrics server compatibility helpers.

DEPS-OBS3 removes the Telegram bot's in-process Prometheus endpoint. Pipeline
latencies and counters are emitted as structured JSON product logs instead.
The small compatibility surface remains so imports and help text can resolve
without pulling ``prometheus_client`` into the core runtime.
"""

from __future__ import annotations

import logging
import os
from typing import Any


logger = logging.getLogger(__name__)

DEFAULT_METRICS_PORT = 9092


def resolve_metrics_port(default: int = DEFAULT_METRICS_PORT) -> int:
    """Resolve ``TELEGRAM_BOT_METRICS_PORT`` for backwards-compatible help text."""
    raw = os.getenv("TELEGRAM_BOT_METRICS_PORT", "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "TELEGRAM_BOT_METRICS_PORT=%r is not a valid integer; falling back to %d",
            raw,
            default,
        )
        return default


def create_metrics_app() -> None:
    """Return no ASGI app: Prometheus exposition is no longer in-process."""
    return


async def start_metrics_server(
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    log_level: str | None = None,
) -> None:
    """No-op compatibility shim for the removed in-process metrics server."""
    _ = (host, port, log_level)
    logger.info("Prometheus /metrics server disabled; use structured JSON product logs")
    return


async def stop_metrics_server(server: Any) -> None:
    """No-op compatibility shim for the removed in-process metrics server."""
    _ = server
