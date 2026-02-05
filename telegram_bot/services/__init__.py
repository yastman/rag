"""Services for Telegram RAG bot.

Uses lazy imports to avoid loading heavy dependencies at import time.
Import specific services directly for best performance:
    from telegram_bot.services.voyage import VoyageService
"""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .bge_m3_dense import BgeM3DenseService
    from .cache import CacheService
    from .cesc import CESCPersonalizer, is_personalized_query
    from .colbert_reranker import ColbertRerankerService
    from .embeddings import EmbeddingService
    from .llm import LOW_CONFIDENCE_THRESHOLD, ConfidenceResult, LLMService
    from .qdrant import QdrantService
    from .query_analyzer import QueryAnalyzer
    from .query_preprocessor import HyDEGenerator, QueryPreprocessor
    from .query_router import (
        QueryType,
        classify_query,
        get_chitchat_response,
        get_off_topic_response,
        is_off_topic,
        needs_rerank,
    )
    from .retriever import RetrieverService
    from .small_to_big import ExpandedChunk, SmallToBigService
    from .user_context import UserContextService
    from .vectorizers import UserBaseVectorizer
    from .voyage import VoyageService


__all__ = [
    "LOW_CONFIDENCE_THRESHOLD",
    "BgeM3DenseService",
    "CESCPersonalizer",
    "CacheService",
    "ColbertRerankerService",
    "ConfidenceResult",
    "EmbeddingService",
    "ExpandedChunk",
    "HyDEGenerator",
    "LLMService",
    "QdrantService",
    "QueryAnalyzer",
    "QueryPreprocessor",
    "QueryType",
    "RetrieverService",
    "SmallToBigService",
    "UserBaseVectorizer",
    "UserContextService",
    "VoyageService",
    "classify_query",
    "get_chitchat_response",
    "get_off_topic_response",
    "is_off_topic",
    "is_personalized_query",
    "needs_rerank",
]

# Lazy import mapping
_IMPORT_MAP = {
    "BgeM3DenseService": ".bge_m3_dense",
    "CacheService": ".cache",
    "CESCPersonalizer": ".cesc",
    "ColbertRerankerService": ".colbert_reranker",
    "is_personalized_query": ".cesc",
    "ConfidenceResult": ".llm",
    "EmbeddingService": ".embeddings",
    "ExpandedChunk": ".small_to_big",
    "HyDEGenerator": ".query_preprocessor",
    "LLMService": ".llm",
    "LOW_CONFIDENCE_THRESHOLD": ".llm",
    "QdrantService": ".qdrant",
    "QueryAnalyzer": ".query_analyzer",
    "QueryPreprocessor": ".query_preprocessor",
    "QueryType": ".query_router",
    "classify_query": ".query_router",
    "get_chitchat_response": ".query_router",
    "get_off_topic_response": ".query_router",
    "is_off_topic": ".query_router",
    "needs_rerank": ".query_router",
    "RetrieverService": ".retriever",
    "SmallToBigService": ".small_to_big",
    "UserContextService": ".user_context",
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
