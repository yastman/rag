"""Live core E2E golden path: fixture ingest -> Qdrant retrieval -> answer."""

from __future__ import annotations

import pytest

from src.core.assistant import UserContext, run_assistant_request
from tests.e2e_core.live_harness import (
    FailingLLMConfig,
    LiveE2EEnv,
    MockCrmClient,
    build_live_core_harness,
    cleanup_collection,
    index_fixture_documents,
    load_golden_case,
    make_qdrant_context,
    recreate_collection,
    require_live_services,
)


pytestmark = [pytest.mark.e2e, pytest.mark.requires_services]


async def _run_core_live_case(
    case_id: str,
    *,
    document_ids: list[str],
    session_suffix: str,
    expected_documents_count: int | None = None,
) -> None:
    env = LiveE2EEnv.from_env()
    await require_live_services(env)

    case = load_golden_case(case_id)
    context = make_qdrant_context(env)
    harness = None

    try:
        recreate_collection(env, context.collection_name)
        indexed_points = await index_fixture_documents(
            env,
            context.collection_name,
            document_ids=document_ids,
        )
        assert indexed_points >= 1

        harness = build_live_core_harness(env, context.collection_name)
        result = await run_assistant_request(
            case.query,
            collection=context.collection_name,
            user_context=UserContext(
                user_id="2336",
                session_id=f"{context.collection_name}:{session_suffix}",
                role="client",
            ),
            dependencies=harness.dependencies,
        )

        assert result.error_type is None, result.error_message
        assert result.route == "rag_search"
        if expected_documents_count is None:
            assert result.documents_count > 0
        else:
            assert result.documents_count == expected_documents_count
        assert set(case.must_retrieve).issubset(set(result.retrieved_doc_ids))

        for expected in case.must_contain:
            assert expected in result.response_text
        for forbidden in case.must_not_contain:
            assert forbidden not in result.response_text
    finally:
        if harness is not None:
            await harness.aclose()
        cleanup_collection(env, context)


@pytest.mark.asyncio
async def test_core_live_llm_dependency_failure_returns_user_safe_fallback() -> None:
    """LLM provider failure must return explicit user-safe fallback, not crash."""

    env = LiveE2EEnv.from_env()
    await require_live_services(env)

    case = load_golden_case("beach_studio_sea_under_120k")
    context = make_qdrant_context(env)
    harness = None

    try:
        recreate_collection(env, context.collection_name)
        indexed_points = await index_fixture_documents(
            env,
            context.collection_name,
            document_ids=["sunny_beach_studio", "mountain_view_villa"],
        )
        assert indexed_points >= 1

        harness = build_live_core_harness(
            env,
            context.collection_name,
            config=FailingLLMConfig(error_message="llm provider timeout"),
        )
        result = await run_assistant_request(
            case.query,
            collection=context.collection_name,
            user_context=UserContext(
                user_id="2336",
                session_id=f"{context.collection_name}:llm-failure",
                role="client",
            ),
            dependencies=harness.dependencies,
        )

        assert result.error_type is None, result.error_message
        assert result.route == "rag_search"
        assert result.llm_model == "fallback"
        assert result.llm_call_count == 1
        assert set(case.must_retrieve).issubset(set(result.retrieved_doc_ids))
        assert result.response_text
        assert "сервис временно недоступен" in result.response_text.lower()
    finally:
        if harness is not None:
            await harness.aclose()
        cleanup_collection(env, context)


@pytest.mark.asyncio
async def test_core_live_ingest_answer_golden_path() -> None:
    """First product golden case against live Qdrant/BGE services."""

    await _run_core_live_case(
        "beach_studio_sea_under_120k",
        document_ids=["sunny_beach_studio", "mountain_view_villa"],
        session_suffix="golden",
    )


@pytest.mark.asyncio
async def test_core_live_missing_corpus_returns_no_claim() -> None:
    """Missing-corpus query must not answer from unrelated retrieved docs."""

    await _run_core_live_case(
        "missing_in_corpus_no_claim",
        document_ids=["sunny_beach_studio", "mountain_view_villa", "city_center_sofia"],
        session_suffix="missing",
        expected_documents_count=0,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_id", "document_ids"),
    [
        (
            "price_constraint_cheapest_sunny_beach",
            ["sunny_beach_2bed", "sunny_beach_studio", "nessebar_penthouse"],
        ),
        (
            "sea_side_excludes_mountain",
            ["sunny_beach_studio", "mountain_view_villa"],
        ),
        (
            "garden_apartment_near_burgas",
            ["sotirovo_garden", "city_center_sofia", "mountain_view_villa"],
        ),
        (
            "service_cleaning_price_policy",
            ["services_cleaning", "sunny_beach_studio", "rules_hitl"],
        ),
    ],
)
async def test_core_live_remaining_golden_cases(case_id: str, document_ids: list[str]) -> None:
    """Remaining product golden cases against live Qdrant/BGE services."""

    await _run_core_live_case(
        case_id,
        document_ids=document_ids,
        session_suffix=case_id,
    )


@pytest.mark.asyncio
async def test_core_live_crm_hitl_requires_confirmation_before_mock_crm_write() -> None:
    """CRM/HITL golden case must propose confirmation policy without CRM writes."""

    crm = MockCrmClient()
    env = LiveE2EEnv.from_env()
    await require_live_services(env)

    case = load_golden_case("crm_hitl_confirmation_policy")
    context = make_qdrant_context(env)
    harness = None

    try:
        recreate_collection(env, context.collection_name)
        indexed_points = await index_fixture_documents(
            env,
            context.collection_name,
            document_ids=["rules_hitl", "sunny_beach_studio"],
        )
        assert indexed_points >= 1

        harness = build_live_core_harness(env, context.collection_name, crm=crm)
        result = await run_assistant_request(
            case.query,
            collection=context.collection_name,
            user_context=UserContext(
                user_id="2336",
                session_id=f"{context.collection_name}:crm-hitl",
                role="client",
            ),
            dependencies=harness.dependencies,
        )

        assert result.error_type is None, result.error_message
        assert result.route == "rag_search"
        assert set(case.must_retrieve).issubset(set(result.retrieved_doc_ids))
        assert result.proposed_crm_action is None
        assert crm.writes == []

        for expected in case.must_contain:
            assert expected in result.response_text
    finally:
        if harness is not None:
            await harness.aclose()
        cleanup_collection(env, context)
