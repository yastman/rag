"""Contextualization module for enriching documents with LLM."""

from typing import Any

from src._compat import load_deprecated_package_export


__all__ = [
    "ClaudeContextualizer",
    "GroqContextualizer",
    "OpenAIContextualizer",
]


_DEPRECATED_EXPORTS = {
    "ClaudeContextualizer": (
        "src.contextualization.claude",
        "ClaudeContextualizer",
        "from src.contextualization.claude import ClaudeContextualizer",
    ),
    "GroqContextualizer": (
        "src.contextualization.groq",
        "GroqContextualizer",
        "from src.contextualization.groq import GroqContextualizer",
    ),
    "OpenAIContextualizer": (
        "src.contextualization.openai",
        "OpenAIContextualizer",
        "from src.contextualization.openai import OpenAIContextualizer",
    ),
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
