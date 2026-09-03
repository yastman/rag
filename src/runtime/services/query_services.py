"""Public service-layer query utilities for adapter use (#2745).

Exposes ``classify_query``, ``detect_injection``, and ``guard_node`` so
adapter layers (``telegram_bot``) can call them without reaching
into ``src.runtime.routing`` / ``src.runtime.safety`` internals directly.
"""

from src.runtime.routing.classify import classify_query
from src.runtime.safety.guard import detect_injection, guard_node


__all__ = ["classify_query", "detect_injection", "guard_node"]
