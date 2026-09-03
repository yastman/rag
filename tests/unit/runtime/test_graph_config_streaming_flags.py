"""Streaming-flag pins for GraphConfig (relocated from tests/unit/agents #3216).

The imperative agent facade those tests lived next to was removed (#3216);
the ``streaming_enabled`` config surface remains part of the runtime config
contract and stays pinned here.
"""

from __future__ import annotations


def test_streaming_config_flag():
    """Streaming is controlled by GraphConfig.streaming_enabled."""
    from src.runtime.config import GraphConfig

    gc = GraphConfig(streaming_enabled=True)
    assert gc.streaming_enabled is True

    gc2 = GraphConfig(streaming_enabled=False)
    assert gc2.streaming_enabled is False


def test_streaming_default_is_true():
    """streaming_enabled defaults to True."""
    from src.runtime.config import GraphConfig

    gc = GraphConfig()
    assert gc.streaming_enabled is True
