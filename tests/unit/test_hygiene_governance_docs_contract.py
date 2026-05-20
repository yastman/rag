"""Contract locks for repo-hygiene governance docs (closes #1717, #1719, #1720).

These docs are the canonical operator playbook for keeping the repo, the
open PR queue, and the issue backlog manageable:

- ``docs/engineering/repo-hygiene-runbook.md`` — weekly runbook (#1717).
- ``docs/engineering/issue-triage.md`` — decision model & lanes (#1720).
- ``docs/engineering/script-native-migration-matrix.md`` — script audit (#1726).

The runbook references three Make targets and three audit scripts. If any
of them is renamed or deleted, the runbook drifts silently and operators
get a stale playbook. This contract pins the cross-references so the
weekly process stays reproducible.

If a future PR legitimately renames a target or splits a doc, update both
the doc and these locks together — never silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]

DOC_RUNBOOK = REPO_ROOT / "docs" / "engineering" / "repo-hygiene-runbook.md"
DOC_TRIAGE = REPO_ROOT / "docs" / "engineering" / "issue-triage.md"
DOC_MATRIX = REPO_ROOT / "docs" / "engineering" / "script-native-migration-matrix.md"

# Audit scripts referenced by the runbook.
SCRIPT_PR_AUDIT = REPO_ROOT / "scripts" / "pr_queue_audit.py"
SCRIPT_ISSUE_AUDIT = REPO_ROOT / "scripts" / "issue_queue_audit.py"
SCRIPT_GIT_HYGIENE = REPO_ROOT / "scripts" / "git_hygiene.py"

MAKEFILE = REPO_ROOT / "Makefile"


# ------------- File existence locks ------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [DOC_RUNBOOK, DOC_TRIAGE, DOC_MATRIX],
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_governance_doc_exists(path: Path) -> None:
    """Three governance docs are part of the contract; none may disappear silently."""
    assert path.exists(), (
        f"missing governance doc: {path.relative_to(REPO_ROOT)}. See #1717 / #1719 / #1720."
    )
    assert path.stat().st_size > 0, f"empty doc: {path.relative_to(REPO_ROOT)}"


# ------------- Runbook structural sections ----------------------------------------


def test_runbook_has_required_sections() -> None:
    """Runbook must keep its three top-level operational sections.

    Splitting #1717 into per-lane child issues (#1719 PR queue, #1720
    issue queue) requires that the runbook still presents all three lanes
    in one document so operators can run the Monday check end-to-end.
    """
    text = DOC_RUNBOOK.read_text(encoding="utf-8")
    required_sections = [
        "## TL;DR",  # Monday 5-minute check command list.
        "## Safety guarantees",
        "## 1. Git hygiene",
        "## 2. PR queue triage",
        "## 3. Issue queue hygiene",
        "### Triage SLA",  # #1719 SLA contract.
        "### Splitting issues",  # #1720 split rules.
        "### Lane labels",
    ]
    missing = [s for s in required_sections if s not in text]
    assert not missing, (
        f"docs/engineering/repo-hygiene-runbook.md drifted; missing section(s): "
        f"{missing}. Update both the doc and this lock together."
    )


def test_runbook_references_all_three_make_targets() -> None:
    """Runbook prescribes three Make entrypoints; they must exist in the Makefile.

    A rename of any target breaks the operator runbook silently otherwise.
    """
    runbook = DOC_RUNBOOK.read_text(encoding="utf-8")
    targets = ["git-hygiene", "pr-hygiene", "issue-hygiene"]
    for target in targets:
        assert f"make {target}" in runbook, (
            f"runbook lost reference to `make {target}`; #1717 contract"
        )

    if MAKEFILE.exists():
        makefile = MAKEFILE.read_text(encoding="utf-8")
        for target in targets:
            # Match a target definition at line start: ``<target>:`` (with optional deps).
            assert f"\n{target}:" in f"\n{makefile}" or f"^{target}:" in makefile, (
                f"Makefile missing target `{target}` referenced by repo-hygiene-runbook.md"
            )


def test_runbook_references_remaining_audit_scripts() -> None:
    """The runbook calls two audit scripts that must exist on disk.

    ``scripts/git_hygiene.py`` was archived as part of #1726 (script audit
    matrix); the runbook now invokes native git via ``make git-hygiene``
    instead. See ``docs/engineering/script-native-migration-matrix.md``.
    """
    runbook = DOC_RUNBOOK.read_text(encoding="utf-8")
    expected = {
        "scripts/pr_queue_audit.py": SCRIPT_PR_AUDIT,
        "scripts/issue_queue_audit.py": SCRIPT_ISSUE_AUDIT,
    }
    for ref, script_path in expected.items():
        assert ref in runbook, f"runbook lost reference to {ref}"
        assert script_path.exists(), f"runbook references {ref} but file is missing"


def test_runbook_does_not_reference_archived_git_hygiene_script() -> None:
    """``scripts/git_hygiene.py`` is archived under ``scripts/archive/``.

    Live runbook must not point operators at the archived path. The native
    git replacement is wired through ``make git-hygiene`` /
    ``make git-hygiene-fix``. Drift here means the audit migration in
    #1726 regressed.
    """
    runbook = DOC_RUNBOOK.read_text(encoding="utf-8")
    assert "scripts/git_hygiene.py" not in runbook, (
        "runbook still references scripts/git_hygiene.py — that script was "
        "archived per #1726 (script-native-migration-matrix.md). Use "
        "`make git-hygiene` / `make git-hygiene-fix` instead."
    )
    # Defense in depth: the archived file must remain only under archive/.
    assert not SCRIPT_GIT_HYGIENE.exists(), (
        "scripts/git_hygiene.py reappeared at the active path; #1726 archive contract violated."
    )
    archived = REPO_ROOT / "scripts" / "archive" / "git_hygiene.py"
    assert archived.exists(), (
        "scripts/archive/git_hygiene.py missing; the audit matrix declared "
        "the file 'archived as scripts/archive/git_hygiene.py'."
    )


# ------------- Issue-triage decision model lock ------------------------------------


def test_issue_triage_has_decision_model_and_lanes() -> None:
    """#1720 contract: triage doc names the three lanes and the decision model."""
    text = DOC_TRIAGE.read_text(encoding="utf-8")
    required = [
        "## Decision Model",
        "## Execution Lanes",
        "Quick execution",
        "Plan needed",
        "Design first",
        "## Session Checklist",
    ]
    missing = [s for s in required if s not in text]
    assert not missing, f"docs/engineering/issue-triage.md missing required section(s): {missing}"


# ------------- Script audit matrix lock --------------------------------------------


def test_script_native_migration_matrix_covers_audit_targets() -> None:
    """#1726 audit must list the four scripts the matrix tracks.

    If any row is dropped, the audit footprint drifts and #1726 cannot be
    closed without re-running the inventory.
    """
    text = DOC_MATRIX.read_text(encoding="utf-8")
    expected = [
        "scripts/git_hygiene.py",
        "scripts/repo_cleanup.sh",
        "scripts/pr_queue_audit.py",
        "scripts/issue_queue_audit.py",
    ]
    for entry in expected:
        assert entry in text, (
            f"script-native-migration-matrix.md lost row for `{entry}`; #1726 contract"
        )
