"""Document ingestion package.

Use lazy exports to keep imports cheap for unified CLI and other lightweight tools.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any


__all__ = [
    "ContextualChunk",
    "ContextualDocument",
    "DoclingClient",
    "DoclingConfig",
    "DocumentChunker",
    "DocumentIndexer",
    "FlowConfig",
    "IngestionService",
    "IngestionStats",
    "UniversalDocumentParser",
    "check_cocoindex_available",
    "chunk_document",
    "create_document_flow",
    "create_text_for_embedding",
    "get_ingestion_status",
    "ingest_from_directory",
    "ingest_from_gdrive",
    "load_contextual_chunks",
    "load_contextual_json",
    "parse_document",
]


if TYPE_CHECKING:
    from .chunker import DocumentChunker
    from .cocoindex_flow import FlowConfig, check_cocoindex_available, create_document_flow
    from .contextual_loader import load_contextual_chunks, load_contextual_json
    from .contextual_schema import ContextualChunk, ContextualDocument, create_text_for_embedding
    from .docling_client import DoclingClient, DoclingConfig, chunk_document
    from .document_parser import UniversalDocumentParser, parse_document
    from .indexer import DocumentIndexer
    from .service import (
        IngestionService,
        IngestionStats,
        get_ingestion_status,
        ingest_from_directory,
        ingest_from_gdrive,
    )


_LAZY_ATTRS = {
    "DocumentChunker": (".chunker", "DocumentChunker"),
    "FlowConfig": (".cocoindex_flow", "FlowConfig"),
    "check_cocoindex_available": (".cocoindex_flow", "check_cocoindex_available"),
    "create_document_flow": (".cocoindex_flow", "create_document_flow"),
    "load_contextual_chunks": (".contextual_loader", "load_contextual_chunks"),
    "load_contextual_json": (".contextual_loader", "load_contextual_json"),
    "ContextualChunk": (".contextual_schema", "ContextualChunk"),
    "ContextualDocument": (".contextual_schema", "ContextualDocument"),
    "create_text_for_embedding": (".contextual_schema", "create_text_for_embedding"),
    "DoclingClient": (".docling_client", "DoclingClient"),
    "DoclingConfig": (".docling_client", "DoclingConfig"),
    "chunk_document": (".docling_client", "chunk_document"),
    "UniversalDocumentParser": (".document_parser", "UniversalDocumentParser"),
    "parse_document": (".document_parser", "parse_document"),
    "DocumentIndexer": (".indexer", "DocumentIndexer"),
    "IngestionService": (".service", "IngestionService"),
    "IngestionStats": (".service", "IngestionStats"),
    "get_ingestion_status": (".service", "get_ingestion_status"),
    "ingest_from_directory": (".service", "ingest_from_directory"),
    "ingest_from_gdrive": (".service", "ingest_from_gdrive"),
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
