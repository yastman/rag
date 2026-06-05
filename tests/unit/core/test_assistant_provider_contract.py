"""Provider and HITL safety contract for the assistant core entrypoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch


def _deps():
    from src.core.assistant import CoreDependencies

    return CoreDependencies(
        cache=object(),
        embeddings=object(),
        sparse_embeddings=object(),
        qdrant=object(),
        reranker=None,
        llm=object(),
        config=None,
    )


async def test_fake_provider_path_returns_stable_assistant_result() -> None:
    from src.core.assistant import AssistantResult, run_assistant_request

    result = await run_assistant_request("hello", collection="core")

    assert isinstance(result, AssistantResult)
    assert result.route == "error"
    assert result.error_type == "service_unavailable"
    assert result.proposed_crm_action is None
    assert result.llm_call_count == 0


async def test_direct_provider_model_metadata_is_preserved() -> None:
    from src.core.assistant import run_assistant_request

    rag = AsyncMock(return_value={"documents": [], "cache_hit": False, "query_type": "GENERAL"})
    gen = AsyncMock(return_value={"response": "answer", "model": "direct/test-model"})

    with (
        patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
        patch("telegram_bot.agents.rag_pipeline.rag_pipeline", rag),
        patch("telegram_bot.services.generate_response.generate_response", gen),
    ):
        result = await run_assistant_request(
            "q",
            collection="core",
            request_id="direct-provider",
            dependencies=_deps(),
        )

    assert result.response_text == "answer"
    assert result.llm_model == "direct/test-model"
    assert result.llm_call_count == 1


async def test_litellm_compatible_provider_model_metadata_is_preserved() -> None:
    from src.core.assistant import run_assistant_request

    rag = AsyncMock(return_value={"documents": [], "cache_hit": False, "query_type": "GENERAL"})
    gen = AsyncMock(return_value={"response": "answer", "llm_provider_model": "openai/gpt-4o-mini"})

    with (
        patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
        patch("telegram_bot.agents.rag_pipeline.rag_pipeline", rag),
        patch("telegram_bot.services.generate_response.generate_response", gen),
    ):
        result = await run_assistant_request(
            "q",
            collection="core",
            request_id="litellm-provider",
            dependencies=_deps(),
        )

    assert result.response_text == "answer"
    assert result.llm_model == "openai/gpt-4o-mini"
    assert result.llm_call_count == 1


async def test_crm_intent_is_returned_as_proposal_without_write_before_hitl() -> None:
    from src.core.assistant import CrmAction, run_assistant_request

    rag = AsyncMock(return_value={"documents": [], "cache_hit": False, "query_type": "GENERAL"})
    gen = AsyncMock(
        return_value={
            "response": "I can prepare a lead.",
            "model": "fake",
            "proposed_crm_action": {
                "action_type": "create_lead",
                "payload": {"name": "Alice", "phone": "+10000000000"},
                "summary": "Create lead for Alice",
            },
        }
    )
    forbidden_write = AsyncMock()

    with (
        patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
        patch("telegram_bot.agents.rag_pipeline.rag_pipeline", rag),
        patch("telegram_bot.services.generate_response.generate_response", gen),
        patch("src.core.assistant._execute_crm_write", forbidden_write, create=True),
    ):
        result = await run_assistant_request(
            "Create a lead for Alice",
            collection="core",
            request_id="hitl-proposal",
            dependencies=_deps(),
        )

    assert isinstance(result.proposed_crm_action, CrmAction)
    assert result.proposed_crm_action.action_type == "create_lead"
    assert result.proposed_crm_action.payload == {"name": "Alice", "phone": "+10000000000"}
    assert result.proposed_crm_action.summary == "Create lead for Alice"
    forbidden_write.assert_not_awaited()
