from telegram_bot.services.cache_policy import build_cacheability_decision


def _cacheable_result() -> dict:
    return {
        "response": "Подтвержденный ответ.",
        "fallback_used": False,
        "safe_fallback_used": False,
        "llm_provider_model": "gpt-4.1",
        "llm_timeout": False,
        "grounded": True,
        "legal_answer_safe": True,
        "semantic_cache_safe_reuse": True,
    }


def test_build_cacheability_decision_marks_provider_fallback_non_cacheable() -> None:
    decision = build_cacheability_decision(
        result={
            "response": "⚠️ Сервис временно недоступен",
            "fallback_used": True,
            "safe_fallback_used": False,
            "llm_provider_model": "fallback",
            "llm_timeout": True,
            "grounded": False,
            "legal_answer_safe": False,
            "semantic_cache_safe_reuse": False,
        },
        query_type="FAQ",
        grounding_mode="strict",
        documents=[{"text": "doc"}],
        cache_hit=False,
        contextual=False,
        grade_confidence=0.9,
        confidence_threshold=0.005,
        schema_version="v7",
    )

    assert decision.response_state == "fallback"
    assert decision.degraded_reason == "provider_fallback"
    assert decision.cache_eligible is False
    assert decision.metadata["cache_eligible"] is False
    assert decision.metadata["response_state"] == "fallback"


def test_build_cacheability_decision_marks_ok_response_cacheable() -> None:
    decision = build_cacheability_decision(
        result=_cacheable_result(),
        query_type="FAQ",
        grounding_mode="strict",
        documents=[{"text": "doc"}],
        cache_hit=False,
        contextual=False,
        grade_confidence=0.9,
        confidence_threshold=0.005,
        schema_version="v7",
    )

    assert decision.response_state == "ok"
    assert decision.cache_eligible is True
    assert decision.metadata["schema_version"] == "v7"


def test_build_cacheability_decision_allows_rrf_threshold_boundary() -> None:
    decision = build_cacheability_decision(
        result=_cacheable_result(),
        query_type="GENERAL",
        grounding_mode="strict",
        documents=[{"text": "doc"}],
        cache_hit=False,
        contextual=False,
        grade_confidence=0.005,
        confidence_threshold=0.005,
        schema_version="v8",
    )

    assert decision.cache_eligible is True
    assert decision.store_reason == "store_allowed"


def test_build_cacheability_decision_blocks_below_rrf_threshold() -> None:
    decision = build_cacheability_decision(
        result=_cacheable_result(),
        query_type="GENERAL",
        grounding_mode="strict",
        documents=[{"text": "doc"}],
        cache_hit=False,
        contextual=False,
        grade_confidence=0.0049,
        confidence_threshold=0.005,
        schema_version="v8",
    )

    assert decision.cache_eligible is False


def test_build_cacheability_decision_blocks_existing_cache_hit() -> None:
    decision = build_cacheability_decision(
        result=_cacheable_result(),
        query_type="FAQ",
        grounding_mode="strict",
        documents=[{"text": "doc"}],
        cache_hit=True,
        contextual=False,
        grade_confidence=0.9,
        confidence_threshold=0.005,
        schema_version="v8",
    )

    assert decision.cache_eligible is False


def test_build_cacheability_decision_blocks_contextual_query() -> None:
    decision = build_cacheability_decision(
        result=_cacheable_result(),
        query_type="FAQ",
        grounding_mode="strict",
        documents=[{"text": "doc"}],
        cache_hit=False,
        contextual=True,
        grade_confidence=0.9,
        confidence_threshold=0.005,
        schema_version="v8",
    )

    assert decision.cache_eligible is False


def test_build_cacheability_decision_blocks_empty_documents() -> None:
    decision = build_cacheability_decision(
        result=_cacheable_result(),
        query_type="FAQ",
        grounding_mode="strict",
        documents=[],
        cache_hit=False,
        contextual=False,
        grade_confidence=0.9,
        confidence_threshold=0.005,
        schema_version="v8",
    )

    assert decision.cache_eligible is False
