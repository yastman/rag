"""LangChain Embeddings wrappers for BGE-M3 API.

Provides BGEM3Embeddings (dense) and BGEM3SparseEmbeddings (sparse)
that wrap the local BGE-M3 REST API for use in LangGraph pipelines.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from langchain_core.embeddings import Embeddings


logger = logging.getLogger(__name__)


class BGEM3Embeddings(Embeddings):
    """LangChain Embeddings wrapper for BGE-M3 /encode/dense endpoint."""

    def __init__(
        self,
        base_url: str = "http://bge-m3:8000",
        timeout: float = 120.0,
        batch_size: int = 32,
        max_length: int = 512,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.batch_size = batch_size
        self.max_length = max_length

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        all_embeddings: list[list[float]] = []
        async with self._make_client() as client:
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i : i + self.batch_size]
                response = await client.post(
                    f"{self.base_url}/encode/dense",
                    json={
                        "texts": batch,
                        "batch_size": len(batch),
                        "max_length": self.max_length,
                    },
                )
                response.raise_for_status()
                data = response.json()
                all_embeddings.extend(data["dense_vecs"])
        return all_embeddings

    async def aembed_query(self, text: str) -> list[float]:
        result = await self.aembed_documents([text])
        return result[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return asyncio.get_event_loop().run_until_complete(self.aembed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return asyncio.get_event_loop().run_until_complete(self.aembed_query(text))


class BGEM3SparseEmbeddings:
    """Sparse embeddings wrapper for BGE-M3 /encode/sparse endpoint."""

    def __init__(
        self,
        base_url: str = "http://bge-m3:8000",
        timeout: float = 120.0,
        max_length: int = 512,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_length = max_length

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout)

    async def aembed_query(self, text: str) -> dict[str, Any]:
        async with self._make_client() as client:
            response = await client.post(
                f"{self.base_url}/encode/sparse",
                json={"texts": [text], "max_length": self.max_length},
            )
            response.raise_for_status()
            data = response.json()
            return data["sparse_vecs"][0]

    async def aembed_documents(self, texts: list[str]) -> list[dict[str, Any]]:
        if not texts:
            return []
        async with self._make_client() as client:
            response = await client.post(
                f"{self.base_url}/encode/sparse",
                json={"texts": texts, "max_length": self.max_length},
            )
            response.raise_for_status()
            data = response.json()
            return data["sparse_vecs"]
