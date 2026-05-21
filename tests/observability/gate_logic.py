"""Shared gate logic for voice trace validation.

Contains validation functions and test helpers used by both the integration
tests (test_voice_trace_gate.py) and unit tests (test_voice_trace_gate_unit.py).
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeTrace:
    """Minimal Langfuse trace representation for assertions."""

    id: str
    name: str
    user_id: str | None = None
    session_id: str | None = None
    tags: list[str] | None = None
    metadata: dict | None = None
    observations: list | None = None


@dataclass
class FakeObservation:
    """Minimal Langfuse observation for assertions."""

    name: str
    type: str = "SPAN"


# ---------------------------------------------------------------------------
# Core gate logic
# ---------------------------------------------------------------------------


def validate_voice_trace_presence(traces_data: list) -> bool:
    """Return True if at least one voice-session trace is present."""
    return len(traces_data) > 0


def validate_voice_trace_attribution(trace: object) -> dict[str, bool]:
    """Validate service attribution fields on a trace object."""
    user_id = getattr(trace, "user_id", None)
    session_id = getattr(trace, "session_id", None) or ""
    tags = getattr(trace, "tags", None) or []

    return {
        "user_id_correct": user_id == "voice-agent",
        "session_id_pattern": session_id.startswith("voice-"),
        "has_voice_tag": "voice" in tags,
        "has_lifecycle_tag": "call-lifecycle" in tags,
    }


def build_evidence_summary(trace: object) -> dict[str, str | list[str]]:
    """Build a redacted evidence summary from a trace (no PII)."""
    observations = getattr(trace, "observations", None) or []
    obs_names = [getattr(o, "name", "unknown") for o in observations]
    return {
        "trace_id": getattr(trace, "id", "unknown"),
        "session_id": getattr(trace, "session_id", "unknown"),
        "observation_names": obs_names,
        "user_id": getattr(trace, "user_id", "unknown"),
        "tags": getattr(trace, "tags", None) or [],
    }
