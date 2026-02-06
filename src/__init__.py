"""Contextual RAG Pipeline - package entrypoint.

Keep this module lightweight.
Heavy imports here can block CLI startup (e.g. ``python -m src.ingestion.unified.cli``),
because Python imports ``src`` before the target submodule.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any


__all__ = [
    "ClaudeContextualizer",
    "DBSFColBERTSearchEngine",
    "DocumentChunker",
    "DocumentIndexer",
    "RAGPipeline",
    "Settings",
    "UniversalDocumentParser",
]


if TYPE_CHECKING:
    # Type checkers get concrete symbols; runtime stays lazy.
    from src.config import Settings
    from src.contextualization import ClaudeContextualizer
    from src.core import RAGPipeline
    from src.ingestion import DocumentChunker, DocumentIndexer, UniversalDocumentParser
    from src.retrieval import DBSFColBERTSearchEngine


_LAZY_ATTRS = {
    "Settings": ("src.config", "Settings"),
    "ClaudeContextualizer": ("src.contextualization", "ClaudeContextualizer"),
    "RAGPipeline": ("src.core", "RAGPipeline"),
    "DocumentChunker": ("src.ingestion", "DocumentChunker"),
    "DocumentIndexer": ("src.ingestion", "DocumentIndexer"),
    "UniversalDocumentParser": ("src.ingestion", "UniversalDocumentParser"),
    "DBSFColBERTSearchEngine": ("src.retrieval", "DBSFColBERTSearchEngine"),
}


def __getattr__(name: str) -> Any:
    """Lazy-load top-level exports on first access."""
    target = _LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(f"module 'src' has no attribute '{name}'")
    module_name, attr_name = target
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


__version__ = "2.3.1"
__author__ = "Contextual RAG Team"
