"""Contract for agent workflow mode separation."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DOC = REPO_ROOT / "docs" / "engineering" / "agent-workflow-modes.md"
ENGINEERING_INDEX = REPO_ROOT / "docs" / "engineering" / "README.md"
WORKFLOW_INDEX = REPO_ROOT / "docs" / "indexes" / "engineering-workflows.md"
ROADMAP = REPO_ROOT / "docs" / "plans" / "open-issues-roadmap-2026-06-10.md"


def test_agent_workflow_modes_are_documented_and_separated() -> None:
    text = WORKFLOW_DOC.read_text(encoding="utf-8")

    assert "Pick exactly one mode" in text
    assert "PR Coordinator Mode" in text
    assert "Issue Executor Mode" in text
    assert "Audit Planner Mode" in text
    assert "Do not create a new feature/refactor PR while operating in PR Coordinator mode" in text
    assert "Do not merge PRs" in text
    assert "Do not implement code changes" in text


def test_pr_coordinator_policy_keeps_review_queue_lightweight() -> None:
    text = WORKFLOW_DOC.read_text(encoding="utf-8")

    assert "Do not run full `make test` for docs-only PRs by default" in text
    assert "Do not create a separate worktree for each docs-only review" in text
    assert "`git diff --check`; markdown/link checks when available" in text
    assert "targeted MyPy; `make check`; focused tests" in text
    assert (
        "lockfile check; import/dependency contract tests; `make check`; `make test` only before final merge if runtime-wide"
        in text
    )
    assert "the PR is not superseded" in text


def test_workflow_doc_is_discoverable_from_indexes_and_roadmap() -> None:
    for path in (ENGINEERING_INDEX, WORKFLOW_INDEX, ROADMAP):
        text = path.read_text(encoding="utf-8")
        assert "agent-workflow-modes.md" in text, f"{path} must link the workflow mode contract"

    roadmap = ROADMAP.read_text(encoding="utf-8")
    assert "This roadmap is an Audit Planner artifact" in roadmap
    assert "Do not mix PR queue cleanup with new issue execution" in roadmap
