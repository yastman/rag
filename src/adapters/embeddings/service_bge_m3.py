"""Embedding provider that calls an external BGE-M3 REST service."""

import os
from collections.abc import Sequence

from src.adapters.embeddings.base import EmbeddingProvider
from src.services.bge_m3_client import BGEM3Client


class ServiceBgeM3Provider(EmbeddingProvider):
    """Embedding provider that calls an external BGE-M3 REST service."""

    def __init__(self, client: BGEM3Client | None = None, base_url: str | None = None) -> None:
        url = base_url or os.getenv("BGE_M3_URL", "http://bge-m3:8000") or "http://bge-m3:8000"
        self._client = client or BGEM3Client(base_url=url)

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Encode texts via external BGE-M3 service /encode/dense endpoint."""
        if not texts:
            return []
        result = await self._client.encode_dense(list(texts))
        return result.vectors

    async def aclose(self) -> None:
        """Close the underlying client."""
        await self._client.aclose()
