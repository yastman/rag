"""Tests for the runtime assistant pipeline seam."""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.contracts import AssistantResult
from src.runtime.generation import GenerationResult


async def test_run_assistant_pipeline_returns_assistant_result(monkeypatch) -> None:
    from src.core import AssistantRequest, CoreDependencies, UserContext
    from src.runtime.pipeline.assistant_pipeline import run_assistant_pipeline

    async def fake_rag_pipeline(**kwargs):
        return {
            "documents": [
                {
                    "content": "fact",
                    "metadata": {
                        "source_id": "doc-1",
                        "title": "Doc 1",
                        "url": "fixture://doc-1",
                    },
                }
            ],
            "cache_hit": False,
            "query_type": "GENERAL",
            "rerank_applied": True,
        }

    async def fake_generate_answer(_request):
        return GenerationResult(
            payload={
                "response": "answer",
                "llm_provider_model": "fake-model",
                "usage_details": {"input": 1, "output": 2},
            }
        )

    classify_mod = types.ModuleType("src.runtime.routing.classify")
    classify_mod.classify_query = lambda _: "GENERAL"

    monkeypatch.setitem(sys.modules, "src.runtime.routing.classify", classify_mod)
    monkeypatch.setattr(
        "src.runtime.pipeline.assistant_pipeline.rag_pipeline",
        fake_rag_pipeline,
    )
    monkeypatch.setattr(
        "src.runtime.pipeline.assistant_pipeline.generate_answer",
        fake_generate_answer,
    )

    result = await run_assistant_pipeline(
        AssistantRequest(
            query="q",
            collection="c",
            user_context=UserContext(user_id="42", session_id="s"),
            request_id="req-1",
        ),
        dependencies=CoreDependencies(
            cache=object(),
            embeddings=object(),
            sparse_embeddings=object(),
            qdrant=object(),
            config=object(),
        ),
    )

    assert result.response_text == "answer"
    assert result.route == "rag_search"
    assert result.retrieved_doc_ids == ["doc-1"]
    assert result.retrieved_sources == [{"title": "Doc 1", "url": "fixture://doc-1"}]
    assert result.llm_model == "fake-model"


# Regression test for #2967: pipeline must not swallow exceptions
async def test_run_assistant_pipeline_propagates_exception(monkeypatch) -> None:
    """Exceptions raised inside the pipeline must propagate, not be swallowed."""
    from src.core import AssistantRequest, CoreDependencies, UserContext
    from src.runtime.pipeline.assistant_pipeline import run_assistant_pipeline

    classify_mod = types.ModuleType("src.runtime.routing.classify")
    classify_mod.classify_query = lambda _: "GENERAL"
    monkeypatch.setitem(sys.modules, "src.runtime.routing.classify", classify_mod)

    async def exploding_rag_pipeline(**kwargs):
        raise RuntimeError("deliberate-test-explosion")

    monkeypatch.setattr(
        "src.runtime.pipeline.assistant_pipeline.rag_pipeline",
        exploding_rag_pipeline,
    )

    with pytest.raises(RuntimeError, match="deliberate-test-explosion"):
        await run_assistant_pipeline(
            AssistantRequest(
                query="q",
                collection="c",
                user_context=UserContext(user_id="42", session_id="s"),
                request_id="req-1",
            ),
            dependencies=CoreDependencies(
                cache=object(),
                embeddings=object(),
                sparse_embeddings=object(),
                qdrant=object(),
                config=object(),
            ),
        )


# ---------------------------------------------------------------------------
# #3208 — core-owned semantic cache store + truthful result metadata
# ---------------------------------------------------------------------------


def _doc() -> dict:
    return {
        "content": "fact",
        "metadata": {"source_id": "doc-1", "title": "Doc 1", "url": "fixture://doc-1"},
        "score": 0.9,
    }


def _cache_store_mocks():
    cache = MagicMock()
    cache.store_semantic = AsyncMock()
    return cache


async def _run(
    *,
    rag_result: dict | None = None,
    generation_payload: dict | None = None,
    cache: Any = None,
    config: Any = None,
    filters: dict | None = None,
) -> AssistantResult:
    from src.core import AssistantRequest, CoreDependencies, UserContext
    from src.runtime.pipeline.assistant_pipeline import run_assistant_pipeline

    rag = AsyncMock(
        return_value=rag_result
        or {
            "documents": [_doc()],
            "cache_hit": False,
            "query_type": "FAQ",
            "rerank_applied": False,
            "grade_confidence": 0.9,
            "cache_key_embedding": [0.1, 0.2, 0.3],
        }
    )
    gen = AsyncMock(
        return_value=GenerationResult(
            payload=generation_payload
            or {
                "response": "answer",
                "llm_provider_model": "fake-model",
                "usage_details": {"input": 1, "output": 2},
                "grounded": True,
                "legal_answer_safe": True,
                "semantic_cache_safe_reuse": True,
                "safe_fallback_used": False,
                "llm_call_count": 1,
            }
        )
    )

    dependencies = CoreDependencies(
        cache=cache if cache is not None else object(),
        embeddings=object(),
        sparse_embeddings=object(),
        qdrant=object(),
        config=config if config is not None else object(),
    )
    with (
        patch("src.runtime.routing.classify.classify_query", return_value="FAQ"),
        patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
        patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
    ):
        return await run_assistant_pipeline(
            AssistantRequest(
                query="топ студий у моря в Солнечном Берегу",
                collection="c",
                user_context=UserContext(user_id="42", session_id="s", role="client", filters=filters),
                request_id="req-3208",
            ),
            dependencies=dependencies,
        )


async def test_surfaces_truthful_cache_safety_metadata() -> None:
    result = await _run()

    assert result.grounded is True
    assert result.legal_answer_safe is True
    assert result.semantic_cache_safe_reuse is True
    assert result.safe_fallback_used is False
    assert result.grounding_mode == "normal"


async def test_stores_semantic_cache_with_filter_signature_and_role() -> None:
    cache = _cache_store_mocks()

    result = await _run(cache=cache, filters={"city": "Несебр"})

    cache.store_semantic.assert_awaited_once()
    kwargs = cache.store_semantic.await_args.kwargs
    assert kwargs["query"] == "топ студий у моря в Солнечном Берегу"
    assert kwargs["response"] == "answer"
    assert kwargs["vector"] == [0.1, 0.2, 0.3]
    assert kwargs["query_type"] == "FAQ"
    assert kwargs["cache_scope"] == "rag"
    assert kwargs["agent_role"] == "client"
    assert kwargs["filter_signature"] == "city=Несебр"
    metadata = kwargs["metadata"]
    assert metadata["grounding_mode"] == "normal"
    assert metadata["semantic_cache_safe_reuse"] is True
    assert metadata["cache_eligible"] is True
    assert result.response_text == "answer"


async def test_strict_unsafe_generation_skips_semantic_store() -> None:
    cache = _cache_store_mocks()

    await _run(
        cache=cache,
        generation_payload={
            "response": "fallback text",
            "llm_provider_model": "safe_fallback",
            "usage_details": None,
            "grounded": False,
            "legal_answer_safe": False,
            "semantic_cache_safe_reuse": False,
            "safe_fallback_used": True,
            "llm_call_count": 0,
        },
    )

    cache.store_semantic.assert_not_awaited()


async def test_provider_fallback_result_skips_semantic_store() -> None:
    cache = _cache_store_mocks()

    await _run(
        cache=cache,
        generation_payload={
            "response": "fallback answer",
            "llm_provider_model": "fallback",
            "usage_details": None,
            "grounded": False,
            "llm_call_count": 1,
            "fallback_used": True,
        },
    )

    cache.store_semantic.assert_not_awaited()


async def test_store_failure_preserves_response() -> None:
    cache = _cache_store_mocks()
    cache.store_semantic = AsyncMock(side_effect=RuntimeError("redis down"))

    result = await _run(cache=cache)

    assert result.response_text == "answer"
    assert result.route == "rag_search"
    assert result.error_type is None


async def test_cache_hit_result_skips_store_and_generation() -> None:
    cache = _cache_store_mocks()

    result = await _run(
        cache=cache,
        rag_result={
            "documents": [],
            "cache_hit": True,
            "response": "cached answer",
            "query_type": "FAQ",
        },
    )

    cache.store_semantic.assert_not_awaited()
    assert result.cache_hit is True
    assert result.route == "cache_hit"
    # Cache hits cannot know generation-time safety verdicts.
    assert result.grounded is None
    assert result.legal_answer_safe is None
    assert result.semantic_cache_safe_reuse is None


async def test_no_store_without_cache_key_embedding() -> None:
    cache = _cache_store_mocks()

    await _run(
        cache=cache,
        rag_result={
            "documents": [_doc()],
            "cache_hit": False,
            "query_type": "FAQ",
            "grade_confidence": 0.9,
        },
    )

    cache.store_semantic.assert_not_awaited()
