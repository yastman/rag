"""Tests for graph assembly (build_graph)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.graph.graph import build_graph


class TestBuildGraph:
    def test_graph_compiles_without_error(self):
        """build_graph returns a compiled graph object."""
        cache = AsyncMock()
        embeddings = AsyncMock()
        sparse = AsyncMock()
        qdrant = AsyncMock()

        graph = build_graph(
            cache=cache,
            embeddings=embeddings,
            sparse_embeddings=sparse,
            qdrant=qdrant,
        )
        assert graph is not None
        # Compiled graph should have an invoke method
        assert hasattr(graph, "ainvoke")

    def test_graph_has_expected_nodes(self):
        """Compiled graph contains all expected node names."""
        cache = AsyncMock()
        embeddings = AsyncMock()
        sparse = AsyncMock()
        qdrant = AsyncMock()

        graph = build_graph(
            cache=cache,
            embeddings=embeddings,
            sparse_embeddings=sparse,
            qdrant=qdrant,
        )

        # Get node names from the graph
        node_names = set(graph.get_graph().nodes.keys())
        expected_nodes = {
            "guard",
            "classify",
            "cache_check",
            "retrieve",
            "grade",
            "rerank",
            "generate",
            "rewrite",
            "cache_store",
            "respond",
            "__start__",
            "__end__",
        }
        assert expected_nodes.issubset(node_names), f"Missing nodes: {expected_nodes - node_names}"

    def test_graph_without_guard_when_filter_disabled(self):
        """Guard node excluded when content_filter_enabled=False."""
        cache = AsyncMock()
        embeddings = AsyncMock()
        sparse = AsyncMock()
        qdrant = AsyncMock()

        graph = build_graph(
            cache=cache,
            embeddings=embeddings,
            sparse_embeddings=sparse,
            qdrant=qdrant,
            content_filter_enabled=False,
        )

        node_names = set(graph.get_graph().nodes.keys())
        assert "guard" not in node_names
        assert "cache_check" in node_names

    def test_graph_with_optional_deps(self):
        """build_graph works with optional reranker and llm."""
        cache = AsyncMock()
        embeddings = AsyncMock()
        sparse = AsyncMock()
        qdrant = AsyncMock()
        reranker = AsyncMock()
        llm = AsyncMock()
        message = MagicMock()

        graph = build_graph(
            cache=cache,
            embeddings=embeddings,
            sparse_embeddings=sparse,
            qdrant=qdrant,
            reranker=reranker,
            llm=llm,
            message=message,
        )
        assert graph is not None
        assert hasattr(graph, "ainvoke")

    @pytest.mark.asyncio
    async def test_graph_ainvoke_allows_context_override(self):
        """ainvoke(context=...) should not fail with duplicate keyword arguments."""
        cache = AsyncMock()
        embeddings = AsyncMock()
        sparse = AsyncMock()
        qdrant = AsyncMock()

        graph = build_graph(
            cache=cache,
            embeddings=embeddings,
            sparse_embeddings=sparse,
            qdrant=qdrant,
        )

        with pytest.raises(Exception) as exc_info:
            # Empty state is intentionally invalid, but this call must not crash
            # with TypeError caused by duplicate "context" kwargs.
            await graph.ainvoke({}, context={"guard_mode": "soft"})

        assert "multiple values for keyword argument 'context'" not in str(exc_info.value)
