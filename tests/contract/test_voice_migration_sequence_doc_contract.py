"""Contract: ``docs/engineering/voice-create-agent-migration-sequence.md`` exists
and pins the cross-issue sequencing for the voice path migration epic.

The voice-path migration to ``create_agent`` is split across four GitHub
issues (#1535 parent, #2050 tools, #2051 rewire, #2048 lifecycle
extraction). ADR-0010 documents the *plan*, but contributors picking up
a follow-up issue need to know:

* which sibling issues are already done;
* which issues block which (and which were just unblocked);
* what the next executable slice is per issue.

The sequencing document is the single source of truth for that
ordering. It lives under ``docs/engineering/`` (per the existing pattern
of ``script-native-migration-matrix.md``) and is referenced from
ADR-0010 plus from each open child issue. This contract pins the
document's existence and minimum content.

When the epic completes, the ``Status`` line flips from ``In progress``
to ``Done`` and that flip is the only expected breaking change to this
contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = (
    REPO_ROOT
    / "docs"
    / "engineering"
    / "voice-create-agent-migration-sequence.md"
)


REQUIRED_ISSUE_REFS: tuple[str, ...] = (
    "#1535",  # parent — ADR-0010 plan
    "#2050",  # tools (closed)
    "#2051",  # rewire voice handler to create_agent
    "#2048",  # extract PropertyBot lifecycle method slices
    "#1948",  # layering closure that unblocks #2048
)

REQUIRED_HEADINGS: tuple[str, ...] = (
    "Status",
    "Sequence",
    "Next executable slice",
    "Cross-references",
)


def test_sequence_doc_exists() -> None:
    assert DOC_PATH.is_file(), (
        f"Voice migration sequencing doc not found at "
        f"{DOC_PATH.relative_to(REPO_ROOT)}. The doc is the single "
        "source of truth for #1535/#2050/#2051/#2048 ordering and is "
        "referenced from ADR-0010 plus each open child issue."
    )


@pytest.mark.parametrize("issue_ref", REQUIRED_ISSUE_REFS)
def test_sequence_doc_references_each_issue(issue_ref: str) -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    assert issue_ref in text, (
        f"voice-create-agent-migration-sequence.md must mention "
        f"{issue_ref} so contributors discover the cross-issue ordering."
    )


@pytest.mark.parametrize("heading", REQUIRED_HEADINGS)
def test_sequence_doc_has_required_heading(heading: str) -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    assert (f"## {heading}" in text) or (f"### {heading}" in text), (
        f"voice-create-agent-migration-sequence.md missing required "
        f"heading: {heading!r}. The minimum structure is "
        f"{REQUIRED_HEADINGS}."
    )


def test_sequence_doc_records_2050_as_done_and_2048_as_unblocked() -> None:
    """Pins the two facts that motivate this doc landing now:
    #2050 (tools) was closed on 2026-05-26, and #1948 final closure
    (PR #2135) unblocked #2048. Both facts must be visible in the doc
    so a contributor reading it immediately knows what is actionable.
    """
    text = DOC_PATH.read_text(encoding="utf-8").lower()
    assert "closed" in text or "done" in text, (
        "Sequencing doc must mark sibling issues as closed/done so the "
        "reader can see what is left."
    )
    assert "unblock" in text or "unblocks" in text, (
        "Sequencing doc must call out that #1948 unblocks #2048 — "
        "without this the reader assumes #2048 is still gated."
    )


def test_adr_0010_links_sequence_doc() -> None:
    """ADR-0010 stays the design plan, but it must point readers at the
    sequencing doc so they don't lose the cross-issue context.
    """
    adr = REPO_ROOT / "docs" / "adr" / "0010-voice-path-create-agent-migration-plan.md"
    text = adr.read_text(encoding="utf-8")
    assert "voice-create-agent-migration-sequence.md" in text, (
        "ADR-0010 must link to docs/engineering/voice-create-agent-"
        "migration-sequence.md so readers can find the per-slice "
        "sequencing without re-deriving it from issue comments."
    )
