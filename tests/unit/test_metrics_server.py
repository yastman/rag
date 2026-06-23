"""Smoke tests for the Prometheus metrics ASGI server (#2057).

Validates the SDK-native ``prometheus_client.make_asgi_app()``
metrics endpoint served via uvicorn as a lightweight ASGI app.
"""

from __future__ import annotations

import asyncio
import importlib
import socket
from contextlib import closing

import httpx
import pytest
from prometheus_client import REGISTRY, Histogram

from telegram_bot.metrics_server import (
    create_metrics_app,
    resolve_metrics_port,
    start_metrics_server,
    stop_metrics_server,
)


def _find_free_port() -> int:
    """Return a free port for testing."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


class TestCreateMetricsApp:
    """The ASGI app created by create_metrics_app() serves Prometheus
    exposition at the root path.
    """

    def test_app_is_asgi_app(self):
        """create_metrics_app() returns a callable ASGI app."""
        app = create_metrics_app()
        assert callable(app), "must return a callable ASGI application"

    async def test_metrics_endpoint_returns_prometheus_text(self):
        """The ASGI app root returns valid Prometheus text format."""
        app = create_metrics_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/")
            assert resp.status_code == 200
            body = resp.text
            # The default prometheus_client.REGISTRY always exposes at
            # least process-level and Python GC metrics, so the output
            # should be non-empty Prometheus text format.
            assert body, "Response body must not be empty"
            assert "HELP " in body or "# HELP " in body, "Body must contain Prometheus HELP lines"

    async def test_metrics_endpoint_includes_registered_metric(self):
        """A metric registered with the default REGISTRY appears in output."""
        # Register a temporary test metric to verify integration
        test_histogram = Histogram(
            "test_metrics_server_smoke_seconds",
            "Smoke-test metric for ASGI metrics endpoint.",
            labelnames=("label",),
        )
        try:
            test_histogram.labels(label="smoke").observe(0.42)
            app = create_metrics_app()

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/")
                assert resp.status_code == 200
                body = resp.text
                assert "test_metrics_server_smoke_seconds" in body, (
                    "Registered metric must appear in /metrics output"
                )
        finally:
            REGISTRY.unregister(test_histogram)


class TestMetricsPortResolution:
    def test_default_port_is_9092(self):
        assert resolve_metrics_port() == 9092

    def test_invalid_env_value_falls_back_without_import_crash(self, monkeypatch, caplog):
        monkeypatch.setenv("TELEGRAM_BOT_METRICS_PORT", "not-an-int")
        with caplog.at_level("WARNING"):
            assert resolve_metrics_port() == 9092
        assert "TELEGRAM_BOT_METRICS_PORT" in caplog.text

        # Regression: this used to evaluate int(os.getenv(...)) at import time.
        import telegram_bot.metrics_server as metrics_server

        importlib.reload(metrics_server)
        assert metrics_server.resolve_metrics_port() == 9092
        monkeypatch.delenv("TELEGRAM_BOT_METRICS_PORT", raising=False)
        importlib.reload(metrics_server)


class TestMetricsServerLifecycle:
    """The uvicorn-based metrics server starts and stops cleanly."""

    @pytest.mark.timeout(10)
    async def test_start_and_stop_server(self):
        """A uvicorn server starts on the given port and can be stopped."""
        port = _find_free_port()

        server = await start_metrics_server(
            host="127.0.0.1",
            port=port,
            log_level="error",
        )

        # Give uvicorn a moment to bind the port
        await asyncio.sleep(0.3)

        # Verify the server is actually listening
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://127.0.0.1:{port}/", timeout=3.0)
                assert resp.status_code == 200
        finally:
            await stop_metrics_server(server)

        # After stop, the port should be free again (give it a moment)
        await asyncio.sleep(0.3)

    @pytest.mark.timeout(10)
    async def test_occupied_port_does_not_raise_or_exit_process(self):
        """A metrics port collision must disable /metrics, not kill the bot."""
        port = _find_free_port()
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("127.0.0.1", port))
        blocker.listen(1)
        try:
            server = await start_metrics_server(
                host="127.0.0.1",
                port=port,
                log_level="error",
            )
            assert server.should_exit is True
            assert getattr(server, "_metrics_task", None) is None
        finally:
            blocker.close()

    @pytest.mark.timeout(10)
    async def test_custom_port(self):
        """Server respects the configured port."""
        port = _find_free_port()

        server = await start_metrics_server(
            host="127.0.0.1",
            port=port,
            log_level="error",
        )

        await asyncio.sleep(0.3)

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://127.0.0.1:{port}/", timeout=3.0)
                assert resp.status_code == 200

                # Verify another port is NOT serving
                other_port = _find_free_port()
                if other_port != port:
                    with pytest.raises(
                        (httpx.ConnectError, httpx.ConnectTimeout),
                    ):
                        await client.get(f"http://127.0.0.1:{other_port}/", timeout=1.0)
        finally:
            await stop_metrics_server(server)
