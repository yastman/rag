"""Live core E2E golden path: fixture ingest -> Qdrant retrieval -> answer."""

from __future__ import annotations

import pytest

from src.core.assistant import UserContext, run_assistant_request
from tests.e2e_core.live_harness import (
    LiveE2EEnv,
    build_live_core_harness,
    cleanup_collection,
    index_fixture_documents,
    load_golden_case,
    make_qdrant_context,
    recreate_collection,
    require_live_services,
)


pytestmark = [pytest.mark.e2e, pytest.mark.requires_services]


@pytest.mark.asyncio
async def test_core_live_ingest_answer_golden_path() -> None:
    """First product golden case against live Qdrant/BGE services."""

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

        harness = build_live_core_harness(env, context.collection_name)
        result = await run_assistant_request(
            case.query,
            collection=context.collection_name,
            user_context=UserContext(
                user_id="2336",
                session_id=f"{context.collection_name}:golden",
                role="client",
            ),
            dependencies=harness.dependencies,
        )

        assert result.error_type is None, result.error_message
        assert result.route == "rag_search"
        assert result.documents_count > 0
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
async def test_core_live_missing_corpus_returns_no_claim() -> None:
    """Missing-corpus query must not answer from unrelated retrieved docs."""

    env = LiveE2EEnv.from_env()
    await require_live_services(env)

    case = load_golden_case("missing_in_corpus_no_claim")
    context = make_qdrant_context(env)
    harness = None

    try:
        recreate_collection(env, context.collection_name)
        indexed_points = await index_fixture_documents(
            env,
            context.collection_name,
            document_ids=["sunny_beach_studio", "mountain_view_villa", "city_center_sofia"],
        )
        assert indexed_points >= 1

        harness = build_live_core_harness(env, context.collection_name)
        result = await run_assistant_request(
            case.query,
            collection=context.collection_name,
            user_context=UserContext(
                user_id="2336",
                session_id=f"{context.collection_name}:missing",
                role="client",
            ),
            dependencies=harness.dependencies,
        )

        assert result.error_type is None, result.error_message
        assert result.route == "rag_search"
        assert result.documents_count == 0
        assert result.retrieved_doc_ids == case.must_retrieve

        for expected in case.must_contain:
            assert expected in result.response_text
        for forbidden in case.must_not_contain:
            assert forbidden not in result.response_text
    finally:
        if harness is not None:
            await harness.aclose()
        cleanup_collection(env, context)
