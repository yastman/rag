"""Voice trace validation gate tests.

Validates Langfuse traces for the voice-session family:
- Trace presence after calling update_voice_trace
- Service attribution (user_id='voice-agent')
- Required tags and session_id pattern
- Observation/span presence per trace_contract.yaml

These tests use mocked Langfuse responses for deterministic unit-lane execution.
A live-Langfuse variant is gated by LANGFUSE_PUBLIC_KEY presence.
"""

from __future__ import annotations

import os
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
# Helpers
# ---------------------------------------------------------------------------


def _build_mock_trace(
    *,
    trace_id: str = "trace-voice-test-001",
    name: str = "voice-session",
    user_id: str = "voice-agent",
    session_id: str = "voice-test-call-1",
    tags: list[str] | None = None,
    metadata: dict | None = None,
    observations: list | None = None,
) -> FakeTrace:
    """Build a mock trace matching expected voice-session structure."""
    return FakeTrace(
        id=trace_id,
        name=name,
        user_id=user_id,
        session_id=session_id,
        tags=tags or ["voice", "call-lifecycle"],
        metadata=metadata or {"call_id": "test-call-1", "status": "completed"},
        observations=observations or [FakeObservation(name="voice-session")],
    )


# ---------------------------------------------------------------------------
# Tests: Mocked (unit-lane, always run)
# ---------------------------------------------------------------------------


class TestVoiceTraceGateMocked:
    """Voice trace gate tests using mocked Langfuse API responses."""

    def test_trace_presence_success(self, mock_langfuse_client: MagicMock) -> None:
        """Gate passes when voice-session trace is found."""
        mock_trace = _build_mock_trace()
        mock_langfuse_client.api.trace.list.return_value = MagicMock(data=[mock_trace])
        mock_langfuse_client.api.trace.get.return_value = mock_trace

        traces = mock_langfuse_client.api.trace.list(name="voice-session").data
        assert validate_voice_trace_presence(traces)

    def test_trace_presence_failure(self, mock_langfuse_client: MagicMock) -> None:
        """Gate fails when no voice-session trace is found."""
        mock_langfuse_client.api.trace.list.return_value = MagicMock(data=[])

        traces = mock_langfuse_client.api.trace.list(name="voice-session").data
        assert not validate_voice_trace_presence(traces)

    def test_attribution_correct(self) -> None:
        """Gate validates correct service attribution."""
        trace = _build_mock_trace()
        result = validate_voice_trace_attribution(trace)
        assert all(result.values()), f"Attribution check failed: {result}"

    def test_attribution_wrong_user_id(self) -> None:
        """Gate detects wrong user_id."""
        trace = _build_mock_trace(user_id="wrong-agent")
        result = validate_voice_trace_attribution(trace)
        assert not result["user_id_correct"]

    def test_attribution_wrong_session_pattern(self) -> None:
        """Gate detects session_id not matching voice-* pattern."""
        trace = _build_mock_trace(session_id="other-session")
        result = validate_voice_trace_attribution(trace)
        assert not result["session_id_pattern"]

    def test_attribution_missing_tags(self) -> None:
        """Gate detects missing voice tags."""
        trace = _build_mock_trace(tags=["other"])
        result = validate_voice_trace_attribution(trace)
        assert not result["has_voice_tag"]
        assert not result["has_lifecycle_tag"]

    def test_evidence_summary_structure(self) -> None:
        """Evidence summary contains expected fields without PII."""
        trace = _build_mock_trace()
        summary = build_evidence_summary(trace)
        assert summary["trace_id"] == "trace-voice-test-001"
        assert summary["session_id"] == "voice-test-call-1"
        assert "voice-session" in summary["observation_names"]
        assert summary["user_id"] == "voice-agent"
        assert "voice" in summary["tags"]

    def test_voice_session_in_required_families(self, trace_contract: dict) -> None:
        """voice-session is listed in required_families in trace_contract."""
        assert "voice-session" in trace_contract["required_families"]

    def test_voice_session_in_coverage_tiers(self, trace_contract: dict) -> None:
        """voice-session is in opportunistic_for_1307 coverage tier."""
        tiers = trace_contract.get("coverage_tiers", {})
        assert "voice-session" in tiers.get("opportunistic_for_1307", [])

    def test_update_voice_trace_produces_expected_calls(self) -> None:
        """Calling update_voice_trace produces the expected Langfuse calls."""
        mock_lf = MagicMock()
        mock_observation = MagicMock()
        mock_obs_ctx = MagicMock()
        mock_obs_ctx.__enter__ = MagicMock(return_value=mock_observation)
        mock_obs_ctx.__exit__ = MagicMock(return_value=None)
        mock_lf.start_as_current_observation.return_value = mock_obs_ctx
        mock_lf.create_trace_id.return_value = "trace-gate-test"
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
                call_id="gate-test-1",
                status="completed",
                duration_sec=15,
            )

        # Verify trace was created with voice-agent attribution
        mock_prop.assert_called_once()
        call_kwargs = mock_prop.call_args[1]
        assert call_kwargs["user_id"] == "voice-agent"
        assert call_kwargs["tags"] == ["voice", "call-lifecycle"]
        assert call_kwargs["session_id"] == "voice-gate-test-1"


# ---------------------------------------------------------------------------
# Tests: Live Langfuse (gated by env var)
# ---------------------------------------------------------------------------

_LIVE_LANGFUSE_AVAILABLE = bool(os.environ.get("LANGFUSE_PUBLIC_KEY"))


@pytest.mark.skipif(
    not _LIVE_LANGFUSE_AVAILABLE,
    reason="LANGFUSE_PUBLIC_KEY not set; skipping live Langfuse tests",
)
class TestVoiceTraceGateLive:
    """Voice trace gate tests against live local Langfuse (opt-in)."""

    def test_live_trace_lookup(self) -> None:
        """Query Langfuse API for recent voice-session traces."""
        from datetime import UTC, datetime, timedelta

        from langfuse import Langfuse

        lf = Langfuse()
        from_ts = datetime.now(UTC) - timedelta(hours=1)
        traces = lf.api.trace.list(
            name="voice-session",
            from_timestamp=from_ts,
            order_by="timestamp.desc",
            limit=5,
        )
        # This test just verifies connectivity; trace may or may not exist
        assert hasattr(traces, "data")
        lf.flush()
