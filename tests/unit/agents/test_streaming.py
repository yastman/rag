"""Tests for agent streaming via astream (#413)."""

from __future__ import annotations


async def test_streaming_config_flag():
    """Streaming is controlled by GraphConfig.streaming_enabled."""
    from telegram_bot.graph.config import GraphConfig

    gc = GraphConfig(streaming_enabled=True)
    assert gc.streaming_enabled is True

    gc2 = GraphConfig(streaming_enabled=False)
    assert gc2.streaming_enabled is False


async def test_streaming_default_is_true():
    """streaming_enabled defaults to True."""
    from telegram_bot.graph.config import GraphConfig

    gc = GraphConfig()
    assert gc.streaming_enabled is True
