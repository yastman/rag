"""Contextual RAG Pipeline - Production-ready RAG system."""

import os


# Skip heavy imports during testing to prevent circular dependencies and full app loading
if os.getenv("RAG_TESTING", "false").lower() != "true":
    from src.config import Settings
    from src.contextualization import ClaudeContextualizer
    from src.core import RAGPipeline
    from src.ingestion import DocumentChunker, DocumentIndexer, UniversalDocumentParser
    from src.retrieval import DBSFColBERTSearchEngine

    __all__ = [
        "ClaudeContextualizer",
        "DBSFColBERTSearchEngine",
        "DocumentChunker",
        "DocumentIndexer",
        "RAGPipeline",
        "Settings",
        "UniversalDocumentParser",
    ]
else:
    __all__ = []

__version__ = "2.3.1"
__author__ = "Contextual RAG Team"
