"""Unified HTTP client for BGE-M3 API endpoints.

Re-exports from src.services.bge_m3_client for backward compatibility.
"""

from src.services.bge_m3_client import (
    BGE_M3_MODEL_NAME,
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_LENGTH,
    DEFAULT_TIMEOUT,
    BGEM3Client,
    BGEM3SyncClient,
    ColbertResult,
    DenseResult,
    HybridResult,
    RerankResult,
    SparseResult,
)


__all__ = [
    "BGE_M3_MODEL_NAME",
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_MAX_LENGTH",
    "DEFAULT_TIMEOUT",
    "BGEM3Client",
    "BGEM3SyncClient",
    "ColbertResult",
    "DenseResult",
    "HybridResult",
    "RerankResult",
    "SparseResult",
]
