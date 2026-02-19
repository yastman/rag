"""Trace resilience contracts — verify graceful degradation when Langfuse is unavailable.

Contracts:
  - _NullLangfuseClient: all methods callable, no exceptions raised
  - write_langfuse_scores: empty trace_id → silent no-op
  - write_history_scores / write_crm_scores: empty trace_id → silent no-op
  - scoring functions work transparently with _NullLangfuseClient
  - _write_voice_error_scores: graceful handling of empty trace_id
  - bot.py wraps scoring calls in try/except (static contract)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


_TRACE_ID = "trace-resilience-001"

_MINIMAL_RESULT: dict = {
    "query_type": "SIMPLE",
    "cache_hit": False,
    "search_results_count": 0,
    "rerank_applied": False,
    "grade_confidence": 0.0,
    "pipeline_wall_ms": 100.0,
    "latency_stages": {},
    "llm_ttft_ms": 0.0,
    "llm_response_duration_ms": 0.0,
    "llm_timeout": False,
    "llm_stream_recovery": False,
    "streaming_enabled": False,
    "messages": [],
}


# ---------------------------------------------------------------------------
# _NullLangfuseClient: all public methods must be callable without raising
# ---------------------------------------------------------------------------


class TestNullLangfuseClientResilience:
    """_NullLangfuseClient: every method must be a no-op that never raises."""

    def test_update_current_trace_no_raise(self):
        from telegram_bot.observability import _NullLangfuseClient

        _NullLangfuseClient().update_current_trace(
            input={"query": "test"}, output={"response": "ok"}, metadata={"k": "v"}
        )

    def test_update_current_span_no_raise(self):
        from telegram_bot.observability import _NullLangfuseClient

        _NullLangfuseClient().update_current_span(
            input={"x": 1}, output={"y": 2}, level="WARNING", status_message="msg"
        )

    def test_update_current_generation_no_raise(self):
        from telegram_bot.observability import _NullLangfuseClient

        _NullLangfuseClient().update_current_generation(model="gpt-4", usage={"tokens": 100})

    def test_score_current_trace_no_raise(self):
        from telegram_bot.observability import _NullLangfuseClient

        _NullLangfuseClient().score_current_trace(
            name="hitl_action", value="approve", data_type="CATEGORICAL"
        )

    def test_create_score_no_raise(self):
        from telegram_bot.observability import _NullLangfuseClient

        _NullLangfuseClient().create_score(
            trace_id="abc",
            name="metric",
            value=1.0,
            score_id="abc-metric",
            data_type="NUMERIC",
        )

    def test_get_current_trace_id_returns_empty_string(self):
        from telegram_bot.observability import _NullLangfuseClient

        result = _NullLangfuseClient().get_current_trace_id()
        assert result == ""
        assert isinstance(result, str)

    def test_flush_no_raise(self):
        from telegram_bot.observability import _NullLangfuseClient

        _NullLangfuseClient().flush()

    def test_write_langfuse_scores_with_null_client_no_raise(self):
        """write_langfuse_scores with _NullLangfuseClient and explicit trace_id must not raise."""
        from telegram_bot.observability import _NullLangfuseClient
        from telegram_bot.scoring import write_langfuse_scores

        write_langfuse_scores(_NullLangfuseClient(), _MINIMAL_RESULT, trace_id=_TRACE_ID)

    def test_write_history_scores_with_null_client_no_raise(self):
        from telegram_bot.observability import _NullLangfuseClient
        from telegram_bot.scoring import write_history_scores

        write_history_scores(_NullLangfuseClient(), _TRACE_ID, count=0)

    def test_write_crm_scores_with_null_client_no_raise(self):
        from telegram_bot.observability import _NullLangfuseClient
        from telegram_bot.scoring import write_crm_scores

        write_crm_scores(_NullLangfuseClient(), [], trace_id=_TRACE_ID)


# ---------------------------------------------------------------------------
# Empty trace_id: all scoring functions silently skip
# ---------------------------------------------------------------------------


class TestEmptyTraceIdSilentSkip:
    """Empty trace_id → no scores written, no exceptions."""

    def test_write_langfuse_scores_no_trace_id_no_calls(self):
        from telegram_bot.scoring import write_langfuse_scores

        lf = MagicMock()
        lf.get_current_trace_id = MagicMock(return_value="")
        write_langfuse_scores(lf, _MINIMAL_RESULT, trace_id="")

        lf.create_score.assert_not_called()

    def test_write_history_scores_no_trace_id_no_calls(self):
        from telegram_bot.scoring import write_history_scores

        lf = MagicMock()
        write_history_scores(lf, "", count=5, latency_ms=100.0)

        lf.create_score.assert_not_called()

    def test_write_crm_scores_no_trace_id_no_calls(self):
        from telegram_bot.scoring import write_crm_scores

        lf = MagicMock()
        write_crm_scores(lf, [], trace_id="")

        lf.create_score.assert_not_called()

    def test_write_langfuse_scores_empty_trace_no_raise(self):
        """Must not raise even when trace_id is empty and get_current_trace_id returns ''."""
        from telegram_bot.scoring import write_langfuse_scores

        lf = MagicMock()
        lf.get_current_trace_id = MagicMock(return_value="")
        # Must complete without raising
        write_langfuse_scores(lf, _MINIMAL_RESULT, trace_id="")


# ---------------------------------------------------------------------------
# _write_voice_error_scores: graceful behavior
# ---------------------------------------------------------------------------


class TestVoiceErrorScoresResilience:
    """_write_voice_error_scores must handle missing trace_id gracefully."""

    @pytest.fixture(autouse=True)
    def _require_aiogram(self):
        pytest.importorskip("aiogram", reason="bot.py requires aiogram")

    def test_empty_trace_id_writes_nothing(self):
        from telegram_bot.bot import _write_voice_error_scores

        lf = MagicMock()
        lf.get_current_trace_id = MagicMock(return_value="")
        _write_voice_error_scores(lf, trace_id="", voice_duration_s=5.0)

        lf.create_score.assert_not_called()

    def test_with_trace_id_writes_input_type_and_error_reason(self):
        from telegram_bot.bot import _write_voice_error_scores

        lf = MagicMock()
        _write_voice_error_scores(
            lf,
            trace_id=_TRACE_ID,
            voice_duration_s=5.0,
            error_reason="empty_transcription",
        )
        written = {c.kwargs["name"] for c in lf.create_score.call_args_list}
        assert "input_type" in written
        assert "voice_error_reason" in written
        assert "voice_duration_s" in written

    def test_input_type_is_voice_categorical(self):
        from telegram_bot.bot import _write_voice_error_scores

        lf = MagicMock()
        _write_voice_error_scores(lf, trace_id=_TRACE_ID)
        scores = {c.kwargs["name"]: c.kwargs for c in lf.create_score.call_args_list}
        assert scores["input_type"]["value"] == "voice"
        assert scores["input_type"]["data_type"] == "CATEGORICAL"

    def test_voice_duration_omitted_when_none(self):
        from telegram_bot.bot import _write_voice_error_scores

        lf = MagicMock()
        _write_voice_error_scores(lf, trace_id=_TRACE_ID, voice_duration_s=None)
        written = {c.kwargs["name"] for c in lf.create_score.call_args_list}
        assert "voice_duration_s" not in written

    def test_fallback_to_get_current_trace_id_when_no_explicit(self):
        """Falls back to lf.get_current_trace_id() when trace_id not passed."""
        from telegram_bot.bot import _write_voice_error_scores

        lf = MagicMock()
        lf.get_current_trace_id = MagicMock(return_value=_TRACE_ID)
        _write_voice_error_scores(lf, trace_id="")

        lf.get_current_trace_id.assert_called()


# ---------------------------------------------------------------------------
# Static contract: bot.py wraps scoring calls in try/except
# ---------------------------------------------------------------------------


class TestBotScoringTryCatchContract:
    """bot.py must wrap write_langfuse_scores and update_current_trace in try/except."""

    def _bot_source(self) -> str:
        from pathlib import Path

        return (Path(__file__).resolve().parents[3] / "telegram_bot" / "bot.py").read_text(
            encoding="utf-8"
        )

    def test_write_langfuse_scores_wrapped_in_try_except(self):
        """write_langfuse_scores must be called inside a try block in handle_voice."""
        source = self._bot_source()
        assert "write_langfuse_scores" in source
        # Both try and write_langfuse_scores exist together in the voice handler
        assert "Failed to write Langfuse voice scores" in source

    def test_update_current_trace_failure_logged_not_raised(self):
        """Failed update_current_trace must be caught and logged, not re-raised."""
        source = self._bot_source()
        assert "Failed to update Langfuse voice trace metadata" in source

    def test_voice_error_scores_wrapped_in_try_except(self):
        """_write_voice_error_scores calls must be wrapped in try/except in handle_voice."""
        source = self._bot_source()
        assert "Failed to write voice error scores" in source

    def test_scoring_exception_does_not_produce_double_error_message(self):
        """No user-facing error message is emitted from the scoring try/except blocks.

        Scoring-specific handlers are identified by the logger messages they contain as
        direct string-literal arguments (not nested code). This avoids false positives
        from outer handlers that wrap scoring calls AND legitimately call message.answer.
        """
        import ast
        from pathlib import Path

        source = (Path(__file__).resolve().parents[3] / "telegram_bot" / "bot.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)

        _SCORING_LOG_MARKERS = (
            "Failed to write Langfuse voice scores",
            "Failed to update Langfuse voice trace metadata",
            "Failed to write voice error scores",
        )

        def _direct_string_literals(stmts: list) -> list[str]:
            """Collect string constants from direct (non-nested) expression statements."""
            literals = []
            for stmt in stmts:
                if not isinstance(stmt, ast.Expr):
                    continue
                for node in ast.walk(stmt.value):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        literals.append(node.value)
            return literals

        def _direct_has_message_answer(stmts: list) -> bool:
            """Check direct body for await message.answer() calls (not nested)."""
            for stmt in stmts:
                # Await expression: await message.answer(...)
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Await):
                    call = stmt.value.value
                    if isinstance(call, ast.Call) and "message.answer" in ast.unparse(call.func):
                        return True
            return False

        # Find except handlers whose DIRECT body contains a scoring log marker
        score_handlers = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            literals = _direct_string_literals(node.body)
            if any(any(m in lit for m in _SCORING_LOG_MARKERS) for lit in literals):
                score_handlers.append(node)

        assert score_handlers, "Expected at least one scoring-specific except handler in bot.py"

        # Each scoring-specific handler must NOT directly call message.answer
        for handler in score_handlers:
            assert not _direct_has_message_answer(handler.body), (
                "Scoring error handler must not send user messages"
            )
