"""Contextualization module for enriching documents with LLM."""

from typing import Any

from src._compat import load_deprecated_package_export

from .claude import ClaudeContextualizer
from .groq import GroqContextualizer
from .openai import OpenAIContextualizer


__all__ = [
    "ClaudeContextualizer",
    "GroqContextualizer",
    "OpenAIContextualizer",
]


_DEPRECATED_EXPORTS = {
    "ContextualizeProvider": (
        "src.contextualization.base",
        "ContextualizeProvider",
        "from src.contextualization.base import ContextualizeProvider",
    ),
}


def __getattr__(name: str) -> Any:
    """Resolve deprecated package exports lazily."""
    target = _DEPRECATED_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'src.contextualization' has no attribute '{name}'")
    value = load_deprecated_package_export(module_name=__name__, attr_name=name, target=target)
    globals()[name] = value
    return value
