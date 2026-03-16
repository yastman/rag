# telegram_bot/services/vectorizers.py
"""Custom vectorizers for semantic cache.

UserBaseVectorizer: Local Russian embedding model (deepvk/USER-base).
Best-in-class for RU semantic matching (STS 74.35 on ruMTEB).
"""

import logging
from typing import Any, cast

import httpx
from redisvl.utils.vectorize import BaseVectorizer


logger = logging.getLogger(__name__)


class UserBaseVectorizer(BaseVectorizer):
    """Vectorizer using local USER-base service for Russian embeddings.

    Connects to USER-base FastAPI service running on port 8003/8000.
    Returns 768-dimensional embeddings optimized for Russian text.

    Advantages over Voyage API:
    - Zero API cost (local)
    - Lower latency (~5ms vs ~30ms)
    - Best Russian semantic matching (ruMTEB #1)
    - On-premise (privacy)
    """

    model: str = "deepvk/USER2-base"
    dims: int = 768
    base_url: str = "http://localhost:8003"
    timeout: float = 5.0

    # Pydantic config to allow arbitrary types (for httpx client)
    model_config = {"arbitrary_types_allowed": True}

    # Private attributes (not Pydantic fields)
    _sync_client: httpx.Client | None = None
    _async_client: httpx.AsyncClient | None = None

    def __init__(self, base_url: str = "http://localhost:8003", **kwargs: Any):
        """Initialize USER-base vectorizer.

        Args:
            base_url: URL of USER-base service
            **kwargs: Additional arguments for BaseVectorizer
        """
        super().__init__(base_url=base_url, **kwargs)

    def _get_sync_client(self) -> httpx.Client:
        """Get or create sync HTTP client."""
        if self._sync_client is None:
            self._sync_client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._sync_client

    async def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._async_client

    def embed(
        self,
        text: str,
        _preprocess: Any = None,
        _as_buffer: bool = False,
        **kwargs: Any,
    ) -> list[float]:
        """Generate embedding for single text (sync).

        Args:
            text: Text to embed
            _preprocess: Optional preprocessing function (unused)
            _as_buffer: Return as buffer (unused)
            **kwargs: Additional arguments (unused)

        Returns:
            768-dimensional embedding vector
        """
        client = self._get_sync_client()
        response = client.post("/embed", json={"text": text})
        response.raise_for_status()
        data = response.json()
        return cast(list[float], data["embedding"])

    def embed_many(
        self,
        texts: list[str],
        _preprocess: Any = None,
        _as_buffer: bool = False,
        **kwargs: Any,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts (sync).

        Args:
            texts: List of texts to embed
            _preprocess: Optional preprocessing function (unused)
            _as_buffer: Return as buffer (unused)
            **kwargs: Additional arguments (unused)

        Returns:
            List of 768-dimensional embedding vectors
        """
        client = self._get_sync_client()
        response = client.post("/embed_batch", json={"texts": texts})
        response.raise_for_status()
        data = response.json()
        return cast(list[list[float]], data["embeddings"])

    async def aembed(
        self,
        text: str,
        _preprocess: Any = None,
        _as_buffer: bool = False,
        **kwargs: Any,
    ) -> list[float]:
        """Generate embedding for single text (async).

        Args:
            text: Text to embed
            _preprocess: Optional preprocessing function (unused)
            _as_buffer: Return as buffer (unused)
            **kwargs: Additional arguments (unused)

        Returns:
            768-dimensional embedding vector
        """
        client = await self._get_async_client()
        response = await client.post("/embed", json={"text": text})
        response.raise_for_status()
        data = response.json()
        return cast(list[float], data["embedding"])

    async def aembed_many(
        self,
        texts: list[str],
        _preprocess: Any = None,
        _as_buffer: bool = False,
        **kwargs: Any,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts (async).

        Args:
            texts: List of texts to embed
            _preprocess: Optional preprocessing function (unused)
            _as_buffer: Return as buffer (unused)
            **kwargs: Additional arguments (unused)

        Returns:
            List of 768-dimensional embedding vectors
        """
        client = await self._get_async_client()
        response = await client.post("/embed_batch", json={"texts": texts})
        response.raise_for_status()
        data = response.json()
        return cast(list[list[float]], data["embeddings"])

    async def aclose(self):
        """Close HTTP clients."""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None


class BgeM3CacheVectorizer(BaseVectorizer):
    """Lightweight vectorizer for SemanticCache index schema (1024-dim BGE-M3).

    Used only for Redis index creation. Actual embeddings are passed via
    ``vector=`` parameter to ``acheck()``/``astore()``, so embed methods
    are rarely called. Falls back to BGEM3Client if called.
    """

    model: str = "BAAI/bge-m3"
    dims: int = 1024
    base_url: str = "http://bge-m3:8000"
    timeout: float = 30.0

    model_config = {"arbitrary_types_allowed": True}

    _bge_client: Any = None  # BGEM3Client, lazy-init

    def __init__(self, base_url: str = "http://bge-m3:8000", **kwargs: Any):
        super().__init__(base_url=base_url, **kwargs)

    def _get_bge_client(self) -> Any:
        if self._bge_client is None:
            from telegram_bot.services.bge_m3_client import BGEM3Client

            self._bge_client = BGEM3Client(base_url=self.base_url, timeout=self.timeout)
        return self._bge_client

    def embed(
        self, text: str, _preprocess: Any = None, _as_buffer: bool = False, **kwargs: Any
    ) -> list[float]:
        raise NotImplementedError(
            "BgeM3CacheVectorizer: use vector= parameter instead of prompt-based embedding"
        )

    def embed_many(
        self, texts: list[str], _preprocess: Any = None, _as_buffer: bool = False, **kwargs: Any
    ) -> list[list[float]]:
        raise NotImplementedError(
            "BgeM3CacheVectorizer: use vector= parameter instead of prompt-based embedding"
        )

    async def aembed(
        self, text: str, _preprocess: Any = None, _as_buffer: bool = False, **kwargs: Any
    ) -> list[float]:
        """Fallback: generate embedding via BGEM3Client (should rarely be called)."""
        client = self._get_bge_client()
        result = await client.encode_dense([text])
        return cast(list[float], result.vectors[0])

    async def aembed_many(
        self, texts: list[str], _preprocess: Any = None, _as_buffer: bool = False, **kwargs: Any
    ) -> list[list[float]]:
        """Fallback: generate embeddings via BGEM3Client (should rarely be called)."""
        client = self._get_bge_client()
        result = await client.encode_dense(texts)
        return cast(list[list[float]], result.vectors)
