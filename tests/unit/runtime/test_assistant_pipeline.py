"""Tests for the runtime assistant pipeline seam."""

from __future__ import annotations

import sys
import types

import pytest

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

    classify_mod = types.ModuleType("src.runtime.graph.nodes.classify")
    classify_mod.classify_query = lambda _: "GENERAL"

    monkeypatch.setitem(sys.modules, "src.runtime.graph.nodes.classify", classify_mod)
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

    classify_mod = types.ModuleType("src.runtime.graph.nodes.classify")
    classify_mod.classify_query = lambda _: "GENERAL"
    monkeypatch.setitem(sys.modules, "src.runtime.graph.nodes.classify", classify_mod)

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
