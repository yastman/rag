"""Embedding provider adapters.

The canonical application-facing embedding layer lives here. Runtime retrieval
code should depend on these providers; low-level SDK clients stay in
``src.services``.
"""

from src.adapters.embeddings.base import EmbeddingProvider
from src.adapters.embeddings.bge_m3 import BgeM3EmbeddingProvider


__all__ = [
    "BgeM3EmbeddingProvider",
    "EmbeddingProvider",
]
