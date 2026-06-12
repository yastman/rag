"""Compatibility name for the canonical BGE-M3 embedding provider."""

from src.adapters.embeddings.bge_m3 import BgeM3EmbeddingProvider
from src.services.bge_m3_client import BGEM3Client


class ServiceBgeM3Provider(BgeM3EmbeddingProvider):
    """Embedding provider that calls an external BGE-M3 REST service.

    Kept for existing ``service_bge_m3`` factory users.  New runtime retrieval
    code should depend on :class:`BgeM3EmbeddingProvider` through the base
    provider interface.
    """


__all__ = ["BGEM3Client", "ServiceBgeM3Provider"]
