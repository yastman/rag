"""Regression tests for make_retrieve_tool (#2574).

Verifies that array-like embedding objects with a raising or falsy __bool__
are forwarded correctly to RetrievalService and NOT replaced by [].
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.agents.retrieve_tool import make_retrieve_tool


class _BoolRaising:
    """Mimics a numpy array: __bool__ raises for non-scalar arrays."""

    def __init__(self, value: list) -> None:
        self._value = value

    def __bool__(self) -> bool:
        raise ValueError("The truth value of an array is ambiguous")

    def __repr__(self) -> str:
        return f"_BoolRaising({self._value})"


class TestRetrieveToolArrayEmbeddings:
    """Regression: array-like dense must not fall back to [] via truthiness check."""

    async def test_array_like_dense_forwarded_not_replaced(self):
        """dense attribute that is a _BoolRaising object must reach RetrievalService as-is."""
        array_dense = _BoolRaising([0.1] * 10)

        class _Embeddings:
            dense = array_dense
            sparse = None
            colbert = None

        embed_query = AsyncMock(return_value=_Embeddings())
        qdrant = MagicMock()

        service = MagicMock()
        service.retrieve_vectors = AsyncMock(return_value=[])

        with patch("telegram_bot.agents.retrieve_tool.RetrievalService", return_value=service):
            tool = make_retrieve_tool(qdrant=qdrant, embed_query=embed_query)
            await tool(query="test", k=5)

        service.retrieve_vectors.assert_awaited_once()
        request = service.retrieve_vectors.await_args.args[0]
        assert request.dense_vector is array_dense, (
            "array-like dense must not be replaced by [] via truthiness check"
        )

    async def test_none_dense_replaced_with_empty_list(self):
        """dense=None must be replaced with [] (explicit None check)."""

        class _EmbeddingsNone:
            dense = None
            sparse = None
            colbert = None

        embed_query = AsyncMock(return_value=_EmbeddingsNone())
        qdrant = MagicMock()

        service = MagicMock()
        service.retrieve_vectors = AsyncMock(return_value=[])

        with patch("telegram_bot.agents.retrieve_tool.RetrievalService", return_value=service):
            tool = make_retrieve_tool(qdrant=qdrant, embed_query=embed_query)
            await tool(query="test", k=5)

        service.retrieve_vectors.assert_awaited_once()
        request = service.retrieve_vectors.await_args.args[0]
        assert request.dense_vector == [], "None dense must fall back to [] via explicit None check"
