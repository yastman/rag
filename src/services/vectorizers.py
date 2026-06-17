# src/services/vectorizers.py
"""Custom vectorizers for semantic cache (canonical home, #2049 slice 4).

Moved from ``telegram_bot/services/vectorizers.py`` as part of the fourth
slice of the reverse-layering fix tracked under #1948 / #2047 / #2049.
The legacy module is kept as a re-export shim.

UserBaseVectorizer (deepvk/USER2-base) has been archived to
archive/user-base/ (#2627). BGE-M3 is the canonical embedding provider.
"""

import logging
from typing import Any, cast

from redisvl.utils.vectorize import BaseVectorizer


logger = logging.getLogger(__name__)


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
            from src.services.bge_m3_client import BGEM3Client

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
