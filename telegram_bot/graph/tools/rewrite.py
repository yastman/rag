"""``rewrite_query`` tool factory for ``create_agent`` (#2050)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class RewriteQueryInput(BaseModel):
    """Schema for the ``rewrite_query`` tool."""

    query: str = Field(description="Original user query that returned weak retrieval results.")


def make_rewrite_tool(
    *,
    rewrite_fn: Callable[[str], Awaitable[str]],
    name: str = "rewrite_query",
) -> BaseTool:
    """Return a ``BaseTool`` that rewrites a query for retry retrieval.

    Args:
        rewrite_fn: Async callable ``(query) -> rewritten_query``. Production
            wiring will pass an LLM-backed rewrite helper that mirrors
            ``rewrite_node`` semantics (translit / synonym expansion /
            scope clarification).
        name: Tool name surfaced to the LLM.

    On error, the original query is returned unchanged so the agent can
    fall back to the previous retrieval attempt instead of crashing.
    """

    @tool(name, args_schema=RewriteQueryInput)
    async def rewrite_query(query: str) -> str:
        """Produce a rewritten query that may yield better retrieval matches.

        Use after ``retrieve_documents`` returns a poor candidate set and
        ``rerank_documents`` cannot rescue the order. The rewritten query
        usually expands synonyms or clarifies scope while preserving the
        user's intent.
        """
        try:
            return await rewrite_fn(query)
        except Exception:
            logger.warning(
                "rewrite_query: rewrite_fn failed; returning original query", exc_info=True
            )
            return query

    return rewrite_query
