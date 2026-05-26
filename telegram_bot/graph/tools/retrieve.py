"""``retrieve_documents`` tool factory for ``create_agent`` (#2050).

Wraps the project's hybrid RRF + ColBERT retrieval into a thin SDK tool.
The tool itself does NOT own the embedder or the Qdrant connection —
both are passed in by ``make_retrieve_tool`` so production code can wire
the singleton services (#2051) and tests can inject mocks.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field, create_model


logger = logging.getLogger(__name__)


def _result_to_dict(item: Any) -> dict[str, Any]:
    """Normalize a Qdrant result into a serialisable dict.

    Accepts the dict shape used elsewhere in the runtime as well as the
    ``ScoredPoint``-like objects returned by ``qdrant-client``.
    """
    if isinstance(item, dict):
        return item
    out: dict[str, Any] = {}
    for attr in ("id", "score"):
        value = getattr(item, attr, None)
        if value is not None:
            out[attr] = value
    payload = getattr(item, "payload", None)
    if isinstance(payload, dict):
        out.update(payload)
    return out


def _make_retrieve_schema(default_k: int) -> type[BaseModel]:
    """Build the args schema with a configurable default ``k``.

    The Pydantic class-level default is fixed at definition time. We rebuild
    the schema per factory call so ``default_k`` flows through to the
    LLM-visible JSON schema and to validated inputs (#2050).
    """
    return create_model(
        "RetrieveDocumentsInput",
        query=(
            str,
            Field(description="Natural-language query against the property knowledge base."),
        ),
        k=(
            int,
            Field(
                default=default_k,
                ge=1,
                le=100,
                description=f"Maximum documents to return (1..100). Defaults to {default_k}.",
            ),
        ),
    )


def make_retrieve_tool(
    *,
    qdrant: Any,
    embed_query: Callable[[str], Awaitable[Any]],
    name: str = "retrieve_documents",
    default_k: int = 20,
) -> BaseTool:
    """Return a ``BaseTool`` wrapping hybrid retrieval.

    Args:
        qdrant: Object exposing ``hybrid_search_rrf_colbert(dense_query=,
            sparse_query=, colbert_query=, k=)`` — typically the production
            ``src.runtime.services.qdrant.QdrantService`` instance.
        embed_query: Async callable that returns an object with ``dense``,
            ``sparse`` and ``colbert`` attributes (the unified query
            embeddings bundle used by the rest of the runtime).
        name: Tool name surfaced to the LLM via tool calls.
        default_k: Default ``k`` when the LLM omits it.
    """

    @tool(name, args_schema=_make_retrieve_schema(default_k))
    async def retrieve_documents(query: str, k: int = default_k) -> list[dict[str, Any]]:
        """Search the property knowledge base for documents relevant to ``query``.

        Uses hybrid retrieval (dense + sparse + ColBERT) with reciprocal-rank
        fusion. Returns up to ``k`` documents ordered by relevance score
        (highest first). Returns an empty list if retrieval fails — the
        agent should then ask a clarifying question rather than fabricate
        an answer.
        """
        try:
            embeddings = await embed_query(query)
        except Exception:
            logger.warning("retrieve_documents: embed_query failed", exc_info=True)
            return []

        try:
            response = await qdrant.hybrid_search_rrf_colbert(
                dense_query=getattr(embeddings, "dense", None),
                sparse_query=getattr(embeddings, "sparse", None),
                colbert_query=getattr(embeddings, "colbert", None),
                k=k,
            )
        except Exception:
            logger.warning("retrieve_documents: qdrant search failed", exc_info=True)
            return []

        # Some helpers return ``(results, meta)`` tuples; others return a list.
        results = response[0] if isinstance(response, tuple) else response
        if not results:
            return []
        return [_result_to_dict(item) for item in results]

    return retrieve_documents
