"""``rerank_documents`` tool factory for ``create_agent`` (#2050)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class RerankDocumentsInput(BaseModel):
    """Schema for the ``rerank_documents`` tool."""

    query: str = Field(description="Original natural-language query.")
    documents: list[dict[str, Any]] = Field(
        description="Documents to reorder, each carrying at minimum an ``id`` and ``text``.",
    )


def make_rerank_tool(
    *,
    rerank_fn: Callable[[str, list[dict[str, Any]]], Awaitable[list[dict[str, Any]]]],
    name: str = "rerank_documents",
) -> BaseTool:
    """Return a ``BaseTool`` that reranks an existing candidate list.

    Args:
        rerank_fn: Async callable ``(query, documents) -> reordered_documents``.
            Production wiring will pass either Voyage AI rerank or the
            ColBERT reranker depending on ``RERANK_PROVIDER``.
        name: Tool name surfaced to the LLM.

    On error, the original document list is returned unchanged so the
    agent can still proceed with the candidates it already has.
    """

    @tool(name, args_schema=RerankDocumentsInput)
    async def rerank_documents(query: str, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Reorder candidate documents by relevance to ``query``.

        Use this after ``retrieve_documents`` returns a wide candidate set
        and the model wants to prioritise the most relevant matches. The
        return value contains the same documents in a new order — never
        adds or drops items.
        """
        try:
            return await rerank_fn(query, documents)
        except Exception:
            logger.warning(
                "rerank_documents: rerank_fn failed; returning input order", exc_info=True
            )
            return documents

    return rerank_documents
