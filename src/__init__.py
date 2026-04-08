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
    "DBSFColBERTSearchEngine": (
        "src.retrieval",
        "DBSFColBERTSearchEngine",
        "from src.retrieval import DBSFColBERTSearchEngine",
    ),
    "DocumentChunker": (
        "src.ingestion",
        "DocumentChunker",
        "from src.ingestion import DocumentChunker",
    ),
    "DocumentIndexer": (
        "src.ingestion",
        "DocumentIndexer",
        "from src.ingestion import DocumentIndexer",
    ),
    "RAGPipeline": (
        "src.core",
        "RAGPipeline",
        "from src.core import RAGPipeline",
    ),
    "Settings": (
        "src.config",
        "Settings",
        "from src.config import Settings",
    ),
    "UniversalDocumentParser": (
        "src.ingestion",
        "UniversalDocumentParser",
        "from src.ingestion import UniversalDocumentParser",
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
