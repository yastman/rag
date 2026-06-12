"""Pure runtime retrieval services.

Retrieval services compose the embedding provider layer with the canonical
Qdrant SDK gateway. They do not generate answers.
"""

from src.runtime.retrieval.service import RetrievalRequest, RetrievalService, VectorRetrievalRequest


__all__ = ["RetrievalRequest", "RetrievalService", "VectorRetrievalRequest"]
