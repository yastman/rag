"""Public service-layer query utilities for adapter use (#2745).

Exposes ``classify_query``, ``detect_injection``, and ``guard_node`` so
adapter layers (``telegram_bot/agents``) can call them without reaching
into ``src.runtime.graph.nodes`` internals directly.
"""

from src.runtime.graph.nodes.classify import classify_query
from src.runtime.graph.nodes.guard import detect_injection, guard_node


__all__ = ["classify_query", "detect_injection", "guard_node"]
