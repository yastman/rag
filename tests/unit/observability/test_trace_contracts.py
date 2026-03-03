"""Trace contract tests — verify score writing and update_current_trace shapes.

Contracts tested:
  - score() must use create_score with trace_id and score_id idempotency key
  - write_langfuse_scores must write all 13 core RAG scores on every call
  - write_history_scores must write all 4 history scores (latency conditional)
  - write_crm_scores must write all 4 CRM scores unconditionally
  - _build_trace_metadata must include required keys for voice/text paths
"""

from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest


_TRACE_ID = "trace-contract-abc"

# Minimal state dict that exercises all 13 core RAG scores.
_MINIMAL_RESULT: dict = {
    "query_type": "SIMPLE",
    "cache_hit": False,
    "embeddings_cache_hit": False,
    "search_cache_hit": False,
    "search_results_count": 3,
    "rerank_applied": False,
    "grade_confidence": 0.7,
    "pipeline_wall_ms": 500.0,
    "latency_stages": {"generate": 0.3},
    "llm_ttft_ms": 100.0,
    "llm_response_duration_ms": 300.0,
    "llm_timeout": False,
    "llm_stream_recovery": False,
    "streaming_enabled": False,
    "messages": [],
}

# 13 core RAG scores from observability.md § "Langfuse Scores" table (hyde_used removed #754)
_CORE_RAG_SCORES = [
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
    "llm_ttft_ms",
    "llm_response_duration_ms",
]


# ---------------------------------------------------------------------------
# score() function signature contract
# ---------------------------------------------------------------------------


class TestScoreSignatureContract:
    """score() must wrap create_score with trace_id + score_id idempotency key."""

    def test_routes_through_create_score_not_score_current_trace(self):
        from telegram_bot.scoring import score

        lf = MagicMock()
        score(lf, _TRACE_ID, name="my_metric", value=1.0)

        lf.create_score.assert_called_once()
        lf.score_current_trace.assert_not_called()

    def test_passes_trace_id_name_value(self):
        from telegram_bot.scoring import score

        lf = MagicMock()
        score(lf, _TRACE_ID, name="latency_ms", value=42.5)

        call = lf.create_score.call_args
        assert call.kwargs["trace_id"] == _TRACE_ID
        assert call.kwargs["name"] == "latency_ms"
        assert call.kwargs["value"] == 42.5

    def test_sets_idempotency_score_id(self):
        from telegram_bot.scoring import score

        lf = MagicMock()
        score(lf, _TRACE_ID, name="cache_hit", value=1.0)

        call = lf.create_score.call_args
        assert call.kwargs["score_id"] == f"{_TRACE_ID}-cache_hit"

    def test_forwards_data_type_kwarg(self):
        from telegram_bot.scoring import score

        lf = MagicMock()
        score(lf, _TRACE_ID, name="flag", value=1, data_type="BOOLEAN")

        call = lf.create_score.call_args
        assert call.kwargs.get("data_type") == "BOOLEAN"

    def test_accepts_categorical_string_value(self):
        from telegram_bot.scoring import score

        lf = MagicMock()
        score(lf, _TRACE_ID, name="input_type", value="voice", data_type="CATEGORICAL")

        call = lf.create_score.call_args
        assert call.kwargs["value"] == "voice"
        assert call.kwargs["data_type"] == "CATEGORICAL"

    def test_empty_trace_id_still_calls_create_score(self):
        """score() does not guard on empty trace_id — callers are responsible."""
        from telegram_bot.scoring import score

        lf = MagicMock()
        score(lf, "", name="metric", value=1.0)

        lf.create_score.assert_called_once()
        assert lf.create_score.call_args.kwargs["trace_id"] == ""


# ---------------------------------------------------------------------------
# write_langfuse_scores: 14 core RAG scores contract
# ---------------------------------------------------------------------------


class TestWriteLangfuseScoresContract:
    """write_langfuse_scores must write all 13 core RAG scores."""

    def _written_scores(self, result: dict) -> dict[str, dict]:
        from telegram_bot.scoring import write_langfuse_scores

        lf = MagicMock()
        write_langfuse_scores(lf, result, trace_id=_TRACE_ID)
        return {c.kwargs["name"]: c.kwargs for c in lf.create_score.call_args_list}

    def test_all_13_core_scores_present(self):
        scores = self._written_scores(_MINIMAL_RESULT)
        missing = [s for s in _CORE_RAG_SCORES if s not in scores]
        assert not missing, f"Missing core RAG scores: {missing}"

    def test_all_scores_use_explicit_trace_id(self):
        from telegram_bot.scoring import write_langfuse_scores

        lf = MagicMock()
        write_langfuse_scores(lf, _MINIMAL_RESULT, trace_id=_TRACE_ID)

        for call in lf.create_score.call_args_list:
            assert call.kwargs["trace_id"] == _TRACE_ID

    def test_all_scores_have_score_id(self):
        from telegram_bot.scoring import write_langfuse_scores

        lf = MagicMock()
        write_langfuse_scores(lf, _MINIMAL_RESULT, trace_id=_TRACE_ID)

        for call in lf.create_score.call_args_list:
            name = call.kwargs["name"]
            expected_id = f"{_TRACE_ID}-{name}"
            assert call.kwargs["score_id"] == expected_id, f"Score '{name}' has wrong score_id"

    def test_skip_all_when_no_trace_and_no_context(self):
        from telegram_bot.scoring import write_langfuse_scores

        lf = MagicMock()
        lf.get_current_trace_id = MagicMock(return_value="")
        write_langfuse_scores(lf, _MINIMAL_RESULT, trace_id="")

        lf.create_score.assert_not_called()

    def test_fallback_to_context_trace_id_when_empty(self):
        """Falls back to lf.get_current_trace_id() when trace_id=''."""
        from telegram_bot.scoring import write_langfuse_scores

        lf = MagicMock()
        lf.get_current_trace_id = MagicMock(return_value="ctx-trace-xyz")
        write_langfuse_scores(lf, _MINIMAL_RESULT, trace_id="")

        lf.get_current_trace_id.assert_called()
        assert lf.create_score.call_count > 0

    def test_query_type_chitchat_maps_to_zero(self):
        scores = self._written_scores({**_MINIMAL_RESULT, "query_type": "CHITCHAT"})
        assert scores["query_type"]["value"] == 0.0

    def test_query_type_structured_maps_to_two(self):
        scores = self._written_scores({**_MINIMAL_RESULT, "query_type": "STRUCTURED"})
        assert scores["query_type"]["value"] == 2.0

    def test_semantic_cache_hit_when_true(self):
        scores = self._written_scores({**_MINIMAL_RESULT, "cache_hit": True})
        assert scores["semantic_cache_hit"]["value"] == 1.0

    def test_semantic_cache_hit_when_false(self):
        scores = self._written_scores({**_MINIMAL_RESULT, "cache_hit": False})
        assert scores["semantic_cache_hit"]["value"] == 0.0

    def test_llm_used_when_generate_stage_present(self):
        scores = self._written_scores(_MINIMAL_RESULT)  # has "generate" in latency_stages
        assert scores["llm_used"]["value"] == 1.0

    def test_llm_used_zero_when_no_generate_stage(self):
        result = {**_MINIMAL_RESULT, "latency_stages": {"cache_check": 0.01}}
        scores = self._written_scores(result)
        assert scores["llm_used"]["value"] == 0.0


# ---------------------------------------------------------------------------
# write_history_scores: 4 history scores contract
# ---------------------------------------------------------------------------

_HISTORY_SCORES_ALWAYS = [
    "history_search_count",
    "history_search_empty",
    "history_backend",
]


class TestWriteHistoryScoresContract:
    """write_history_scores must write all 4 history scores (latency conditional)."""

    def _written(self, **kwargs) -> dict[str, dict]:
        from telegram_bot.scoring import write_history_scores

        lf = MagicMock()
        write_history_scores(lf, _TRACE_ID, **kwargs)
        return {c.kwargs["name"]: c.kwargs for c in lf.create_score.call_args_list}

    def test_always_written_3_scores_present(self):
        scores = self._written(count=3, backend="qdrant")
        for name in _HISTORY_SCORES_ALWAYS:
            assert name in scores, f"Expected history score '{name}' not written"

    def test_latency_written_when_positive(self):
        scores = self._written(count=1, latency_ms=50.0)
        assert "history_search_latency_ms" in scores
        assert scores["history_search_latency_ms"]["value"] == 50.0

    def test_latency_not_written_when_zero(self):
        scores = self._written(count=0, latency_ms=0.0)
        assert "history_search_latency_ms" not in scores

    def test_empty_flag_one_for_zero_count(self):
        scores = self._written(count=0)
        assert scores["history_search_empty"]["value"] == 1.0

    def test_empty_flag_zero_for_nonzero_count(self):
        scores = self._written(count=5)
        assert scores["history_search_empty"]["value"] == 0.0

    def test_backend_is_categorical(self):
        scores = self._written(count=1, backend="qdrant")
        assert scores["history_backend"]["data_type"] == "CATEGORICAL"
        assert scores["history_backend"]["value"] == "qdrant"

    def test_empty_trace_id_writes_nothing(self):
        from telegram_bot.scoring import write_history_scores

        lf = MagicMock()
        write_history_scores(lf, "", count=5, latency_ms=100.0)
        lf.create_score.assert_not_called()


# ---------------------------------------------------------------------------
# write_crm_scores: 4 CRM scores contract
# NOTE: Behavioural tests (tool message parsing, success/error counting, score_id pattern,
#       empty trace_id skip) live in tests/unit/test_crm_scores.py.
#       This class tests SCHEMA contracts only: all 4 names present, value types.
# ---------------------------------------------------------------------------

_CRM_SCORES = ["crm_tool_used", "crm_tools_count", "crm_tools_success", "crm_tools_error"]


class TestWriteCrmScoresContract:
    """Schema contract: write_crm_scores must write all 4 CRM scores with correct types."""

    def _written(self, messages, *, trace_id: str = _TRACE_ID) -> dict[str, dict]:
        from telegram_bot.scoring import write_crm_scores

        lf = MagicMock()
        write_crm_scores(lf, messages, trace_id=trace_id)
        return {c.kwargs["name"]: c.kwargs for c in lf.create_score.call_args_list}

    def test_all_4_scores_present(self):
        """All 4 CRM score names must always be written (contract: complete schema)."""
        scores = self._written([])
        missing = [s for s in _CRM_SCORES if s not in scores]
        assert not missing, f"Missing CRM scores: {missing}"

    def test_crm_tool_used_is_boolean(self):
        scores = self._written([])
        assert scores["crm_tool_used"]["data_type"] == "BOOLEAN"

    def test_counts_are_numeric_float(self):
        """All three count scores must be float (allows arithmetic in dashboards)."""
        scores = self._written([])
        for name in ["crm_tools_count", "crm_tools_success", "crm_tools_error"]:
            assert isinstance(scores[name]["value"], float), f"{name} value should be float"


# ---------------------------------------------------------------------------
# _build_trace_metadata: shape contract (requires aiogram for bot.py import)
# ---------------------------------------------------------------------------


class TestBuildTraceMetadataContract:
    """_build_trace_metadata must include required keys for voice/text paths."""

    _REQUIRED_KEYS = {
        "input_type",
        "query_type",
        "cache_hit",
        "search_results_count",
        "rerank_applied",
        "embedding_error",
        "memory_messages_count",
    }

    @pytest.fixture(autouse=True)
    def _require_aiogram(self):
        pytest.importorskip("aiogram", reason="bot.py requires aiogram")

    def test_all_required_keys_present(self):
        from telegram_bot.bot import _build_trace_metadata

        result = {
            "input_type": "text",
            "query_type": "SIMPLE",
            "cache_hit": False,
            "search_results_count": 3,
            "rerank_applied": False,
            "messages": [],
        }
        metadata = _build_trace_metadata(result)
        missing = self._REQUIRED_KEYS - set(metadata.keys())
        assert not missing, f"Missing metadata keys: {missing}"

    def test_voice_specific_keys_propagate(self):
        from telegram_bot.bot import _build_trace_metadata

        result = {
            "input_type": "voice",
            "stt_duration_ms": 200.0,
            "messages": [],
        }
        metadata = _build_trace_metadata(result)
        assert metadata["input_type"] == "voice"
        assert metadata["stt_duration_ms"] == 200.0

    def test_defaults_for_minimal_result(self):
        from telegram_bot.bot import _build_trace_metadata

        metadata = _build_trace_metadata({})
        assert metadata["input_type"] == "text"
        assert metadata["cache_hit"] is False
        assert metadata["embedding_error"] is False
        assert metadata["memory_messages_count"] == 0

    def test_memory_messages_count_from_messages_list(self):
        from telegram_bot.bot import _build_trace_metadata

        result = {"messages": [{"role": "user"}, {"role": "assistant"}, {"role": "user"}]}
        metadata = _build_trace_metadata(result)
        assert metadata["memory_messages_count"] == 3

    def test_heavy_payload_keys_are_not_in_trace_metadata(self):
        """Heavy internals should never leak into trace metadata payload."""
        from telegram_bot.bot import _build_trace_metadata

        result = {
            "documents": [{"id": "d1"}],
            "query_embedding": [0.1] * 16,
            "voice_audio": b"raw-bytes",
            "messages": [],
        }
        metadata = _build_trace_metadata(result)
        assert "documents" not in metadata
        assert "query_embedding" not in metadata
        assert "voice_audio" not in metadata


class TestVoiceLifecycleTraceContract:
    """Voice lifecycle traces should preserve call/session/status contract (#609)."""

    def test_voice_session_id_has_voice_prefix(self):
        from src.voice.observability import voice_session_id

        assert voice_session_id("call-123") == "voice-call-123"
        assert voice_session_id("") == "voice-unknown"

    def test_build_voice_trace_metadata_includes_finalize_duration(self):
        from src.voice.observability import build_voice_trace_metadata

        payload = build_voice_trace_metadata(
            call_id="call-123",
            status="finalized",
            duration_sec=31,
        )
        assert payload["call_id"] == "call-123"
        assert payload["status"] == "finalized"
        assert payload["duration_sec"] == 31

    def test_update_voice_trace_writes_answered_status(self):
        from src.voice.observability import update_voice_trace

        lf = MagicMock()
        lf.update_current_trace = MagicMock()
        with (
            pytest.MonkeyPatch().context() as mp,
        ):
            mp.setattr("src.voice.observability.get_client", lambda: lf)
            mp.setattr("src.voice.observability.propagate_attributes", lambda **_: nullcontext())
            update_voice_trace(call_id="call-123", status="answered")

        lf.update_current_trace.assert_called_once()
        kwargs = lf.update_current_trace.call_args.kwargs
        assert kwargs["session_id"] == "voice-call-123"
        assert kwargs["metadata"]["status"] == "answered"
        assert kwargs["metadata"]["call_id"] == "call-123"


class TestSessionIdFormatContract:
    """Session id should keep `{type}-{hash}-{YYYYMMDD}` contract."""

    @pytest.fixture(autouse=True)
    def _require_aiogram(self):
        pytest.importorskip("aiogram", reason="bot.py requires aiogram")

    def test_make_session_id_matches_expected_format(self):
        import re

        from telegram_bot.bot import make_session_id

        sid = make_session_id("history", 12345)
        assert re.match(r"^history-[a-f0-9]{8}-\d{8}$", sid)
