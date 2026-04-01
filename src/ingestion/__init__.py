"""Document ingestion package.

Use lazy exports to keep imports cheap for unified CLI and other lightweight tools.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any


__all__ = [
    "ContextualChunk",
    "ContextualDocument",
    "DocumentChunker",
    "DocumentIndexer",
    "FlowConfig",
    "IngestionService",
    "IngestionStats",
    "UniversalDocumentParser",
    "check_cocoindex_available",
    "create_document_flow",
    "load_contextual_chunks",
    "load_contextual_json",
]


if TYPE_CHECKING:
    from .chunker import DocumentChunker
    from .cocoindex_flow import FlowConfig, check_cocoindex_available, create_document_flow
    from .contextual_loader import load_contextual_chunks, load_contextual_json
    from .contextual_schema import ContextualChunk, ContextualDocument
    from .document_parser import UniversalDocumentParser
    from .indexer import DocumentIndexer
    from .service import IngestionService, IngestionStats


_LAZY_ATTRS = {
    "DocumentChunker": (".chunker", "DocumentChunker"),
    "FlowConfig": (".cocoindex_flow", "FlowConfig"),
    "check_cocoindex_available": (".cocoindex_flow", "check_cocoindex_available"),
    "create_document_flow": (".cocoindex_flow", "create_document_flow"),
    "load_contextual_chunks": (".contextual_loader", "load_contextual_chunks"),
    "load_contextual_json": (".contextual_loader", "load_contextual_json"),
    "ContextualChunk": (".contextual_schema", "ContextualChunk"),
    "ContextualDocument": (".contextual_schema", "ContextualDocument"),
    "UniversalDocumentParser": (".document_parser", "UniversalDocumentParser"),
    "DocumentIndexer": (".indexer", "DocumentIndexer"),
    "IngestionService": (".service", "IngestionService"),
    "IngestionStats": (".service", "IngestionStats"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(f"module 'src.ingestion' has no attribute '{name}'")
    module_name, attr_name = target
    module = import_module(module_name, package=__name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
