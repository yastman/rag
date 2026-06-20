"""Contextual RAG Pipeline package metadata.

Keep this module lightweight.
Heavy imports here can block CLI startup (e.g. ``python -m src.ingestion.unified.cli``),
because Python imports ``src`` before the target submodule.
"""

from typing import Any

from ._compat import load_deprecated_package_export


_DEPRECATED_EXPORTS = {
    "ClaudeContextualizer": (
        "src.contextualization",
        "ClaudeContextualizer",
        "from src.contextualization import ClaudeContextualizer",
    ),
    # Removed deprecated export for DBSFColBERTSearchEngine; evaluation search engines are no longer exported from src
    "DocumentIndexer": (
        "src.ingestion",
        "DocumentIndexer",
        "from src.ingestion import DocumentIndexer",
    ),
    "Settings": (
        "src.config",
        "Settings",
        "from src.config import Settings",
    ),
}


def __getattr__(name: str) -> Any:
    """Resolve deprecated package exports lazily."""
    target = _DEPRECATED_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'src' has no attribute '{name}'")
    value = load_deprecated_package_export(module_name=__name__, attr_name=name, target=target)
    globals()[name] = value
    return value


__version__ = "2.3.1"
__author__ = "Contextual RAG Team"
