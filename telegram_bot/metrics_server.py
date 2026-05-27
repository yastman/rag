"""Standalone Prometheus metrics ASGI server for the Telegram bot.

Issue #2057: expose the SDK-native ``prometheus_client`` default registry
via a lightweight ASGI ``/metrics`` endpoint using
:func:`prometheus_client.make_asgi_app`.  The server runs on
``TELEGRAM_BOT_METRICS_PORT`` (default 9092) alongside the aiogram
polling loop and is exposed only on localhost / internal networking.

Context7 baseline (``/prometheus/client_python``):
    ``make_asgi_app()`` returns an ASGI application that exposes the
    default ``prometheus_client.REGISTRY``.  The canonical FastAPI/Starlette
    mounting pattern is ``app.mount("/metrics", make_asgi_app())``.

For the bot the ASGI app is served standalone (no FastAPI parent) because
the bot runtime is aiogram-based, not ASGI-based.

Refs #2057.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
from typing import Any

import uvicorn
from prometheus_client import make_asgi_app


logger = logging.getLogger(__name__)

DEFAULT_METRICS_PORT = 9092


def resolve_metrics_port(default: int = DEFAULT_METRICS_PORT) -> int:
    """Resolve ``TELEGRAM_BOT_METRICS_PORT`` without import-time crashes."""
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


def create_metrics_app() -> Any:
    """Create an ASGI application that exposes the default Prometheus registry."""
    return make_asgi_app()


def _port_can_bind(host: str, port: int) -> bool:
    """Return False when the configured metrics port is already occupied."""
    if port == 0:
        return True
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((host, port))
    except OSError as exc:
        logger.warning(
            "Cannot bind Prometheus metrics server on %s:%d: %s; /metrics disabled",
            host,
            port,
            exc,
        )
        return False
    finally:
        probe.close()
    return True


async def start_metrics_server(
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    log_level: str | None = None,
) -> uvicorn.Server:
    """Start a background uvicorn server for Prometheus metrics.

    The bot must keep polling even when metrics cannot bind, so bind
    failures and uvicorn ``SystemExit`` are downgraded to warnings.
    """
    if port is None:
        port = resolve_metrics_port()
    if log_level is None:
        log_level = "warning"

    config = uvicorn.Config(
        app=create_metrics_app(),
        host=host,
        port=port,
        log_level=log_level,
        loop="asyncio",
        lifespan="off",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # type: ignore[attr-defined,method-assign]

    if not _port_can_bind(host, port):
        server.should_exit = True
        return server

    logger.info("Starting Prometheus metrics ASGI server on %s:%s", host, port)

    async def _serve() -> None:
        try:
            await server.serve()
        except SystemExit as exc:
            logger.warning("Prometheus metrics server exited during startup: %s", exc)
        except Exception:
            logger.warning("Prometheus metrics server stopped unexpectedly", exc_info=True)

    task = asyncio.create_task(_serve(), name="metrics-server")
    server._metrics_task = task  # type: ignore[attr-defined]

    # Wait briefly for the socket to bind so startup races are visible in logs.
    for _ in range(50):
        await asyncio.sleep(0.1)
        servers = getattr(server, "servers", None) or []
        if servers and any(getattr(s, "sockets", None) for s in servers):
            return server
        if task.done():
            return server

    logger.warning("Prometheus metrics server did not bind within timeout on %s:%s", host, port)
    return server


async def stop_metrics_server(server: uvicorn.Server) -> None:
    """Stop a running uvicorn metrics server gracefully."""
    if server is None:
        return
    logger.info("Stopping Prometheus metrics ASGI server")
    server.should_exit = True
    task = getattr(server, "_metrics_task", None)
    if task is None:
        return
    with contextlib.suppress(asyncio.CancelledError):
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except TimeoutError:
            task.cancel()
            with contextlib.suppress(BaseException):
                await task
