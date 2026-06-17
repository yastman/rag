"""Factory for embedding providers."""

import os

from src.adapters.embeddings.base import EmbeddingProvider
from src.adapters.embeddings.bge_m3 import BgeM3EmbeddingProvider
from src.adapters.embeddings.local_bge_m3 import LocalBgeM3Provider
from src.adapters.embeddings.openai_embeddings import OpenAIEmbeddingProvider


def get_embeddings_provider(provider_name: str | None = None) -> EmbeddingProvider:
    """Return the configured EmbeddingProvider instance.

    Args:
        provider_name: Optional provider name. If not supplied, read from
          the EMBEDDINGS_PROVIDER environment variable, defaulting to 'local_bge_m3'.

    Returns:
        An instance of EmbeddingProvider.

    Raises:
        ValueError: If the provider name is unknown.
    """
    raw_name = provider_name if provider_name is not None else os.getenv("EMBEDDINGS_PROVIDER")
    name = (raw_name or "local_bge_m3").strip().lower()

    if name == "local_bge_m3":
        return LocalBgeM3Provider()
    if name in {"bge_m3", "service_bge_m3"}:
        return BgeM3EmbeddingProvider()
    if name == "openai":
        return OpenAIEmbeddingProvider()
    raise ValueError(
        f"Unknown embeddings provider: '{name}'. Supported providers: "
        "'local_bge_m3', 'bge_m3', 'service_bge_m3', 'openai'."
    )
