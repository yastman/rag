"""Services for Telegram RAG bot.

Uses lazy imports to avoid loading heavy dependencies at import time.
Import specific services directly for best performance:
    from telegram_bot.services.qdrant import QdrantService
"""

from typing import TYPE_CHECKING

from .generate_response import generate_response


if TYPE_CHECKING:
    from .bge_m3_client import BGEM3Client, BGEM3SyncClient
    from .history_service import HistoryService
    from .metrics import PipelineMetrics
    from .qdrant import QdrantService
    from .query_analyzer import QueryAnalyzer
    from .query_preprocessor import HyDEGenerator, QueryPreprocessor
    from .small_to_big import ExpandedChunk, SmallToBigService


__all__ = [
    "BGEM3Client",
    "BGEM3SyncClient",
    "ExpandedChunk",
    "HistoryService",
    "HyDEGenerator",
    "PipelineMetrics",
    "QdrantService",
    "QueryAnalyzer",
    "QueryPreprocessor",
    "SmallToBigService",
    "generate_response",
]

_IMPORT_MAP = {
    "BGEM3Client": ".bge_m3_client",
    "BGEM3SyncClient": ".bge_m3_client",
    "ExpandedChunk": ".small_to_big",
    "HistoryService": ".history_service",
    "HyDEGenerator": ".query_preprocessor",
    "PipelineMetrics": ".metrics",
    "QdrantService": ".qdrant",
    "QueryAnalyzer": ".query_analyzer",
    "QueryPreprocessor": ".query_preprocessor",
    "SmallToBigService": ".small_to_big",
}


def __getattr__(name: str):
    """Lazy import handler."""
    if name in _IMPORT_MAP:
        import importlib

        module = importlib.import_module(_IMPORT_MAP[name], __package__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
