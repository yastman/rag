"""Embedding provider adapters.

The canonical application-facing embedding layer lives here. Runtime retrieval
code should depend on these providers; low-level SDK clients stay in
``src.services``.
"""

from src.adapters.embeddings.base import EmbeddingProvider
from src.adapters.embeddings.bge_m3 import BgeM3EmbeddingProvider
from src.adapters.embeddings.factory import get_embeddings_provider
from src.adapters.embeddings.local_bge_m3 import LocalBgeM3Provider
from src.adapters.embeddings.openai_embeddings import OpenAIEmbeddingProvider
from src.adapters.embeddings.service_bge_m3 import ServiceBgeM3Provider


__all__ = [
    "BgeM3EmbeddingProvider",
    "EmbeddingProvider",
    "LocalBgeM3Provider",
    "OpenAIEmbeddingProvider",
    "ServiceBgeM3Provider",
    "get_embeddings_provider",
]
