"""Document ingestion package.

Use lazy exports to keep imports cheap for unified CLI and other lightweight tools.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from src._compat import load_deprecated_package_export


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


_DEPRECATED_EXPORTS = {
    "DoclingClient": (
        "src.ingestion.docling_client",
        "DoclingClient",
        "from src.ingestion.docling_client import DoclingClient",
    ),
    "DoclingConfig": (
        "src.ingestion.docling_client",
        "DoclingConfig",
        "from src.ingestion.docling_client import DoclingConfig",
    ),
    "chunk_document": (
        "src.ingestion.docling_client",
        "chunk_document",
        "from src.ingestion.docling_client import chunk_document",
    ),
    "create_text_for_embedding": (
        "src.ingestion.contextual_schema",
        "create_text_for_embedding",
        "from src.ingestion.contextual_schema import create_text_for_embedding",
    ),
    "get_ingestion_status": (
        "src.ingestion.service",
        "get_ingestion_status",
        "from src.ingestion.service import get_ingestion_status",
    ),
    "ingest_from_directory": (
        "src.ingestion.service",
        "ingest_from_directory",
        "from src.ingestion.service import ingest_from_directory",
    ),
    "ingest_from_gdrive": (
        "src.ingestion.service",
        "ingest_from_gdrive",
        "from src.ingestion.service import ingest_from_gdrive",
    ),
    "parse_document": (
        "src.ingestion.document_parser",
        "parse_document",
        "from src.ingestion.document_parser import parse_document",
    ),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_ATTRS.get(name)
    if target is not None:
        module_name, attr_name = target
        module = import_module(module_name, package=__name__)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value

    deprecated_target = _DEPRECATED_EXPORTS.get(name)
    if deprecated_target is None:
        raise AttributeError(f"module 'src.ingestion' has no attribute '{name}'")
    value = load_deprecated_package_export(
        module_name=__name__,
        attr_name=name,
        target=deprecated_target,
    )
    globals()[name] = value
    return value
