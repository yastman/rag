"""ASGI ``/metrics`` endpoint for the Telegram bot (#2057).

Exposes the canonical Prometheus surface (``pipeline_latency_seconds`` and
``rag_pipeline_events_total`` from :mod:`src.runtime.services.metrics`) on a
dedicated port so operator dashboards can scrape the bot without going
through the bge-m3-api process.

Mirrors the ``services/bge-m3-api/app.py:make_asgi_app() + app.mount('/metrics', ...)``
pattern recorded in ADR-0015 (SDK-native baseline). The bot has no
ambient FastAPI app, so the ASGI surface is hosted by a dedicated uvicorn
server bound to ``TELEGRAM_BOT_METRICS_PORT`` (default ``9091`` —
intentionally distinct from the bge-m3-api default ``9090`` to avoid the
documented port collision).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from typing import Any

from prometheus_client import make_asgi_app


__all__ = ["MetricsServer", "make_metrics_app", "resolve_metrics_port"]


logger = logging.getLogger(__name__)

# Default avoids the bge-m3-api 9090 collision documented in #2057.
DEFAULT_METRICS_PORT = 9091


def make_metrics_app() -> Any:
    """Return the SDK-native Prometheus ASGI application.

    A thin wrapper around :func:`prometheus_client.make_asgi_app` so call
    sites and tests do not need to import the SDK directly. The returned
    callable is mounted by :class:`MetricsServer` (production) or driven
    by ``httpx.ASGITransport`` (tests).
    """
    return make_asgi_app()


def resolve_metrics_port(default: int = DEFAULT_METRICS_PORT) -> int:
    """Resolve the metrics port from ``TELEGRAM_BOT_METRICS_PORT``.

    Falls back to *default* (``9091``) on missing or invalid values, with a
    ``WARNING`` log so operators notice misconfiguration without the bot
    refusing to start.
    """
    raw = os.environ.get("TELEGRAM_BOT_METRICS_PORT", "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "TELEGRAM_BOT_METRICS_PORT=%r is not a valid int; falling back to %d",
            raw,
            default,
        )
        return default


class MetricsServer:
    """Background ``uvicorn`` server hosting the Prometheus ASGI app.

    Designed to be created once at bot startup. ``start_in_background`` is
    idempotent and ``stop`` is safe to call even if the server was never
    started (so the bot's ``finally:`` shutdown branch can call it
    unconditionally).

    The actual ``uvicorn`` import and ``uvicorn.Server`` lifecycle are
    deferred until ``start_in_background`` is awaited, so ``import``-time
    errors in environments without the optional ``uvicorn`` extra do not
    break bot startup outside the metrics endpoint path.
    """

    def __init__(self, *, port: int | None = None, host: str = "127.0.0.1") -> None:
        self.host = host
        self.port = port if port is not None else resolve_metrics_port()
        self._server: Any | None = None
        self._task: asyncio.Task[None] | None = None
        self._started = asyncio.Event()

    @property
    def bound_port(self) -> int | None:
        """Return the OS-assigned port when ``port=0`` was used at init time."""
        if self._server is None:
            return None
        servers = getattr(self._server, "servers", None) or []
        for s in servers:
            sockets = getattr(s, "sockets", None) or []
            for sock in sockets:
                getsockname = getattr(sock, "getsockname", None)
                if callable(getsockname):
                    try:
                        return int(getsockname()[1])
                    except (IndexError, TypeError, ValueError):
                        continue
        return self.port if self.port != 0 else None

    async def start_in_background(self) -> None:
        """Bind the metrics server and start serving in a background task."""
        if self._task is not None and not self._task.done():
            return  # Idempotent: already running.

        try:
            import uvicorn
        except ImportError as exc:  # pragma: no cover — uvicorn ships in deps
            logger.warning("uvicorn is not installed; /metrics endpoint disabled (%s)", exc)
            return

        # Pre-bind probe so a port collision does not reach uvicorn's
        # ``sys.exit(1)`` branch (uvicorn aborts the whole process on
        # OSError otherwise — see uvicorn/server.py:create_server). The
        # probe is skipped when ``port=0`` because the OS picks a free port
        # and there is no collision possible there.
        if self.port != 0:
            import socket as _socket

            probe = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            try:
                probe.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
                probe.bind((self.host, self.port))
            except OSError as exc:
                logger.warning(
                    "Cannot bind metrics port %d on %s: %s — /metrics disabled",
                    self.port,
                    self.host,
                    exc,
                )
                probe.close()
                return
            finally:
                probe.close()

        config = uvicorn.Config(
            make_metrics_app(),
            host=self.host,
            port=self.port,
            log_level="warning",
            lifespan="off",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        # Disable signal handler installation (would conflict with the
        # bot's own asyncio loop signal handlers).
        self._server.install_signal_handlers = lambda: None  # type: ignore[method-assign]

        self._started.clear()

        async def _serve() -> None:
            try:
                await self._server.serve()
            except SystemExit as exc:
                # uvicorn calls ``sys.exit(1)`` on bind failure even with
                # signal handlers disabled. Demote to a warning so the bot
                # keeps running without /metrics.
                logger.warning("Metrics server exited (uvicorn SystemExit): %s", exc)
            except Exception:  # pragma: no cover — defensive
                logger.exception("Metrics server crashed")

        self._task = asyncio.create_task(_serve(), name="metrics-server")

        # Wait until uvicorn binds before returning so callers can read
        # ``bound_port`` immediately after ``await server.start_in_background()``.
        for _ in range(50):  # up to ~5s
            await asyncio.sleep(0.1)
            servers = getattr(self._server, "servers", None) or []
            if servers and any(getattr(s, "sockets", None) for s in servers):
                self._started.set()
                logger.info(
                    "Metrics endpoint listening on http://%s:%d/metrics",
                    self.host,
                    self.bound_port or self.port,
                )
                return

        logger.warning("Metrics server did not bind within timeout on port %d", self.port)

    async def stop(self) -> None:
        """Stop the background server. Safe to call even if never started."""
        if self._server is None and self._task is None:
            return

        if self._server is not None:
            self._server.should_exit = True

        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                try:
                    await asyncio.wait_for(self._task, timeout=5.0)
                except TimeoutError:
                    self._task.cancel()
                    with contextlib.suppress(BaseException):
                        await self._task

        self._server = None
        self._task = None
        self._started.clear()
