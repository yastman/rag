"""Document ingestion module for loading and indexing documents."""

from .chunker import DocumentChunker
from .cocoindex_flow import FlowConfig, check_cocoindex_available, create_document_flow
from .contextual_loader import load_contextual_chunks, load_contextual_json
from .contextual_schema import (
    ContextualChunk,
    ContextualDocument,
    create_text_for_embedding,
)
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
