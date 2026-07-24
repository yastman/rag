"""Contract locks for repo-hygiene operator entrypoints (closes #1717, #1719, #1720).

Governance markdown playbooks were intentionally removed. The live contract is
the Makefile targets and audit scripts operators still run.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

SCRIPT_PR_AUDIT = REPO_ROOT / "scripts" / "pr_queue_audit.py"
SCRIPT_ISSUE_AUDIT = REPO_ROOT / "scripts" / "issue_queue_audit.py"
SCRIPT_GIT_HYGIENE = REPO_ROOT / "scripts" / "git_hygiene.py"
SCRIPT_REPO_CLEANUP = REPO_ROOT / "scripts" / "repo_cleanup.sh"
ARCHIVE_DIR = REPO_ROOT / "scripts" / "archive"

MAKEFILE = REPO_ROOT / "Makefile"

HYGIENE_TARGETS = ("git-hygiene", "pr-hygiene", "issue-hygiene")


def test_makefile_defines_hygiene_targets() -> None:
    """Operators still get the three hygiene Make entrypoints."""
    makefile = MAKEFILE.read_text(encoding="utf-8")
    for target in HYGIENE_TARGETS:
        assert f"\n{target}:" in f"\n{makefile}", (
            f"Makefile missing target `{target}` required by the hygiene contract"
        )


def test_pr_and_issue_hygiene_targets_wire_audit_scripts() -> None:
    """Kept audit scripts must stay on disk and wired into Make."""
    makefile = MAKEFILE.read_text(encoding="utf-8")
    assert "scripts/pr_queue_audit.py" in makefile
    assert "scripts/issue_queue_audit.py" in makefile
    assert SCRIPT_PR_AUDIT.exists(), "scripts/pr_queue_audit.py missing"
    assert SCRIPT_ISSUE_AUDIT.exists(), "scripts/issue_queue_audit.py missing"


def test_legacy_python_hygiene_scripts_stay_deleted() -> None:
    """Native-git migration deleted the python helpers; do not resurrect them."""
    assert not SCRIPT_GIT_HYGIENE.exists(), (
        "scripts/git_hygiene.py reappeared at the active path; native-git contract violated."
    )
    assert not SCRIPT_REPO_CLEANUP.exists(), (
        "scripts/repo_cleanup.sh reappeared at the active path; native-git contract violated."
    )
    assert not ARCHIVE_DIR.exists(), (
        "scripts/archive/ reappeared; git history is the archive (#2891)."
    )
