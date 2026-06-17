"""Focused tests for make_rewrite_tool (#2565)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from telegram_bot.graph.tools.rewrite import make_rewrite_tool


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestRewriteToolMetadata:
    def test_rewrite_default_name(self):
        t = make_rewrite_tool(rewrite_fn=AsyncMock(return_value="rewritten"))
        assert t.name == "rewrite_query"

    def test_rewrite_custom_name(self):
        t = make_rewrite_tool(rewrite_fn=AsyncMock(return_value="x"), name="my_rewriter")
        assert t.name == "my_rewriter"

    def test_rewrite_description_is_non_empty(self):
        t = make_rewrite_tool(rewrite_fn=AsyncMock(return_value="x"))
        assert t.description

    def test_rewrite_tool_metadata_has_name(self):
        t = make_rewrite_tool(rewrite_fn=AsyncMock(return_value="x"))
        assert "name" in t.tool_metadata

    def test_rewrite_callable(self):
        t = make_rewrite_tool(rewrite_fn=AsyncMock(return_value="x"))
        assert callable(t)


# ---------------------------------------------------------------------------
# Rewrite output
# ---------------------------------------------------------------------------


class TestRewriteToolSuccess:
    @pytest.mark.asyncio
    async def test_rewritten_string_returned(self):
        t = make_rewrite_tool(rewrite_fn=AsyncMock(return_value="expanded query"))
        result = await t(query="short q")
        assert result == "expanded query"

    @pytest.mark.asyncio
    async def test_passes_query_to_fn(self):
        mock_fn = AsyncMock(return_value="better query")
        t = make_rewrite_tool(rewrite_fn=mock_fn)
        await t(query="original")
        mock_fn.assert_awaited_once_with("original")


# ---------------------------------------------------------------------------
# Failure fallback
# ---------------------------------------------------------------------------


class TestRewriteToolFailure:
    @pytest.mark.asyncio
    async def test_rewrite_fn_failure_returns_original_query(self):
        t = make_rewrite_tool(rewrite_fn=AsyncMock(side_effect=RuntimeError("llm down")))
        result = await t(query="my original query")
        assert result == "my original query"

    @pytest.mark.asyncio
    async def test_empty_query_returned_on_failure(self):
        t = make_rewrite_tool(rewrite_fn=AsyncMock(side_effect=ValueError("bad")))
        result = await t(query="")
        assert result == ""
