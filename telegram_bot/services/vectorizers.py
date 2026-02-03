# telegram_bot/services/vectorizers.py
"""Custom vectorizers for semantic cache.

UserBaseVectorizer: Local Russian embedding model (deepvk/USER-base).
Best-in-class for RU semantic matching (STS 74.35 on ruMTEB).
"""

import asyncio
import logging

import httpx


logger = logging.getLogger(__name__)


class UserBaseVectorizer:
    """Vectorizer using local USER-base service for Russian embeddings.

    Connects to USER-base FastAPI service running on port 8003.
    Returns 768-dimensional embeddings optimized for Russian text.

    Advantages over Voyage API:
    - Zero API cost (local)
    - Lower latency (~5ms vs ~30ms)
    - Best Russian semantic matching (ruMTEB #1)
    - On-premise (privacy)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8003",
        timeout: float = 5.0,
    ):
        """Initialize USER-base vectorizer.

        Args:
            base_url: URL of USER-base service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.timeout = timeout
        self.dims = 768  # USER-base output dimension
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def aembed(self, text: str) -> list[float]:
        """Generate embedding for single text (async).

        Args:
            text: Text to embed

        Returns:
            768-dimensional embedding vector
        """
        client = await self._get_client()
        response = await client.post("/embed", json={"text": text})
        response.raise_for_status()
        data = response.json()
        return data["embedding"]

    async def aembed_many(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts (async).

        Args:
            texts: List of texts to embed

        Returns:
            List of 768-dimensional embedding vectors
        """
        client = await self._get_client()
        response = await client.post("/embed_batch", json={"texts": texts})
        response.raise_for_status()
        data = response.json()
        return data["embeddings"]

    def embed(self, text: str) -> list[float]:
        """Generate embedding for single text (sync wrapper).

        Args:
            text: Text to embed

        Returns:
            768-dimensional embedding vector
        """
        return asyncio.run(self.aembed(text))

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts (sync wrapper).

        Args:
            texts: List of texts to embed

        Returns:
            List of 768-dimensional embedding vectors
        """
        return asyncio.run(self.aembed_many(texts))

    async def aclose(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
