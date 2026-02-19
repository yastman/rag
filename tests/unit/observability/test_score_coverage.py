"""Score coverage contract — parametrized verification of each score name and type.

Verifies scoring.py covers all documented scores:
  - 14 core RAG scores (write_langfuse_scores)
  - Always-written supplementary scores (BOOLEAN/CATEGORICAL)
  - 4 history scores (write_history_scores)
  - 4 CRM tool scores (write_crm_scores)
  - Supervisor score names present as string literals in bot.py
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


_TRACE_ID = "trace-coverage-001"

_FULL_RESULT: dict = {
    "query_type": "STRUCTURED",
    "cache_hit": False,
    "embeddings_cache_hit": False,
    "search_cache_hit": False,
    "search_results_count": 5,
    "rerank_applied": True,
    "grade_confidence": 0.85,
    "pipeline_wall_ms": 862.0,
    "latency_stages": {
        "cache_check": 0.050,
        "retrieve": 0.200,
        "generate": 0.500,
    },
    "llm_ttft_ms": 150.0,
    "llm_response_duration_ms": 450.0,
    "llm_decode_ms": 300.0,
    "llm_tps": 42.5,
    "llm_queue_ms": None,
    "llm_timeout": False,
    "llm_stream_recovery": False,
    "streaming_enabled": True,
    "answer_words": 12,
    "answer_chars": 65,
    "answer_to_question_ratio": 2.4,
    "response_policy_mode": "enforced",
    "response_style": "balanced",
    "sources_count": 3,
    "messages": [{"role": "user"}, {"role": "assistant"}],
    "input_type": "text",
}


@pytest.fixture()
def all_rag_scores() -> dict[str, dict]:
    from telegram_bot.scoring import write_langfuse_scores

    lf = MagicMock()
    write_langfuse_scores(lf, _FULL_RESULT, trace_id=_TRACE_ID)
    return {c.kwargs["name"]: c.kwargs for c in lf.create_score.call_args_list}


# ---------------------------------------------------------------------------
# Core RAG scores (14) — documented table in observability.md
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score_name",
    [
        "query_type",
        "latency_total_ms",
        "semantic_cache_hit",
        "embeddings_cache_hit",
        "search_cache_hit",
        "rerank_applied",
        "rerank_cache_hit",
        "results_count",
        "no_results",
        "llm_used",
        "confidence_score",
        "hyde_used",
        "llm_ttft_ms",
        "llm_response_duration_ms",
    ],
)
def test_core_rag_score_is_written(score_name: str, all_rag_scores: dict) -> None:
    assert score_name in all_rag_scores, f"Core RAG score '{score_name}' not written"


# ---------------------------------------------------------------------------
# Core RAG scores — numeric value type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score_name",
    [
        "latency_total_ms",
        "semantic_cache_hit",
        "embeddings_cache_hit",
        "search_cache_hit",
        "rerank_applied",
        "rerank_cache_hit",
        "results_count",
        "no_results",
        "llm_used",
        "confidence_score",
        "hyde_used",
        "llm_ttft_ms",
        "llm_response_duration_ms",
    ],
)
def test_core_rag_score_value_is_numeric(score_name: str, all_rag_scores: dict) -> None:
    val = all_rag_scores[score_name]["value"]
    assert isinstance(val, (int, float)), (
        f"Score '{score_name}' value must be numeric, got {type(val)}"
    )


# ---------------------------------------------------------------------------
# BOOLEAN scores — must carry data_type="BOOLEAN"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score_name",
    [
        "streaming_enabled",
        "llm_timeout",
        "llm_stream_recovery",
        "bge_embed_error",
        "security_alert",
        "guard_ml_available",
        "summarization_triggered",
    ],
)
def test_boolean_score_has_boolean_data_type(score_name: str, all_rag_scores: dict) -> None:
    assert score_name in all_rag_scores, f"BOOLEAN score '{score_name}' not written"
    assert all_rag_scores[score_name].get("data_type") == "BOOLEAN", (
        f"Score '{score_name}' should have data_type='BOOLEAN'"
    )


# ---------------------------------------------------------------------------
# CATEGORICAL scores
# ---------------------------------------------------------------------------


def test_input_type_is_categorical(all_rag_scores: dict) -> None:
    assert "input_type" in all_rag_scores
    assert all_rag_scores["input_type"]["data_type"] == "CATEGORICAL"


def test_input_type_text_value_for_text_result(all_rag_scores: dict) -> None:
    assert all_rag_scores["input_type"]["value"] == "text"


def test_input_type_voice_for_voice_result() -> None:
    from telegram_bot.scoring import write_langfuse_scores

    lf = MagicMock()
    write_langfuse_scores(lf, {**_FULL_RESULT, "input_type": "voice"}, trace_id=_TRACE_ID)
    scores = {c.kwargs["name"]: c.kwargs for c in lf.create_score.call_args_list}
    assert scores["input_type"]["value"] == "voice"


# ---------------------------------------------------------------------------
# memory_messages_count — always written
# ---------------------------------------------------------------------------


def test_memory_messages_count_always_written(all_rag_scores: dict) -> None:
    assert "memory_messages_count" in all_rag_scores


def test_memory_messages_count_value_matches_messages(all_rag_scores: dict) -> None:
    # _FULL_RESULT has 2 messages
    assert all_rag_scores["memory_messages_count"]["value"] == 2.0


# ---------------------------------------------------------------------------
# Streaming path scores — llm_decode_ms, llm_tps when available
# ---------------------------------------------------------------------------


def test_llm_decode_ms_written_when_available(all_rag_scores: dict) -> None:
    # _FULL_RESULT has llm_decode_ms=300.0
    assert "llm_decode_ms" in all_rag_scores
    assert all_rag_scores["llm_decode_ms"]["value"] == 300.0


def test_llm_tps_written_when_available(all_rag_scores: dict) -> None:
    assert "llm_tps" in all_rag_scores
    assert all_rag_scores["llm_tps"]["value"] == 42.5


def test_llm_decode_unavailable_written_when_none() -> None:
    from telegram_bot.scoring import write_langfuse_scores

    lf = MagicMock()
    result = {**_FULL_RESULT, "llm_decode_ms": None, "llm_tps": None}
    del result["llm_decode_ms"]
    del result["llm_tps"]
    write_langfuse_scores(lf, result, trace_id=_TRACE_ID)
    scores = {c.kwargs["name"]: c.kwargs for c in lf.create_score.call_args_list}
    assert "llm_decode_unavailable" in scores
    assert scores["llm_decode_unavailable"]["data_type"] == "BOOLEAN"
    assert "llm_tps_unavailable" in scores


# ---------------------------------------------------------------------------
# History scores (4) — write_history_scores
# ---------------------------------------------------------------------------


@pytest.fixture()
def history_scores() -> dict[str, dict]:
    from telegram_bot.scoring import write_history_scores

    lf = MagicMock()
    write_history_scores(lf, _TRACE_ID, count=5, latency_ms=75.0, backend="qdrant")
    return {c.kwargs["name"]: c.kwargs for c in lf.create_score.call_args_list}


@pytest.mark.parametrize(
    "score_name",
    [
        "history_search_count",
        "history_search_latency_ms",
        "history_search_empty",
        "history_backend",
    ],
)
def test_history_score_is_written(score_name: str, history_scores: dict) -> None:
    assert score_name in history_scores, f"History score '{score_name}' not written"


def test_history_search_count_is_numeric(history_scores: dict) -> None:
    val = history_scores["history_search_count"]["value"]
    assert isinstance(val, (int, float))


def test_history_backend_is_categorical(history_scores: dict) -> None:
    assert history_scores["history_backend"]["data_type"] == "CATEGORICAL"


def test_history_search_latency_is_numeric(history_scores: dict) -> None:
    val = history_scores["history_search_latency_ms"]["value"]
    assert isinstance(val, float)


# ---------------------------------------------------------------------------
# CRM scores (4) — write_crm_scores
# ---------------------------------------------------------------------------


@pytest.fixture()
def crm_scores() -> dict[str, dict]:
    from telegram_bot.scoring import write_crm_scores

    lf = MagicMock()
    write_crm_scores(lf, [], trace_id=_TRACE_ID)
    return {c.kwargs["name"]: c.kwargs for c in lf.create_score.call_args_list}


@pytest.mark.parametrize(
    "score_name",
    [
        "crm_tool_used",
        "crm_tools_count",
        "crm_tools_success",
        "crm_tools_error",
    ],
)
def test_crm_score_is_written(score_name: str, crm_scores: dict) -> None:
    """Each CRM score name must be written (parametrized for individual failure messages)."""
    assert score_name in crm_scores, f"CRM score '{score_name}' not written"
    # Type/schema contracts are in test_trace_contracts.py::TestWriteCrmScoresContract


# ---------------------------------------------------------------------------
# Supervisor scores — verify names appear as string literals in bot.py
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score_name",
    [
        "supervisor_model",
        "user_role",
        "history_save_success",
        "tool_calls_total",
    ],
)
def test_supervisor_score_name_in_bot_source(score_name: str) -> None:
    """Supervisor score names must appear as string literals in bot.py."""
    from pathlib import Path

    bot_py = Path(__file__).resolve().parents[3] / "telegram_bot" / "bot.py"
    bot_source = bot_py.read_text(encoding="utf-8")
    assert f'"{score_name}"' in bot_source or f"'{score_name}'" in bot_source, (
        f"Supervisor score '{score_name}' not found as string literal in bot.py"
    )


# ---------------------------------------------------------------------------
# Response-length control scores — conditional on enforced policy
# ---------------------------------------------------------------------------


def test_response_style_applied_written_for_enforced_policy(all_rag_scores: dict) -> None:
    # _FULL_RESULT has response_policy_mode="enforced", response_style="balanced"
    assert "response_style_applied" in all_rag_scores


def test_response_style_applied_not_written_for_shadow_policy() -> None:
    from telegram_bot.scoring import write_langfuse_scores

    lf = MagicMock()
    result = {**_FULL_RESULT, "response_policy_mode": "shadow", "response_style": "short"}
    write_langfuse_scores(lf, result, trace_id=_TRACE_ID)
    scores = {c.kwargs["name"] for c in lf.create_score.call_args_list}
    assert "response_style_applied" not in scores


# ---------------------------------------------------------------------------
# Source attribution scores — conditional on sources_count > 0
# ---------------------------------------------------------------------------


def test_sources_shown_boolean_written_when_sources_present(all_rag_scores: dict) -> None:
    # _FULL_RESULT has sources_count=3
    assert "sources_shown" in all_rag_scores
    assert all_rag_scores["sources_shown"]["data_type"] == "BOOLEAN"
    assert all_rag_scores["sources_shown"]["value"] == 1


def test_sources_count_written_when_sources_present(all_rag_scores: dict) -> None:
    assert "sources_count" in all_rag_scores
    assert all_rag_scores["sources_count"]["value"] == 3.0
