"""BGE-M3 embedding service."""

from typing import cast

import httpx


class EmbeddingService:
    """Generate embeddings using BGE-M3 API."""

    def __init__(self, base_url: str):
        """Initialize embedding service.

        Args:
            base_url: BGE-M3 API URL (e.g., http://localhost:8001)
        """
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)

    async def embed_query(self, text: str) -> list[float]:
        """
        Generate dense embedding for query text.

        Args:
            text: Query text to embed

        Returns:
            Dense embedding vector (1024-dim for BGE-M3)
        """
        response = await self.client.post(
            f"{self.base_url}/encode/dense",
            json={"texts": [text]},  # API expects array of texts
        )
        response.raise_for_status()
        data = response.json()
        # Return first embedding (we only sent one text)
        return cast(list[float], data["dense_vecs"][0])

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
