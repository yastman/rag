"""Services for Telegram RAG bot.

Uses lazy imports to avoid loading heavy dependencies at import time.
Import specific services directly for best performance:
    from telegram_bot.services.qdrant import QdrantService
"""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .bge_m3_dense import BgeM3DenseService
    from .colbert_reranker import ColbertRerankerService
    from .embeddings import EmbeddingService
    from .history_service import HistoryService
    from .llm import LOW_CONFIDENCE_THRESHOLD, ConfidenceResult, LLMService
    from .metrics import PipelineMetrics
    from .qdrant import QdrantService
    from .query_analyzer import QueryAnalyzer
    from .query_preprocessor import HyDEGenerator, QueryPreprocessor
    from .retriever import RetrieverService
    from .small_to_big import ExpandedChunk, SmallToBigService
    from .vectorizers import UserBaseVectorizer
    from .voyage import VoyageService


__all__ = [
    "LOW_CONFIDENCE_THRESHOLD",
    "BgeM3DenseService",
    "ColbertRerankerService",
    "ConfidenceResult",
    "EmbeddingService",
    "ExpandedChunk",
    "HistoryService",
    "HyDEGenerator",
    "LLMService",
    "PipelineMetrics",
    "QdrantService",
    "QueryAnalyzer",
    "QueryPreprocessor",
    "RetrieverService",
    "SmallToBigService",
    "UserBaseVectorizer",
    "VoyageService",
]

# Lazy import mapping
_IMPORT_MAP = {
    "BgeM3DenseService": ".bge_m3_dense",
    "ColbertRerankerService": ".colbert_reranker",
    "ConfidenceResult": ".llm",
    "EmbeddingService": ".embeddings",
    "ExpandedChunk": ".small_to_big",
    "HistoryService": ".history_service",
    "HyDEGenerator": ".query_preprocessor",
    "LLMService": ".llm",
    "LOW_CONFIDENCE_THRESHOLD": ".llm",
    "PipelineMetrics": ".metrics",
    "QdrantService": ".qdrant",
    "QueryAnalyzer": ".query_analyzer",
    "QueryPreprocessor": ".query_preprocessor",
    "RetrieverService": ".retriever",
    "SmallToBigService": ".small_to_big",
    "UserBaseVectorizer": ".vectorizers",
    "VoyageService": ".voyage",
}


def __getattr__(name: str):
    """Lazy import handler."""
    if name in _IMPORT_MAP:
        import importlib

        module = importlib.import_module(_IMPORT_MAP[name], __package__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
