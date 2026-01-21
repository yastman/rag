"""Document ingestion module for loading and indexing documents."""

from .chunker import DocumentChunker
from .contextual_loader import load_contextual_chunks, load_contextual_json
from .contextual_schema import (
    ContextualChunk,
    ContextualDocument,
    create_text_for_embedding,
)
from .document_parser import UniversalDocumentParser, parse_document
from .indexer import DocumentIndexer


__all__ = [
    "ContextualChunk",
    "ContextualDocument",
    "DocumentChunker",
    "DocumentIndexer",
    "UniversalDocumentParser",
    "create_text_for_embedding",
    "load_contextual_chunks",
    "load_contextual_json",
    "parse_document",
]
