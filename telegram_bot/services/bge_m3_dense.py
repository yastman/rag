"""BGE-M3 dense embedding service client.

HTTP client for bge-m3-api /encode/dense endpoint.
Replaces VoyageService for dense retrieval when RETRIEVAL_DENSE_PROVIDER=bge_m3_api.
"""

import logging

import httpx


logger = logging.getLogger(__name__)


class BgeM3DenseService:
    """HTTP client for bge-m3-api dense embeddings.

    Provides drop-in replacement for VoyageService.embed_query/embed_documents.
    Uses local BGE-M3 model (1024-dim embeddings).
    """

    BATCH_SIZE = 32
    MAX_LENGTH = 512

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ):
        """Initialize service.

        Args:
            base_url: BGE-M3 API base URL
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)
        logger.info(f"BgeM3DenseService initialized: {base_url}")

    async def embed_query(self, text: str) -> list[float]:
        """Generate embedding for a single query.

        Args:
            text: Query text

        Returns:
            1024-dim embedding vector
        """
        response = await self._client.post(
            f"{self.base_url}/encode/dense",
            json={
                "texts": [text],
                "batch_size": 1,
                "max_length": self.MAX_LENGTH,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["dense_vecs"][0]

    async def embed_documents(
        self,
        texts: list[str],
        batch_size: int | None = None,
    ) -> list[list[float]]:
        """Generate embeddings for documents.

        Args:
            texts: List of document texts
            batch_size: Batch size (default: self.BATCH_SIZE)

        Returns:
            List of 1024-dim embedding vectors
        """
        if not texts:
            return []

        batch_size = batch_size or self.BATCH_SIZE
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = await self._client.post(
                f"{self.base_url}/encode/dense",
                json={
                    "texts": batch,
                    "batch_size": len(batch),
                    "max_length": self.MAX_LENGTH,
                },
            )
            response.raise_for_status()
            data = response.json()
            all_embeddings.extend(data["dense_vecs"])

        return all_embeddings

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()
