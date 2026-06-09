"""OpenAI embedding provider (placeholder / implementation)."""

import os
from collections.abc import Sequence

from src.adapters.embeddings.base import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embedding provider (placeholder / implementation)."""

    def __init__(self, model: str = "text-embedding-3-small", api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "dummy-key")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Encode texts via OpenAI Embeddings API."""
        if not texts:
            return []
        client = self._get_client()
        response = await client.embeddings.create(
            input=list(texts),
            model=self.model,
        )
        return [data.embedding for data in response.data]
