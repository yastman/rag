"""Tests for the runtime assistant pipeline seam."""

from __future__ import annotations

import sys
import types


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

    async def fake_generate_response(**kwargs):
        return {
            "response": "answer",
            "llm_provider_model": "fake-model",
            "usage_details": {"input": 1, "output": 2},
        }

    classify_mod = types.ModuleType("src.runtime.graph.nodes.classify")
    classify_mod.classify_query = lambda _: "GENERAL"
    generate_mod = types.ModuleType("telegram_bot.services.generate_response")
    generate_mod.generate_response = fake_generate_response

    monkeypatch.setitem(sys.modules, "src.runtime.graph.nodes.classify", classify_mod)
    monkeypatch.setitem(sys.modules, "telegram_bot.services.generate_response", generate_mod)
    monkeypatch.setattr(
        "src.runtime.pipeline.assistant_pipeline.rag_pipeline",
        fake_rag_pipeline,
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
        ),
    )

    assert result.response_text == "answer"
    assert result.route == "rag_search"
    assert result.retrieved_doc_ids == ["doc-1"]
    assert result.retrieved_sources == [{"title": "Doc 1", "url": "fixture://doc-1"}]
    assert result.llm_model == "fake-model"
