"""Contract test for ADR-0010: voice path create_agent migration plan (***REMOVED***1535).

This contract guards the design-first slice of issue ***REMOVED***1535 (`blocked`,
`lane:design-first`). The voice path still runs the legacy 11-node
StateGraph in `telegram_bot/graph/graph.py::build_graph`, while the text
path runs through `langchain.agents.create_agent` in
`telegram_bot/agents/agent.py::create_bot_agent`. Migration cannot land
in a single PR; the first deliverable is an ADR that codifies the plan.

The test is intentionally minimal: it pins the ADR's existence, status,
required structural headings, and Context7 attribution. It does NOT
inspect any code under `telegram_bot/`; the migration itself is gated by
follow-up issues. When migration progresses, a future PR flips the ADR
status from "Proposed" to "Accepted" — that flip is the only expected
breaking change to this contract, and the test is updated alongside.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = REPO_ROOT / "docs" / "adr" / "0010-voice-path-create-agent-migration-plan.md"
ADR_INDEX_PATH = REPO_ROOT / "docs" / "adr" / "README.md"

***REMOVED*** Status is a bold-line marker in this repo's ADRs (matches ADR-0001..0009).
***REMOVED*** All other entries are markdown headings.
REQUIRED_HEADINGS: tuple[str, ...] = (
    "Context",
    "Decision",
    "Consequences",
    "Migration Steps",
)
STATUS_LINE_MARKER = "**Status:**"

***REMOVED*** At least one Context7-compatible library ID must be cited for SDK-native research.
***REMOVED*** Format: /org/project or /websites/<slug>.
CONTEXT7_ID_MARKERS: tuple[str, ...] = (
    "/websites/langchain_oss_python_langchain",
    "/websites/langchain_oss_python_langgraph",
)


def test_adr_file_exists() -> None:
    """ADR-0010 file must exist at the canonical path."""
    assert ADR_PATH.is_file(), (
        f"ADR-0010 not found at {ADR_PATH.relative_to(REPO_ROOT)}. "
        "Issue ***REMOVED***1535 is design-first; the migration plan ADR must land "
        "before any voice-path topology change."
    )


def test_adr_status_is_proposed() -> None:
    """Status must be 'Proposed' until a follow-up PR completes the migration."""
    text = ADR_PATH.read_text(encoding="utf-8")
    ***REMOVED*** Repo convention: '**Status:** Proposed' (matches ADR-0001..0009).
    assert f"{STATUS_LINE_MARKER} Proposed" in text, (
        "ADR-0010 must declare '**Status:** Proposed'. A follow-up PR will "
        "flip this to Accepted once the gradual migration completes."
    )
    ***REMOVED*** Guardrail: forbid 'Accepted' until the migration is actually done.
    forbidden = ("**Status:** Accepted", "Status: Accepted")
    assert not any(marker in text for marker in forbidden), (
        "ADR-0010 must not be Accepted while the voice path still runs "
        "build_graph. Update tests + flip status in the same PR that "
        "removes telegram_bot/graph/graph.py."
    )


@pytest.mark.parametrize("heading", REQUIRED_HEADINGS)
def test_adr_has_required_heading(heading: str) -> None:
    """ADR-0010 must contain each required structural heading."""
    text = ADR_PATH.read_text(encoding="utf-8")
    ***REMOVED*** Heading style in this repo is '***REMOVED******REMOVED*** Heading' (or '***REMOVED******REMOVED******REMOVED*** Sub'); accept both.
    assert (f"***REMOVED******REMOVED*** {heading}" in text) or (f"***REMOVED******REMOVED******REMOVED*** {heading}" in text), (
        f"ADR-0010 missing required heading: {heading!r}. "
        f"Required headings: {REQUIRED_HEADINGS}."
    )


def test_adr_cites_context7_library_id() -> None:
    """ADR-0010 must cite at least one Context7 library ID as SDK evidence."""
    text = ADR_PATH.read_text(encoding="utf-8")
    assert any(marker in text for marker in CONTEXT7_ID_MARKERS), (
        "ADR-0010 must cite at least one Context7-compatible library ID "
        f"from {CONTEXT7_ID_MARKERS} in its Evidence section. The "
        "migration plan is grounded on canonical SDK documentation, not "
        "on inferred behaviour."
    )


def test_adr_index_links_adr_0010() -> None:
    """The ADR index must link ADR-0010 so contributors can discover it."""
    text = ADR_INDEX_PATH.read_text(encoding="utf-8")
    assert "0010-voice-path-create-agent-migration-plan.md" in text, (
        "docs/adr/README.md must include an index entry pointing to "
        "0010-voice-path-create-agent-migration-plan.md."
    )
