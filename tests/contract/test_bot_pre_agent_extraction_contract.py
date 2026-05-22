"""Drift guard for #1265 Slice 1 PR-5 — _bot_pre_agent extract.

Issue #1265 published a 6-PR Slice 1 plan that extracts pure module-level
helpers out of ``telegram_bot/bot.py`` before any class-level decomposition.

This contract pins **PR-5** (pre-agent semantic-cache helpers):

  - _build_pre_agent_state_contract  — pre-agent miss state contract builder
  - _has_async_method                — duck-type async-method probe
  - _get_or_compute_pre_agent_dense  — cached/computed dense embedding
  - _prepare_pre_agent_retrieval_vectors — sparse + ColBERT vector prep

These helpers feed the pre-agent semantic-cache check (#563/#1501) before
the SDK agent runs. They are pure: only depend on stdlib (asyncio, time,
logging) plus a lazy import of ``telegram_bot.pipelines.state_contract``
(which lives in the bot package and is fine to keep as a lazy import).

Mirrors PR-1..PR-4 contracts:

  1. ``telegram_bot/_bot_pre_agent.py`` exists, module-level imports
     are restricted to stdlib (no aiogram / langgraph / fastapi /
     langchain / redis / qdrant_client).
  2. All four helpers are exposed at module top.
  3. ``_has_async_method`` returns identical bool for sync/async/missing
     methods via the bot wrapper and the canonical module.
  4. ``_get_or_compute_pre_agent_dense`` and
     ``_prepare_pre_agent_retrieval_vectors`` are async and return
     identical results via either path on a representative cache/embed
     fixture.
  5. ``_build_pre_agent_state_contract`` returns identical state-contract
     dicts via either path.
  6. ``bot.py`` keeps each helper definition exactly once (the wrapper),
     so existing test patches like
     ``patch("telegram_bot.bot._get_or_compute_pre_agent_dense", ...)``
     keep intercepting the canonical call.
  7. ``bot.py`` line count is strictly below the 4863 baseline.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
NEW_MODULE = REPO_ROOT / "telegram_bot" / "_bot_pre_agent.py"
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"

HELPERS: tuple[str, ...] = (
    "_build_pre_agent_state_contract",
    "_has_async_method",
    "_get_or_compute_pre_agent_dense",
    "_prepare_pre_agent_retrieval_vectors",
)

FORBIDDEN_MODULE_LEVEL_IMPORTS: tuple[str, ...] = (
    "aiogram",
    "langgraph",
    "fastapi",
    "langchain",
    "redis",
    "qdrant_client",
)

BOT_PY_LINE_COUNT_CEILING = 4863


# ---------------------------------------------------------------------------
# Module existence + import hygiene
# ---------------------------------------------------------------------------


def test_bot_pre_agent_module_exists() -> None:
    assert NEW_MODULE.exists(), (
        f"#1265 Slice 1 PR-5: expected {NEW_MODULE.relative_to(REPO_ROOT)} "
        "to own the extracted pre-agent helpers."
    )


def test_bot_pre_agent_module_imports_are_clean() -> None:
    tree = ast.parse(NEW_MODULE.read_text())
    bad: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_MODULE_LEVEL_IMPORTS:
                    bad.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod in FORBIDDEN_MODULE_LEVEL_IMPORTS:
                bad.append(node.module or "")
    assert not bad, (
        f"_bot_pre_agent.py module-level imports must avoid the bot stack; "
        f"found forbidden roots: {bad}"
    )


@pytest.mark.parametrize("helper", HELPERS)
def test_helper_exposed(helper: str) -> None:
    """Each helper must be defined at module top-level."""
    tree = ast.parse(NEW_MODULE.read_text())
    names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert helper in names, f"_bot_pre_agent.{helper} must be defined at module top."


# ---------------------------------------------------------------------------
# _has_async_method parity
# ---------------------------------------------------------------------------


class _ProbeObj:
    async def aembed_query(self, query: str) -> list[float]:  # pragma: no cover
        return [0.0]

    def sync_method(self) -> int:
        return 1


@pytest.mark.parametrize(
    ("attr", "expected"),
    [
        ("aembed_query", True),  # async method
        ("sync_method", False),  # sync method
        ("missing_method", False),  # absent
    ],
)
def test_has_async_method_byte_for_byte_parity(attr: str, expected: bool) -> None:
    from telegram_bot import _bot_pre_agent, bot

    probe = _ProbeObj()
    assert bot._has_async_method(probe, attr) == expected
    assert _bot_pre_agent._has_async_method(probe, attr) == expected


# ---------------------------------------------------------------------------
# _get_or_compute_pre_agent_dense parity
# ---------------------------------------------------------------------------


class _FakeCache:
    def __init__(self) -> None:
        self._embeddings: dict[str, list[float]] = {}
        self._sparse: dict[str, dict] = {}
        self.stored_dense: list[tuple[str, list[float]]] = []

    async def get_embedding(self, query: str) -> list[float] | None:
        return self._embeddings.get(query)

    async def store_embedding(self, query: str, vec: list[float]) -> None:
        self._embeddings[query] = vec
        self.stored_dense.append((query, vec))

    async def get_sparse_embedding(self, query: str) -> dict | None:
        return self._sparse.get(query)

    async def store_sparse_embedding(self, query: str, sparse: dict) -> None:
        self._sparse[query] = sparse


class _FakeEmbeddings:
    """Embeddings that returns a tuple (vec, processing_s) for dense, plus
    sparse + ColBERT for hybrid encode."""

    async def aembed_dense_query(self, query: str) -> tuple[list[float], float]:
        return [0.1, 0.2, 0.3], 0.05

    async def aembed_query(self, query: str) -> list[float]:
        return [0.4, 0.5]

    async def aembed_hybrid_with_colbert(
        self, query: str
    ) -> tuple[list[float], dict, list[list[float]]]:
        return [0.1], {"indices": [1, 2], "values": [0.7, 0.8]}, [[0.9, 1.0]]

    async def aembed_colbert_query(self, query: str) -> list[list[float]]:
        return [[0.5, 0.5]]


@pytest.mark.asyncio
async def test_get_or_compute_pre_agent_dense_parity() -> None:
    from telegram_bot import _bot_pre_agent, bot

    cache_a = _FakeCache()
    cache_b = _FakeCache()
    emb = _FakeEmbeddings()
    rag_a: dict = {}
    rag_b: dict = {}

    a = await bot._get_or_compute_pre_agent_dense(cache_a, emb, "hello", rag_a)
    b = await _bot_pre_agent._get_or_compute_pre_agent_dense(cache_b, emb, "hello", rag_b)

    assert a == b == [0.1, 0.2, 0.3]
    # bge_model_processing_ms recorded in both
    assert "bge_model_processing_ms" in rag_a
    assert "bge_model_processing_ms" in rag_b
    assert rag_a["bge_model_processing_ms"] == rag_b["bge_model_processing_ms"]
    # both cached the result
    assert cache_a._embeddings == cache_b._embeddings == {"hello": [0.1, 0.2, 0.3]}


@pytest.mark.asyncio
async def test_get_or_compute_pre_agent_dense_uses_cache() -> None:
    """When the cache already has the embedding, no encode runs."""
    from telegram_bot import _bot_pre_agent

    cache = _FakeCache()
    cache._embeddings["cached_query"] = [9.0, 9.0]
    emb = _FakeEmbeddings()
    rag: dict = {}

    out = await _bot_pre_agent._get_or_compute_pre_agent_dense(cache, emb, "cached_query", rag)
    assert out == [9.0, 9.0]
    assert "bge_model_processing_ms" not in rag  # short-circuit before encode
    assert "pre_agent_embed_ms" not in rag  # only set on the encode path


# ---------------------------------------------------------------------------
# _prepare_pre_agent_retrieval_vectors parity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_pre_agent_retrieval_vectors_parity() -> None:
    from telegram_bot import _bot_pre_agent, bot

    cache_a = _FakeCache()
    cache_b = _FakeCache()
    emb = _FakeEmbeddings()
    rag_a: dict = {}
    rag_b: dict = {}
    dense = [0.1, 0.2]

    await bot._prepare_pre_agent_retrieval_vectors(cache_a, emb, "q", dense, rag_a)
    await _bot_pre_agent._prepare_pre_agent_retrieval_vectors(cache_b, emb, "q", dense, rag_b)

    for key in (
        "cache_key_embedding",
        "cache_key_sparse",
        "cache_key_colbert",
    ):
        assert key in rag_a, f"bot path missing {key}"
        assert key in rag_b, f"canonical missing {key}"
        assert rag_a[key] == rag_b[key], f"{key} parity break"

    assert rag_a["cache_key_embedding"] == dense
    assert rag_a["cache_key_sparse"] == {"indices": [1, 2], "values": [0.7, 0.8]}
    assert rag_a["cache_key_colbert"] == [[0.9, 1.0]]


# ---------------------------------------------------------------------------
# _build_pre_agent_state_contract parity
# ---------------------------------------------------------------------------


def test_build_pre_agent_state_contract_parity() -> None:
    from telegram_bot import _bot_pre_agent, bot

    common_kwargs: dict[str, object] = {
        "rag_result_store": {"filters": {"city": "Sofia"}},
        "query_type": "DOMAIN_SPECIFIC",
        "topic_hint": "apartments",
        "dense_vector": [0.1, 0.2],
        "sparse_vector": {"indices": [1], "values": [0.5]},
        "colbert_query": [[0.3, 0.4]],
        "grounding_mode": "normal",
        "filters": None,
    }
    a = bot._build_pre_agent_state_contract(**common_kwargs)
    b = _bot_pre_agent._build_pre_agent_state_contract(**common_kwargs)

    # Both return the same TypedDict-shaped payload — compare keys + values.
    assert isinstance(a, dict)
    assert isinstance(b, dict)
    assert a == b


def test_build_pre_agent_state_contract_explicit_filters_take_precedence() -> None:
    """``filters`` argument overrides ``rag_result_store['filters']``."""
    from telegram_bot import _bot_pre_agent

    out = _bot_pre_agent._build_pre_agent_state_contract(
        rag_result_store={"filters": {"city": "ignored"}},
        query_type="DOMAIN_SPECIFIC",
        topic_hint=None,
        dense_vector=None,
        sparse_vector=None,
        colbert_query=None,
        grounding_mode="normal",
        filters={"city": "Plovdiv"},
    )
    assert out["filters"] == {"city": "Plovdiv"}


# ---------------------------------------------------------------------------
# bot.py shape — wrapper preserved + line-count ratchet
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("helper", HELPERS)
def test_bot_py_defines_helper_at_most_once(helper: str) -> None:
    """``bot.py`` keeps the wrapper exactly once.

    Existing tests patch ``telegram_bot.bot._get_or_compute_pre_agent_dense``
    and similar — those patches must continue to intercept the bot's call.
    """
    src = BOT_PY.read_text()
    pattern = re.compile(rf"^(async\s+def|def)\s+{re.escape(helper)}\(", re.MULTILINE)
    matches = pattern.findall(src)
    assert len(matches) == 1, (
        f"bot.py defines `{helper}` {len(matches)} times; expected exactly 1 "
        "(the thin wrapper that delegates to _bot_pre_agent — preserves "
        "patch('telegram_bot.bot._get_or_compute_pre_agent_dense', ...))."
    )


def test_bot_py_line_count_below_ratchet() -> None:
    line_count = sum(1 for _ in BOT_PY.read_text().splitlines())
    assert line_count < BOT_PY_LINE_COUNT_CEILING, (
        f"bot.py line count is {line_count}; #1265 Slice 1 PR-5 ratchet "
        f"requires < {BOT_PY_LINE_COUNT_CEILING}."
    )


# ---------------------------------------------------------------------------
# Patch-point preservation — critical for existing tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bot_dense_helper_is_patchable_at_bot_module() -> None:
    """``patch('telegram_bot.bot._get_or_compute_pre_agent_dense', ...)`` must
    keep working after extraction so the existing test suite at
    ``tests/unit/test_bot_query_supervisor.py:125,180,337,412,491`` does not
    regress.
    """
    from unittest.mock import patch

    sentinel_vector = [9.99, 9.99, 9.99]

    with patch(
        "telegram_bot.bot._get_or_compute_pre_agent_dense",
        new=AsyncMock(return_value=sentinel_vector),
    ):
        from telegram_bot import bot as bot_mod

        out = await bot_mod._get_or_compute_pre_agent_dense(
            cache=_FakeCache(),
            embeddings=_FakeEmbeddings(),
            query="anything",
            result_store={},
        )
        assert out is sentinel_vector
