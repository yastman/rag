"""Contextual RAG Pipeline - Production-ready RAG system."""

from src.config import Settings
from src.contextualization import ClaudeContextualizer
from src.core import RAGPipeline
from src.ingestion import DocumentChunker, DocumentIndexer, UniversalDocumentParser
from src.retrieval import DBSFColBERTSearchEngine


__version__ = "2.3.1"
__author__ = "Contextual RAG Team"

__all__ = [
    "ClaudeContextualizer",
    "DBSFColBERTSearchEngine",
    "DocumentChunker",
    "DocumentIndexer",
    "RAGPipeline",
    "Settings",
    "UniversalDocumentParser",
]
