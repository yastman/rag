"""Services for Telegram RAG bot.

Uses lazy imports to avoid loading heavy dependencies at import time.
Import specific services directly for best performance:
    from src.runtime.services.qdrant import QdrantService
"""

from typing import TYPE_CHECKING

from .generation.generate_response import GenerationDeps, generate_response


if TYPE_CHECKING:
    from src.runtime.services.colbert_reranker import ColbertRerankerService
    from src.runtime.services.metrics import PipelineMetrics
    from src.runtime.services.qdrant import QdrantService
    from src.runtime.services.query_preprocessor import HyDEGenerator, QueryPreprocessor
    from src.runtime.services.small_to_big import ExpandedChunk, SmallToBigService
    from src.services.bge_m3_client import BGEM3Client, BGEM3SyncClient

    from .query_analyzer import QueryAnalyzer


__all__ = [
    "BGEM3Client",
    "BGEM3SyncClient",
    "ColbertRerankerService",
    "ExpandedChunk",
    "GenerationDeps",
    "HyDEGenerator",
    "PipelineMetrics",
    "QdrantService",
    "QueryAnalyzer",
    "QueryPreprocessor",
    "SmallToBigService",
    "generate_response",
]

_IMPORT_MAP = {
    "BGEM3Client": "src.services.bge_m3_client",
    "BGEM3SyncClient": "src.services.bge_m3_client",
    "ColbertRerankerService": "src.runtime.services.colbert_reranker",
    "ExpandedChunk": "src.runtime.services.small_to_big",
    "HyDEGenerator": "src.runtime.services.query_preprocessor",
    "PipelineMetrics": "src.runtime.services.metrics",
    "QdrantService": "src.runtime.services.qdrant",
    "QueryAnalyzer": "telegram_bot.services.rag.query_analyzer",
    "QueryPreprocessor": "src.runtime.services.query_preprocessor",
    "SmallToBigService": "src.runtime.services.small_to_big",
}


def __getattr__(name: str):
    """Lazy import handler."""
    if name in _IMPORT_MAP:
        import importlib

        module = importlib.import_module(_IMPORT_MAP[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
