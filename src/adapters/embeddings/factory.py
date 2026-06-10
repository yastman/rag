"""Factory for embedding providers."""

import os

from src.adapters.embeddings.base import EmbeddingProvider
from src.adapters.embeddings.local_bge_m3 import LocalBgeM3Provider
from src.adapters.embeddings.openai_embeddings import OpenAIEmbeddingProvider
from src.adapters.embeddings.service_bge_m3 import ServiceBgeM3Provider


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
    name: str = (provider_name or os.getenv("EMBEDDINGS_PROVIDER", "local_bge_m3")).strip().lower()

    if name == "local_bge_m3":
        return LocalBgeM3Provider()
    if name == "service_bge_m3":
        return ServiceBgeM3Provider()
    if name == "openai":
        return OpenAIEmbeddingProvider()
    raise ValueError(
        f"Unknown embeddings provider: '{name}'. Supported providers: "
        "'local_bge_m3', 'service_bge_m3', 'openai'."
    )
