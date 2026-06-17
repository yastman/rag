"""Focused tests for make_rerank_tool (#2565)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from telegram_bot.graph.tools.rerank import make_rerank_tool


DOCS = [
    {"id": "1", "text": "first doc", "score": 0.5},
    {"id": "2", "text": "second doc", "score": 0.9},
]
REORDERED = [DOCS[1], DOCS[0]]


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestRerankToolMetadata:
    def test_rerank_default_name(self):
        t = make_rerank_tool(rerank_fn=AsyncMock(return_value=REORDERED))
        assert t.name == "rerank_documents"

    def test_rerank_custom_name(self):
        t = make_rerank_tool(rerank_fn=AsyncMock(return_value=[]), name="my_reranker")
        assert t.name == "my_reranker"

    def test_rerank_description_is_non_empty(self):
        t = make_rerank_tool(rerank_fn=AsyncMock(return_value=[]))
        assert t.description

    def test_rerank_tool_metadata_has_name(self):
        t = make_rerank_tool(rerank_fn=AsyncMock(return_value=[]))
        assert "name" in t.tool_metadata

    def test_rerank_callable(self):
        t = make_rerank_tool(rerank_fn=AsyncMock(return_value=[]))
        assert callable(t)


# ---------------------------------------------------------------------------
# Reorder output
# ---------------------------------------------------------------------------


class TestRerankToolSuccess:
    @pytest.mark.asyncio
    async def test_reordered_output_returned(self):
        t = make_rerank_tool(rerank_fn=AsyncMock(return_value=REORDERED))
        result = await t(query="q", documents=DOCS)
        assert result == REORDERED

    @pytest.mark.asyncio
    async def test_passes_query_and_docs_to_fn(self):
        mock_fn = AsyncMock(return_value=REORDERED)
        t = make_rerank_tool(rerank_fn=mock_fn)
        await t(query="search term", documents=DOCS)
        mock_fn.assert_awaited_once_with("search term", DOCS)


# ---------------------------------------------------------------------------
# Failure fallback
# ---------------------------------------------------------------------------


class TestRerankToolFailure:
    @pytest.mark.asyncio
    async def test_rerank_fn_failure_returns_original_docs(self):
        t = make_rerank_tool(rerank_fn=AsyncMock(side_effect=RuntimeError("rerank failure")))
        result = await t(query="q", documents=DOCS)
        assert result == DOCS

    @pytest.mark.asyncio
    async def test_empty_docs_returned_on_failure(self):
        t = make_rerank_tool(rerank_fn=AsyncMock(side_effect=ValueError("bad")))
        result = await t(query="q", documents=[])
        assert result == []
