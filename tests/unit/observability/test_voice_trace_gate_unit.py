"""Unit tests for voice trace validation gate logic.

Tests the core validation functions without requiring a live Langfuse instance.
Validates both success and failure cases for trace presence, attribution,
and evidence summary generation.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.observability.gate_logic import (
    FakeObservation,
    FakeTrace,
    build_evidence_summary,
    validate_voice_trace_attribution,
    validate_voice_trace_presence,
)


# ---------------------------------------------------------------------------
# validate_voice_trace_presence
# ---------------------------------------------------------------------------


class TestValidateVoiceTracePresence:
    """Tests for trace presence check."""

    def test_returns_true_when_traces_exist(self) -> None:
        traces = [MagicMock()]
        assert validate_voice_trace_presence(traces) is True

    def test_returns_false_when_empty(self) -> None:
        assert validate_voice_trace_presence([]) is False

    def test_returns_true_for_multiple_traces(self) -> None:
        traces = [MagicMock(), MagicMock(), MagicMock()]
        assert validate_voice_trace_presence(traces) is True


# ---------------------------------------------------------------------------
# validate_voice_trace_attribution
# ---------------------------------------------------------------------------


class TestValidateVoiceTraceAttribution:
    """Tests for service attribution validation."""

    def test_all_correct(self) -> None:
        trace = FakeTrace(
            id="t1",
            name="voice-session",
            user_id="voice-agent",
            session_id="voice-call-123",
            tags=["voice", "call-lifecycle"],
        )
        result = validate_voice_trace_attribution(trace)
        assert result == {
            "user_id_correct": True,
            "session_id_pattern": True,
            "has_voice_tag": True,
            "has_lifecycle_tag": True,
        }

    def test_wrong_user_id(self) -> None:
        trace = FakeTrace(
            id="t1",
            name="voice-session",
            user_id="telegram-bot",
            session_id="voice-abc",
            tags=["voice", "call-lifecycle"],
        )
        result = validate_voice_trace_attribution(trace)
        assert result["user_id_correct"] is False
        assert result["session_id_pattern"] is True

    def test_missing_user_id(self) -> None:
        trace = FakeTrace(
            id="t1",
            name="voice-session",
            user_id=None,
            session_id="voice-abc",
            tags=["voice", "call-lifecycle"],
        )
        result = validate_voice_trace_attribution(trace)
        assert result["user_id_correct"] is False

    def test_wrong_session_pattern(self) -> None:
        trace = FakeTrace(
            id="t1",
            name="voice-session",
            user_id="voice-agent",
            session_id="session-123",
            tags=["voice", "call-lifecycle"],
        )
        result = validate_voice_trace_attribution(trace)
        assert result["session_id_pattern"] is False

    def test_empty_session_id(self) -> None:
        trace = FakeTrace(
            id="t1",
            name="voice-session",
            user_id="voice-agent",
            session_id="",
            tags=["voice", "call-lifecycle"],
        )
        result = validate_voice_trace_attribution(trace)
        assert result["session_id_pattern"] is False

    def test_missing_voice_tag(self) -> None:
        trace = FakeTrace(
            id="t1",
            name="voice-session",
            user_id="voice-agent",
            session_id="voice-x",
            tags=["call-lifecycle"],
        )
        result = validate_voice_trace_attribution(trace)
        assert result["has_voice_tag"] is False
        assert result["has_lifecycle_tag"] is True

    def test_missing_lifecycle_tag(self) -> None:
        trace = FakeTrace(
            id="t1",
            name="voice-session",
            user_id="voice-agent",
            session_id="voice-x",
            tags=["voice"],
        )
        result = validate_voice_trace_attribution(trace)
        assert result["has_voice_tag"] is True
        assert result["has_lifecycle_tag"] is False

    def test_none_tags(self) -> None:
        trace = FakeTrace(
            id="t1",
            name="voice-session",
            user_id="voice-agent",
            session_id="voice-x",
            tags=None,
        )
        result = validate_voice_trace_attribution(trace)
        assert result["has_voice_tag"] is False
        assert result["has_lifecycle_tag"] is False


# ---------------------------------------------------------------------------
# build_evidence_summary
# ---------------------------------------------------------------------------


class TestBuildEvidenceSummary:
    """Tests for redacted evidence summary generation."""

    def test_complete_trace(self) -> None:
        trace = FakeTrace(
            id="trace-abc-123",
            name="voice-session",
            user_id="voice-agent",
            session_id="voice-call-42",
            tags=["voice", "call-lifecycle"],
            observations=[
                FakeObservation(name="voice-session"),
                FakeObservation(name="llm-call"),
            ],
        )
        summary = build_evidence_summary(trace)
        assert summary["trace_id"] == "trace-abc-123"
        assert summary["session_id"] == "voice-call-42"
        assert summary["user_id"] == "voice-agent"
        assert "voice-session" in summary["observation_names"]
        assert "llm-call" in summary["observation_names"]
        assert "voice" in summary["tags"]

    def test_empty_observations(self) -> None:
        trace = FakeTrace(
            id="t1",
            name="voice-session",
            user_id="voice-agent",
            session_id="voice-x",
            observations=[],
        )
        summary = build_evidence_summary(trace)
        assert summary["observation_names"] == []

    def test_none_observations(self) -> None:
        trace = FakeTrace(
            id="t1",
            name="voice-session",
            user_id="voice-agent",
            session_id="voice-x",
            observations=None,
        )
        summary = build_evidence_summary(trace)
        assert summary["observation_names"] == []

    def test_no_pii_leaked(self) -> None:
        """Ensure evidence summary does not expose raw call content."""
        trace = FakeTrace(
            id="t1",
            name="voice-session",
            user_id="voice-agent",
            session_id="voice-x",
            metadata={"call_id": "secret-call", "status": "completed"},
        )
        summary = build_evidence_summary(trace)
        # metadata is not part of evidence summary
        assert "secret-call" not in str(summary)


# ---------------------------------------------------------------------------
# Integration: update_voice_trace produces correct attribution
# ---------------------------------------------------------------------------


class TestUpdateVoiceTraceIntegration:
    """Test that update_voice_trace wiring matches gate expectations."""

    def test_produces_voice_agent_user_id(self) -> None:
        """update_voice_trace sets user_id='voice-agent' for attribution."""
        mock_lf = MagicMock()
        mock_obs = MagicMock()
        mock_obs_ctx = MagicMock()
        mock_obs_ctx.__enter__ = MagicMock(return_value=mock_obs)
        mock_obs_ctx.__exit__ = MagicMock(return_value=None)
        mock_lf.start_as_current_observation.return_value = mock_obs_ctx
        mock_lf.create_trace_id.return_value = "trace-unit-001"
        mock_prop_ctx = MagicMock()
        mock_prop_ctx.__enter__ = MagicMock(return_value=None)
        mock_prop_ctx.__exit__ = MagicMock(return_value=None)

        with (
            patch("src.voice.observability.get_client", return_value=mock_lf),
            patch(
                "src.voice.observability.propagate_attributes",
                return_value=mock_prop_ctx,
            ) as mock_prop,
        ):
            from src.voice.observability import update_voice_trace

            update_voice_trace(call_id="unit-1", status="answered")

        kwargs = mock_prop.call_args[1]
        assert kwargs["user_id"] == "voice-agent"
        assert kwargs["tags"] == ["voice", "call-lifecycle"]
        assert kwargs["session_id"] == "voice-unit-1"

    def test_produces_correct_session_id_pattern(self) -> None:
        """Session ID follows voice-* pattern."""
        mock_lf = MagicMock()
        mock_obs = MagicMock()
        mock_obs_ctx = MagicMock()
        mock_obs_ctx.__enter__ = MagicMock(return_value=mock_obs)
        mock_obs_ctx.__exit__ = MagicMock(return_value=None)
        mock_lf.start_as_current_observation.return_value = mock_obs_ctx
        mock_lf.create_trace_id.return_value = "trace-unit-002"
        mock_prop_ctx = MagicMock()
        mock_prop_ctx.__enter__ = MagicMock(return_value=None)
        mock_prop_ctx.__exit__ = MagicMock(return_value=None)

        with (
            patch("src.voice.observability.get_client", return_value=mock_lf),
            patch(
                "src.voice.observability.propagate_attributes",
                return_value=mock_prop_ctx,
            ) as mock_prop,
        ):
            from src.voice.observability import update_voice_trace

            update_voice_trace(
                call_id="my-call-id",
                status="completed",
                session_id="voice-custom-session",
            )

        kwargs = mock_prop.call_args[1]
        assert kwargs["session_id"].startswith("voice-")


class TestValidateVoiceTracesCli:
    """CLI behavior tests for the live validation gate."""

    def test_fails_when_fresh_trace_production_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Default mode must fail instead of validating stale traces."""
        from scripts import validate_voice_traces as gate

        validate_called = False

        def _raise_production_error() -> str:
            raise RuntimeError("trace producer unavailable")

        def _validate_existing_traces(
            lookback_minutes: int,
            expected_session_id: str | None = None,
        ) -> dict:
            nonlocal validate_called
            validate_called = True
            return {
                "ok": True,
                "evidence": {
                    "trace_id": "old-trace",
                    "session_id": "voice-old",
                    "user_id": "voice-agent",
                    "tags": ["voice", "call-lifecycle"],
                    "traces_found": 1,
                },
                "errors": [],
            }

        monkeypatch.setattr(sys, "argv", ["validate_voice_traces.py"])
        monkeypatch.setattr(gate, "check_langfuse_connectivity", lambda *_: True)
        monkeypatch.setattr(gate, "check_compose_service_name", lambda: True)
        monkeypatch.setattr(gate, "produce_voice_trace", _raise_production_error)
        monkeypatch.setattr(gate, "wait_for_ingestion", lambda _: None)
        monkeypatch.setattr(gate, "validate_traces", _validate_existing_traces)

        with pytest.raises(SystemExit) as exc_info:
            gate.main()

        assert exc_info.value.code == 1
        assert validate_called is False

    def test_produce_voice_trace_flushes_before_readback(self) -> None:
        """Short-lived CLI must flush the produced trace before polling."""
        from scripts import validate_voice_traces as gate

        mock_lf = MagicMock()

        with (
            patch("src.voice.observability.update_voice_trace") as mock_update,
            patch("telegram_bot.observability.get_client", return_value=mock_lf),
        ):
            session_id = gate.produce_voice_trace()

        assert session_id.startswith("voice-validate-")
        mock_update.assert_called_once()
        mock_lf.flush.assert_called_once_with()
