"""Contract locks for repo-hygiene operator entrypoints (closes #1717, #1719, #1720).

Governance markdown playbooks were intentionally removed. #3379 (entrypoint
convergence) later removed the ``git-hygiene`` / ``pr-hygiene`` /
``issue-hygiene`` Make targets: the retained contract is only that the
legacy python helpers stay deleted and the audit-kept scripts stay on disk.
Operators run those scripts directly with ``uv run`` when needed.
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

# #3379: hygiene Make targets were removed; they must not come back silently.
REMOVED_HYGIENE_TARGETS = (
    "git-hygiene",
    "git-hygiene-fix",
    "pr-hygiene",
    "issue-hygiene",
    "repo-cleanup",
    "repo-cleanup-force",
)


def test_removed_hygiene_targets_stay_removed() -> None:
    """#3379 removed the hygiene Make DSL; do not resurrect it."""
    makefile = MAKEFILE.read_text(encoding="utf-8")
    present = [target for target in REMOVED_HYGIENE_TARGETS if f"\n{target}:" in f"\n{makefile}"]
    assert present == [], f"Removed hygiene targets reappeared in Makefile: {present}"


def test_audit_scripts_stay_on_disk() -> None:
    """Audit-kept scripts remain available for direct ``uv run`` invocation."""
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
