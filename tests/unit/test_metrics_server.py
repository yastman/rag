"""Tests for DEPS-OBS3 metrics-server compatibility shims."""

from __future__ import annotations

import logging

import pytest

from telegram_bot.metrics_server import (
    create_metrics_app,
    resolve_metrics_port,
    start_metrics_server,
    stop_metrics_server,
)


def test_create_metrics_app_returns_none() -> None:
    assert create_metrics_app() is None


def test_resolve_metrics_port_fallback_and_invalid(monkeypatch, caplog) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_METRICS_PORT", "not-an-int")
    caplog.set_level(logging.WARNING)
    assert resolve_metrics_port() == 9092
    assert "TELEGRAM_BOT_METRICS_PORT" in caplog.text


@pytest.mark.asyncio
async def test_start_and_stop_metrics_server_are_noops(caplog) -> None:
    caplog.set_level(logging.INFO)
    server = await start_metrics_server(port=0)
    assert server is None
    assert "structured JSON product logs" in caplog.text
    await stop_metrics_server(server)
