"""Compatibility shim — re-exports from src.runtime.graph.nodes.classify."""

from src.runtime.graph.nodes.classify import (  # noqa: F401
    CHITCHAT,
    OFF_TOPIC,
    OFF_TOPIC_RESPONSES,
    _get_chitchat_response,
    classify_query,
)
