"""Services for Telegram RAG bot.

Uses lazy imports to avoid loading heavy dependencies at import time.
Import specific services directly for best performance:
    from telegram_bot.services.voyage import VoyageService
"""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .cache import CacheService
    from .cesc import CESCPersonalizer, is_personalized_query
    from .embeddings import EmbeddingService
    from .llm import LLMService
    from .qdrant import QdrantService
    from .query_analyzer import QueryAnalyzer
    from .query_preprocessor import QueryPreprocessor
    from .query_router import QueryType, classify_query, get_chitchat_response, needs_rerank
    from .retriever import RetrieverService
    from .small_to_big import ExpandedChunk, SmallToBigService
    from .user_context import UserContextService
    from .vectorizers import UserBaseVectorizer
    from .voyage import VoyageService


__all__ = [
    "CESCPersonalizer",
    "CacheService",
    "EmbeddingService",
    "ExpandedChunk",
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
    "is_personalized_query",
    "needs_rerank",
]

# Lazy import mapping
_IMPORT_MAP = {
    "CacheService": ".cache",
    "CESCPersonalizer": ".cesc",
    "is_personalized_query": ".cesc",
    "EmbeddingService": ".embeddings",
    "ExpandedChunk": ".small_to_big",
    "LLMService": ".llm",
    "QdrantService": ".qdrant",
    "QueryAnalyzer": ".query_analyzer",
    "QueryPreprocessor": ".query_preprocessor",
    "QueryType": ".query_router",
    "classify_query": ".query_router",
    "get_chitchat_response": ".query_router",
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
