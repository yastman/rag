"""Standalone Prometheus metrics ASGI server for the Telegram bot.

Issue #2057: expose the SDK-native ``prometheus_client`` default registry
via a lightweight ASGI ``/metrics`` endpoint using
:func:`prometheus_client.make_asgi_app`.  The server runs on
``TELEGRAM_BOT_METRICS_PORT`` (default 9091) alongside the aiogram
polling loop and is exposed only on localhost / internal networking.

Context7 baseline (``/prometheus/client_python``):
    ``make_asgi_app()`` returns an ASGI application that exposes the
    default ``prometheus_client.REGISTRY``.  The canonical FastAPI/Starlette
    mounting pattern is ``app.mount("/metrics", make_asgi_app())``.

The local pattern in ``services/bge-m3-api/app.py:588-589`` confirms the
same approach is used across the repository:

    .. code-block:: python

        from prometheus_client import make_asgi_app

        metrics_app = make_asgi_app()
        app.mount("/metrics", metrics_app)

For the bot the ASGI app is served standalone (no FastAPI parent) because
the bot runtime is aiogram-based, not ASGI-based.

Refs #2057.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import uvicorn
from prometheus_client import make_asgi_app


logger = logging.getLogger(__name__)

# Default port for the metrics endpoint.  Override with
# TELEGRAM_BOT_METRICS_PORT environment variable.
DEFAULT_METRICS_PORT: int = int(os.getenv("TELEGRAM_BOT_METRICS_PORT", "9091"))


def create_metrics_app() -> Any:
    """Create an ASGI application that exposes Prometheus metrics.

    Uses :func:`prometheus_client.make_asgi_app` with the package-wide
    default ``prometheus_client.REGISTRY``.  No custom
    ``CollectorRegistry`` is used.

    Returns:
        An ASGI application callable serving the Prometheus text format
        at its root path (``/``).
    """
    return make_asgi_app()


async def start_metrics_server(
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    log_level: str | None = None,
) -> uvicorn.Server:
    """Start a uvicorn ASGI server for the Prometheus ``/metrics`` endpoint.

    The server runs as an asyncio background task so the aiogram polling
    loop is not blocked.  Call :func:`stop_metrics_server` to shut it down
    gracefully.

    Args:
        host: Bind address (default ``"127.0.0.1"`` — internal only).
        port: Port to listen on (default ``TELEGRAM_BOT_METRICS_PORT``
            env or ``9091``).
        log_level: Uvicorn log level (default ``"info"``).

    Returns:
        A ``uvicorn.Server`` instance whose shutdown is controlled by
        ``stop_metrics_server``.
    """
    if port is None:
        port = DEFAULT_METRICS_PORT
    if log_level is None:
        log_level = "info"

    app = create_metrics_app()
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level=log_level,
        # The bot owns its own event loop (aiogram polling); avoid
        # uvicorn trying to install its own signal handlers or manage
        # event-loop lifecycle.
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    logger.info(
        "Starting Prometheus metrics ASGI server on %s:%s",
        host,
        port,
    )

    # Run the server as a concurrent task so the bot polling loop is not
    # blocked.
    import asyncio

    __metrics_server_task = asyncio.create_task(server.serve(), name="metrics-server")
    # Store a reference on the server object so the task is not garbage-
    # collected; the dunder prefix signals "internal — do not touch".
    server._metrics_task = __metrics_server_task  # type: ignore[attr-defined]

    # Let the server bind its socket before returning.
    await asyncio.sleep(0.1)

    return server


async def stop_metrics_server(server: uvicorn.Server) -> None:
    """Stop a running uvicorn metrics server gracefully.

    Args:
        server: The ``uvicorn.Server`` instance returned by
            :func:`start_metrics_server`.
    """
    if server is None:
        return
    logger.info("Stopping Prometheus metrics ASGI server")
    server.should_exit = True
    # Give the server a moment to drain
    import asyncio

    await asyncio.sleep(0.1)
