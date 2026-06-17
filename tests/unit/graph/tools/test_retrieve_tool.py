"""Focused tests for make_retrieve_tool (#2565)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.graph.tools.retrieve import make_retrieve_tool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_tool(*, embed_results=None, qdrant_results=None, embed_raises=False, qdrant_raises=False):
    """Return a configured retrieve tool with injectable mocks."""

    async def embed_query(q: str):
        if embed_raises:
            raise RuntimeError("embed failure")
        emb = MagicMock()
        emb.dense = [0.1, 0.2]
        emb.sparse = {"indices": [], "values": []}
        emb.colbert = [[0.1]]
        return emb

    qdrant = MagicMock()
    if qdrant_raises:
        qdrant.hybrid_search_rrf_colbert = AsyncMock(side_effect=RuntimeError("qdrant failure"))
    else:
        results = (
            qdrant_results
            if qdrant_results is not None
            else [{"id": "1", "text": "doc1", "score": 0.9}]
        )
        qdrant.hybrid_search_rrf_colbert = AsyncMock(return_value=results)

    return make_retrieve_tool(qdrant=qdrant, embed_query=embed_query)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestRetrieveToolMetadata:
    def test_default_name(self):
        t = _make_tool()
        assert t.name == "retrieve_documents"

    def test_custom_name(self):
        async def embed(q):
            return MagicMock()

        qdrant = MagicMock()
        qdrant.hybrid_search_rrf_colbert = AsyncMock(return_value=[])
        t = make_retrieve_tool(qdrant=qdrant, embed_query=embed, name="my_retriever")
        assert t.name == "my_retriever"

    def test_description_is_non_empty(self):
        t = _make_tool()
        assert t.description

    def test_tool_metadata_has_name(self):
        t = _make_tool()
        assert "name" in t.tool_metadata

    def test_callable(self):
        t = _make_tool()
        assert callable(t)


# ---------------------------------------------------------------------------
# Args schema / default k
# ---------------------------------------------------------------------------


class TestRetrieveToolSchema:
    def test_args_schema_attached(self):
        t = _make_tool()
        assert hasattr(t, "tool_metadata")
        schema = t.tool_metadata.get("args_schema")
        assert schema is not None

    def test_default_k_reflected_in_schema(self):
        async def embed(q):
            return MagicMock()

        qdrant = MagicMock()
        qdrant.hybrid_search_rrf_colbert = AsyncMock(return_value=[])
        t = make_retrieve_tool(qdrant=qdrant, embed_query=embed, default_k=7)
        schema = t.tool_metadata["args_schema"]
        k_default = schema.model_fields["k"].default
        assert k_default == 7


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


class TestRetrieveToolSuccess:
    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        t = _make_tool(qdrant_results=[{"id": "1", "text": "hello", "score": 0.9}])
        result = await t(query="test", k=1)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["id"] == "1"

    @pytest.mark.asyncio
    async def test_normalizes_scored_point_objects(self):
        """ScoredPoint-like objects (not dicts) are converted to dicts."""

        class _ScoredPoint:
            def __init__(self):
                self.id = "pt1"
                self.score = 0.8
                self.payload = {"text": "doc content"}

        t = _make_tool(qdrant_results=[_ScoredPoint()])
        result = await t(query="test", k=1)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["id"] == "pt1"
        assert result[0]["score"] == 0.8
        assert result[0]["text"] == "doc content"

    @pytest.mark.asyncio
    async def test_tuple_response_unwrapped(self):
        """qdrant returns (results, meta) tuple — only results used."""
        docs = [{"id": "1", "text": "doc"}]
        meta = {"total": 1}

        async def embed(q):
            emb = MagicMock()
            emb.dense = [0.1]
            emb.sparse = {}
            emb.colbert = [[0.1]]
            return emb

        qdrant = MagicMock()
        qdrant.hybrid_search_rrf_colbert = AsyncMock(return_value=(docs, meta))
        t = make_retrieve_tool(qdrant=qdrant, embed_query=embed)
        result = await t(query="test", k=5)
        assert result == docs

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty_list(self):
        t = _make_tool(qdrant_results=[])
        result = await t(query="test", k=5)
        assert result == []


# ---------------------------------------------------------------------------
# Failure fallback
# ---------------------------------------------------------------------------


class TestRetrieveToolFailure:
    @pytest.mark.asyncio
    async def test_embed_failure_returns_empty(self):
        t = _make_tool(embed_raises=True)
        result = await t(query="test", k=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_qdrant_failure_returns_empty(self):
        t = _make_tool(qdrant_raises=True)
        result = await t(query="test", k=5)
        assert result == []


class TestRetrieveToolRetrievalServiceSeam:
    @pytest.mark.asyncio
    async def test_routes_through_retrieval_service_and_preserves_normalization(self):
        class _ScoredPoint:
            id = "pt1"
            score = 0.8
            payload = {"text": "doc content"}

        async def embed(query: str):
            emb = MagicMock()
            emb.dense = [0.1, 0.2]
            emb.sparse = {"indices": [1], "values": [0.5]}
            emb.colbert = [[0.3, 0.4]]
            return emb

        service = MagicMock()
        service.retrieve_vectors = AsyncMock(return_value=([_ScoredPoint()], {"total": 1}))
        qdrant = MagicMock()

        from telegram_bot.graph.tools import retrieve as retrieve_module

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(
                retrieve_module,
                "RetrievalService",
                MagicMock(return_value=service),
            )
            tool = make_retrieve_tool(qdrant=qdrant, embed_query=embed)
            result = await tool(query="test", k=3)

        service.retrieve_vectors.assert_awaited_once()
        request = service.retrieve_vectors.await_args.args[0]
        assert request.dense_vector == [0.1, 0.2]
        assert request.sparse_vector == {"indices": [1], "values": [0.5]}
        assert request.colbert_query == [[0.3, 0.4]]
        assert request.top_k == 3
        assert result == [{"id": "pt1", "score": 0.8, "text": "doc content"}]

    @pytest.mark.asyncio
    async def test_array_like_dense_does_not_raise(self):
        """Array-like dense vector must not trigger __bool__ (numpy ValueError fix, #2574)."""

        class _ArrayLike:
            """Minimal array-like that raises on bool() like numpy arrays do."""

            def __init__(self, data: list):
                self._data = data

            def __bool__(self):
                raise ValueError("The truth value of an array is ambiguous")

            def __iter__(self):
                return iter(self._data)

            def __len__(self):
                return len(self._data)

        async def embed(query: str):
            emb = MagicMock()
            emb.dense = _ArrayLike([0.1, 0.2, 0.3])
            emb.sparse = None
            emb.colbert = None
            return emb

        service = MagicMock()
        service.retrieve_vectors = AsyncMock(return_value=[{"id": "1", "score": 0.9}])

        from telegram_bot.graph.tools import retrieve as retrieve_module

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(
                retrieve_module,
                "RetrievalService",
                MagicMock(return_value=service),
            )
            tool = make_retrieve_tool(qdrant=MagicMock(), embed_query=embed)
            # Must not raise ValueError
            result = await tool(query="test", k=5)

        assert result == [{"id": "1", "score": 0.9}]
        request = service.retrieve_vectors.await_args.args[0]
        assert request.dense_vector != []  # passed through as-is, not replaced with []

    @pytest.mark.asyncio
    async def test_retrieval_service_failure_returns_empty_list(self):
        async def embed(query: str):
            emb = MagicMock()
            emb.dense = [0.1]
            emb.sparse = None
            emb.colbert = None
            return emb

        service = MagicMock()
        service.retrieve_vectors = AsyncMock(side_effect=RuntimeError("qdrant failure"))

        from telegram_bot.graph.tools import retrieve as retrieve_module

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(
                retrieve_module,
                "RetrievalService",
                MagicMock(return_value=service),
            )
            tool = make_retrieve_tool(qdrant=MagicMock(), embed_query=embed)
            result = await tool(query="test", k=5)

        assert result == []
