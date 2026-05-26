"""Unit tests for SDK-native voice tools (#2050).

Companion to ``GuardMiddleware`` (#2052). This PR introduces three
``create_agent``-compatible tool factories that #2051 will wire into the
voice handler:

* ``make_retrieve_tool`` — semantic retrieval against ``QdrantService``.
* ``make_rerank_tool`` — server-side document reranking.
* ``make_rewrite_tool`` — query rewrite for retry loops.

Each factory takes its dependencies as arguments so production code can
inject real services and tests can pass mocks. The tests verify the
``langchain.tools.@tool`` decorator shape (Pydantic args schema, async
``ainvoke``, name, description) so #2051 can plug the resulting
``BaseTool`` instances directly into ``create_agent(tools=[...])``.

Verified via Context7 (``/websites/langchain_oss_python_langchain``):
``@tool`` decorated callables expose ``BaseTool``-style ``ainvoke``,
``name`` and ``args`` attributes; the tool description comes from the
docstring.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.tools import BaseTool

from telegram_bot.graph.tools import (
    make_rerank_tool,
    make_retrieve_tool,
    make_rewrite_tool,
)


# ---------------------------------------------------------------------------
# retrieve_documents
# ---------------------------------------------------------------------------


class _FakeEmbeddings:
    """Stand-in for the production query embeddings bundle."""

    def __init__(self) -> None:
        self.dense = [0.1] * 4
        self.sparse = {"indices": [0, 1], "values": [0.5, 0.5]}
        self.colbert = [[0.1, 0.2, 0.3, 0.4]]


def _make_qdrant_mock(results: list[dict] | None = None) -> MagicMock:
    qdrant = MagicMock(name="QdrantService")
    if results is None:
        results = [
            {"id": "doc-1", "text": "пример квартиры", "score": 0.92},
            {"id": "doc-2", "text": "вторая квартира", "score": 0.81},
        ]
    qdrant.hybrid_search_rrf_colbert = AsyncMock(return_value=(results, {"latency_ms": 12}))
    return qdrant


async def _embed_query_async(_text: str) -> _FakeEmbeddings:
    return _FakeEmbeddings()


def test_retrieve_tool_is_a_basetool():
    tool = make_retrieve_tool(qdrant=_make_qdrant_mock(), embed_query=_embed_query_async)
    assert isinstance(tool, BaseTool), (
        "make_retrieve_tool must return a langchain BaseTool so create_agent "
        "can pick it up via tools=[...] (#2051)."
    )


def test_retrieve_tool_has_descriptive_name_and_doc():
    tool = make_retrieve_tool(qdrant=_make_qdrant_mock(), embed_query=_embed_query_async)
    assert tool.name == "retrieve_documents"
    assert tool.description, "Tool must expose a non-empty description for the model."


def test_retrieve_tool_args_schema_is_pydantic():
    tool = make_retrieve_tool(qdrant=_make_qdrant_mock(), embed_query=_embed_query_async)
    schema = tool.args_schema
    assert schema is not None, "args_schema must be set so the LLM gets a typed JSON schema."
    fields = schema.model_fields if hasattr(schema, "model_fields") else schema.__fields__
    assert "query" in fields
    assert "k" in fields


async def test_retrieve_tool_ainvoke_returns_documents():
    qdrant = _make_qdrant_mock()
    tool = make_retrieve_tool(qdrant=qdrant, embed_query=_embed_query_async)

    out = await tool.ainvoke({"query": "квартира в Несебре", "k": 5})

    assert isinstance(out, list)
    assert len(out) == 2
    assert out[0]["id"] == "doc-1"
    qdrant.hybrid_search_rrf_colbert.assert_awaited_once()
    call_kwargs = qdrant.hybrid_search_rrf_colbert.await_args.kwargs
    # Embeddings forwarded; k forwarded.
    assert call_kwargs.get("k") == 5


async def test_retrieve_tool_uses_default_k_when_unspecified():
    qdrant = _make_qdrant_mock()
    tool = make_retrieve_tool(qdrant=qdrant, embed_query=_embed_query_async, default_k=12)

    await tool.ainvoke({"query": "test"})

    call_kwargs = qdrant.hybrid_search_rrf_colbert.await_args.kwargs
    assert call_kwargs.get("k") == 12


async def test_retrieve_tool_returns_empty_on_qdrant_error():
    """Tool failures must not crash the agent; the LLM gets an empty list."""
    qdrant = MagicMock(name="QdrantService")
    qdrant.hybrid_search_rrf_colbert = AsyncMock(side_effect=RuntimeError("qdrant down"))
    tool = make_retrieve_tool(qdrant=qdrant, embed_query=_embed_query_async)

    out = await tool.ainvoke({"query": "anything"})

    assert out == []


# ---------------------------------------------------------------------------
# rerank_documents
# ---------------------------------------------------------------------------


async def test_rerank_tool_is_a_basetool_and_named():
    async def _rerank(_query: str, docs: list[dict]) -> list[dict]:
        return docs[::-1]

    tool = make_rerank_tool(rerank_fn=_rerank)
    assert isinstance(tool, BaseTool)
    assert tool.name == "rerank_documents"
    assert tool.description


async def test_rerank_tool_returns_reordered_documents():
    async def _rerank(_query: str, docs: list[dict]) -> list[dict]:
        # Stable sort by length desc to make the reorder visible.
        return sorted(docs, key=lambda d: len(d.get("text", "")), reverse=True)

    tool = make_rerank_tool(rerank_fn=_rerank)
    out = await tool.ainvoke(
        {
            "query": "квартира",
            "documents": [
                {"id": "a", "text": "short"},
                {"id": "b", "text": "longer document"},
            ],
        }
    )
    assert [d["id"] for d in out] == ["b", "a"]


async def test_rerank_tool_returns_input_on_error():
    async def _rerank(_query: str, _docs: list[dict]) -> list[dict]:
        raise RuntimeError("reranker offline")

    tool = make_rerank_tool(rerank_fn=_rerank)
    docs = [{"id": "a"}]
    out = await tool.ainvoke({"query": "q", "documents": docs})
    assert out == docs


# ---------------------------------------------------------------------------
# rewrite_query
# ---------------------------------------------------------------------------


async def test_rewrite_tool_is_a_basetool_and_named():
    async def _rewrite(_query: str) -> str:
        return "(rewritten)"

    tool = make_rewrite_tool(rewrite_fn=_rewrite)
    assert isinstance(tool, BaseTool)
    assert tool.name == "rewrite_query"
    assert tool.description


async def test_rewrite_tool_returns_string():
    captured: dict[str, str] = {}

    async def _rewrite(query: str) -> str:
        captured["query"] = query
        return f"улучшенный: {query}"

    tool = make_rewrite_tool(rewrite_fn=_rewrite)
    out = await tool.ainvoke({"query": "квартира 2 комнаты"})

    assert isinstance(out, str)
    assert "улучшенный" in out
    assert captured["query"] == "квартира 2 комнаты"


async def test_rewrite_tool_returns_original_on_error():
    async def _rewrite(_query: str) -> str:
        raise RuntimeError("LLM down")

    tool = make_rewrite_tool(rewrite_fn=_rewrite)
    out = await tool.ainvoke({"query": "оригинал"})
    assert out == "оригинал"


# ---------------------------------------------------------------------------
# Package exports
# ---------------------------------------------------------------------------


def test_package_exports_factories():
    from telegram_bot.graph import tools as tools_pkg

    for name in ("make_retrieve_tool", "make_rerank_tool", "make_rewrite_tool"):
        assert hasattr(tools_pkg, name), f"telegram_bot.graph.tools must export {name}"


@pytest.mark.parametrize(
    "factory_name, kwargs",
    [
        (
            "make_retrieve_tool",
            {"qdrant": _make_qdrant_mock(), "embed_query": _embed_query_async},
        ),
        ("make_rerank_tool", {"rerank_fn": AsyncMock(return_value=[])}),
        ("make_rewrite_tool", {"rewrite_fn": AsyncMock(return_value="x")}),
    ],
)
def test_factory_returns_basetool(factory_name: str, kwargs: dict):
    """Defensive check: each factory returns a BaseTool, not a raw callable."""
    from telegram_bot.graph import tools as tools_pkg

    factory = getattr(tools_pkg, factory_name)
    tool = factory(**kwargs)
    assert isinstance(tool, BaseTool)
