"""Unit tests for telegram_bot.metrics_server (#2057).

The bot exposes its Prometheus surface (``pipeline_latency_seconds`` and
``rag_pipeline_events_total`` from ``src.runtime.services.metrics``) on a
dedicated ASGI ``/metrics`` endpoint, mirroring the
``services/bge-m3-api`` pattern.

Verified shape via the Prometheus Python client docs:
``prometheus_client.make_asgi_app()`` returns a Starlette-compatible ASGI
callable that serves the registered metrics in text-format on the
configured registry.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_exports_expected_public_surface():
    """The module must export the documented helpers."""
    from telegram_bot import metrics_server

    for name in ("make_metrics_app", "resolve_metrics_port", "MetricsServer"):
        assert hasattr(metrics_server, name), (
            f"telegram_bot.metrics_server must export {name} (#2057)."
        )


def test_make_metrics_app_returns_asgi_callable():
    """``make_metrics_app()`` returns the prometheus_client ASGI app.

    The test uses ``callable()`` rather than an isinstance check because
    ``make_asgi_app`` returns a closure rather than a class instance.
    """
    from telegram_bot.metrics_server import make_metrics_app

    app = make_metrics_app()
    assert callable(app)


# ---------------------------------------------------------------------------
# Live ASGI behaviour
# ---------------------------------------------------------------------------


async def _fetch_metrics(app) -> tuple[int, str]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://metrics") as client:
        response = await client.get("/")
    return response.status_code, response.text


async def test_metrics_app_returns_pipeline_latency_seconds():
    """The exposed surface must include the canonical pipeline latency Histogram."""
    from src.runtime.services.metrics import pipeline_latency_seconds
    from telegram_bot.metrics_server import make_metrics_app

    # Force at least one observation so the metric appears in the export.
    pipeline_latency_seconds.labels(stage="metrics-test").observe(0.001)

    status, body = await _fetch_metrics(make_metrics_app())
    assert status == 200
    assert "pipeline_latency_seconds" in body, (
        "Acceptance criterion: /metrics emits pipeline_latency_seconds (#2057)."
    )


async def test_metrics_app_returns_rag_pipeline_events_total():
    """The exposed surface must include the canonical RAG events Counter."""
    from src.runtime.services.metrics import rag_pipeline_events_total
    from telegram_bot.metrics_server import make_metrics_app

    # Force at least one increment so the counter appears in the export.
    rag_pipeline_events_total.labels(event="metrics-test").inc()

    status, body = await _fetch_metrics(make_metrics_app())
    assert status == 200
    assert "rag_pipeline_events_total" in body, (
        "Acceptance criterion: /metrics emits rag_pipeline_events_total (#2057)."
    )


async def test_metrics_app_returns_text_format():
    """Response content type must match the Prometheus text format contract."""
    from telegram_bot.metrics_server import make_metrics_app

    transport = httpx.ASGITransport(app=make_metrics_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://metrics") as client:
        response = await client.get("/")

    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "text/plain" in content_type, (
        f"prometheus_client must return text/plain Prometheus exposition format. "
        f"Got: {content_type!r}"
    )


# ---------------------------------------------------------------------------
# Port resolution
# ---------------------------------------------------------------------------


def test_resolve_metrics_port_default_is_9091():
    """Default port avoids the bge-m3-api 9090 collision (#2057 acceptance)."""
    from telegram_bot.metrics_server import resolve_metrics_port

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TELEGRAM_BOT_METRICS_PORT", None)
        assert resolve_metrics_port() == 9091


def test_resolve_metrics_port_reads_env_var():
    from telegram_bot.metrics_server import resolve_metrics_port

    with patch.dict(os.environ, {"TELEGRAM_BOT_METRICS_PORT": "9555"}):
        assert resolve_metrics_port() == 9555


def test_resolve_metrics_port_falls_back_on_invalid_value(caplog):
    """Garbage env values must not crash the bot startup."""
    from telegram_bot.metrics_server import resolve_metrics_port

    with patch.dict(os.environ, {"TELEGRAM_BOT_METRICS_PORT": "not-a-number"}):
        with caplog.at_level("WARNING"):
            assert resolve_metrics_port() == 9091
        assert any("TELEGRAM_BOT_METRICS_PORT" in r.message for r in caplog.records)


def test_resolve_metrics_port_does_not_collide_with_bge_m3_api():
    """Sanity guard for the documented 9090 vs 9091 split."""
    from telegram_bot.metrics_server import resolve_metrics_port

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TELEGRAM_BOT_METRICS_PORT", None)
        # bge-m3-api default is 9090; we must not equal it by default.
        assert resolve_metrics_port() != 9090


# ---------------------------------------------------------------------------
# MetricsServer lifecycle
# ---------------------------------------------------------------------------


def test_metrics_server_constructor_records_port():
    from telegram_bot.metrics_server import MetricsServer

    server = MetricsServer(port=9555)
    assert server.port == 9555


def test_metrics_server_default_port_uses_resolver():
    """When no port is passed, fall back to ``resolve_metrics_port()``."""
    from telegram_bot.metrics_server import MetricsServer

    with patch.dict(os.environ, {"TELEGRAM_BOT_METRICS_PORT": "9777"}):
        server = MetricsServer()
        assert server.port == 9777


async def test_metrics_server_start_in_background_is_idempotent():
    """Calling ``start_in_background`` twice must not double-bind the port."""
    from telegram_bot.metrics_server import MetricsServer

    server = MetricsServer(port=0)  # port=0 so the OS picks a free one
    try:
        await server.start_in_background()
        first_task = server._task
        await server.start_in_background()
        assert server._task is first_task, (
            "Idempotency: a second start_in_background must reuse the running task."
        )
    finally:
        await server.stop()


async def test_metrics_server_stop_when_not_started_is_noop():
    """Stopping a never-started server must not raise."""
    from telegram_bot.metrics_server import MetricsServer

    server = MetricsServer(port=0)
    # Must not raise.
    await server.stop()


async def test_metrics_server_serves_pipeline_metrics_when_running():
    """Integration: bind to a free port and curl /metrics for the canonical signals."""
    pytest.importorskip("uvicorn")
    from src.runtime.services.metrics import (
        pipeline_latency_seconds,
        rag_pipeline_events_total,
    )
    from telegram_bot.metrics_server import MetricsServer

    pipeline_latency_seconds.labels(stage="metrics-server-it").observe(0.002)
    rag_pipeline_events_total.labels(event="metrics-server-it").inc()

    server = MetricsServer(port=0)
    await server.start_in_background()
    try:
        bound_port = server.bound_port
        assert bound_port is not None and bound_port > 0
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{bound_port}") as client:
            response = await client.get("/metrics")
        assert response.status_code == 200
        assert "pipeline_latency_seconds" in response.text
        assert "rag_pipeline_events_total" in response.text
    finally:
        await server.stop()
