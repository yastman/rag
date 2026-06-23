"""Tests for metrics port conflict fix (issue #2190).

The default metrics port must NOT be 9091 to avoid collision with MinIO
console when the ML/MinIO profile is active.
"""

from __future__ import annotations

from telegram_bot.metrics_server import DEFAULT_METRICS_PORT, resolve_metrics_port


def test_default_metrics_port_not_9091() -> None:
    """DEFAULT_METRICS_PORT must not collide with MinIO console (9091)."""
    assert DEFAULT_METRICS_PORT != 9091, (
        "DEFAULT_METRICS_PORT must not be 9091 (MinIO console conflict)"
    )


def test_default_metrics_port_is_9092() -> None:
    """The new default should be 9092."""
    assert DEFAULT_METRICS_PORT == 9092


def test_resolve_metrics_port_returns_new_default() -> None:
    """resolve_metrics_port() with no env var returns the new default."""
    assert resolve_metrics_port() == 9092
