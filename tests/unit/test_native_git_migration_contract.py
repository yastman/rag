"""Contract locks for the native-git script migration (closes ***REMOVED***1726 partial).

The audit in ``docs/engineering/script-native-migration-matrix.md`` made
two destructive decisions that are easy to regress accidentally:

1. ``scripts/git_hygiene.py`` was archived under
   ``scripts/archive/git_hygiene.py``. The Makefile target
   ``git-hygiene`` is now native git (``git fetch --prune``,
   ``git branch --merged``, ``git for-each-ref``,
   ``git worktree list --porcelain``, ``git ls-files --others``).
2. ``scripts/repo_cleanup.sh`` was archived under
   ``scripts/archive/repo_cleanup.sh`` for the same reason.

A future PR that "fixes" git-hygiene by reintroducing a python helper
would silently restart the audit cycle. These locks prevent that.

Two scripts kept by the audit decision (``pr_queue_audit.py``,
``issue_queue_audit.py``) must remain in their active locations and stay
wired into ``make pr-hygiene`` / ``make issue-hygiene``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
SCRIPTS = REPO_ROOT / "scripts"
ARCHIVE = SCRIPTS / "archive"


def _make_target_body(target: str) -> str:
    """Return the recipe lines (everything until next non-tab line) for a target."""
    text = MAKEFILE.read_text(encoding="utf-8")
    pattern = rf"(?ms)^{re.escape(target)}:.*?$\n((?:\t.*\n?)+)"
    match = re.search(pattern, text)
    if not match:
        pytest.fail(f"Makefile target `{target}` not found")
    return match.group(1)


***REMOVED*** ------------- Archive contract ------------------------------------------------


@pytest.mark.parametrize(
    "active_path,archived_name",
    [
        (SCRIPTS / "git_hygiene.py", "git_hygiene.py"),
        (SCRIPTS / "repo_cleanup.sh", "repo_cleanup.sh"),
    ],
)
def test_audited_script_archived(active_path: Path, archived_name: str) -> None:
    """Both scripts moved to ``scripts/archive/`` per the audit matrix."""
    assert not active_path.exists(), (
        f"{active_path.relative_to(REPO_ROOT)} reappeared at the active path. "
        f"Per docs/engineering/script-native-migration-matrix.md, this script "
        f"is archived. Use the native-git path or a new audit decision."
    )
    archived = ARCHIVE / archived_name
    assert archived.exists(), (
        f"scripts/archive/{archived_name} missing. The audit matrix declares "
        f"this script 'archived as scripts/archive/{archived_name}'."
    )


***REMOVED*** ------------- git-hygiene target uses native git --------------------------------


def test_git_hygiene_target_uses_native_git() -> None:
    """``make git-hygiene`` must call git directly, not a python helper.

    The audit-mandated commands per migration matrix:
      - ``git fetch --prune origin``
      - ``git branch --merged``
      - ``git for-each-ref``
      - ``git worktree list --porcelain``
      - ``git ls-files --others --exclude-standard``
    """
    body = _make_target_body("git-hygiene")
    required = [
        "git fetch --prune origin",
        "git branch --merged",
        "git for-each-ref",
        "git worktree list --porcelain",
        "git ls-files --others --exclude-standard",
    ]
    missing = [cmd for cmd in required if cmd not in body]
    assert not missing, (
        f"`make git-hygiene` lost native-git commands: {missing}. "
        f"Per docs/engineering/script-native-migration-matrix.md, this target "
        f"must call git directly."
    )


def test_git_hygiene_target_does_not_invoke_archived_script() -> None:
    """``make git-hygiene`` must not call ``scripts/git_hygiene.py`` (archived)."""
    body = _make_target_body("git-hygiene")
    assert "scripts/git_hygiene.py" not in body, (
        "`make git-hygiene` re-introduced scripts/git_hygiene.py. The script "
        "is archived under scripts/archive/. Update the audit matrix and "
        "ADR before reintroducing it."
    )
    assert "scripts/repo_cleanup" not in body, (
        "`make git-hygiene` references scripts/repo_cleanup* which is archived."
    )


def test_git_hygiene_fix_target_uses_native_git() -> None:
    """``make git-hygiene-fix`` (dry-run cleanup) must use native git operations."""
    body = _make_target_body("git-hygiene-fix")
    required = [
        "git fetch --prune origin",
        "git branch --merged",
        "git merge-base --is-ancestor",
        "git branch -D",
    ]
    missing = [cmd for cmd in required if cmd not in body]
    assert not missing, f"`make git-hygiene-fix` lost native-git operations: {missing}"
    assert "scripts/git_hygiene.py" not in body
    assert "scripts/repo_cleanup" not in body


***REMOVED*** ------------- Audit-kept scripts stay wired -------------------------------------


def test_pr_hygiene_target_invokes_pr_queue_audit() -> None:
    """``make pr-hygiene`` keeps ``scripts/pr_queue_audit.py`` (audit decision: keep)."""
    body = _make_target_body("pr-hygiene")
    assert "scripts/pr_queue_audit.py" in body, (
        "`make pr-hygiene` lost reference to scripts/pr_queue_audit.py"
    )
    assert (SCRIPTS / "pr_queue_audit.py").exists()


def test_issue_hygiene_target_invokes_issue_queue_audit() -> None:
    """``make issue-hygiene`` keeps ``scripts/issue_queue_audit.py`` (audit decision: keep)."""
    body = _make_target_body("issue-hygiene")
    assert "scripts/issue_queue_audit.py" in body, (
        "`make issue-hygiene` lost reference to scripts/issue_queue_audit.py"
    )
    assert (SCRIPTS / "issue_queue_audit.py").exists()


***REMOVED*** ------------- Migration matrix structural contract ------------------------------


def test_migration_matrix_documents_decisions_for_audited_scripts() -> None:
    """The matrix must record the explicit decision for each audited script.

    Decisions per audit:
      - git_hygiene.py:        archived
      - repo_cleanup.sh:       archived
      - pr_queue_audit.py:     keep custom audit wrapper
      - issue_queue_audit.py:  keep custom audit wrapper
    """
    matrix = (REPO_ROOT / "docs" / "engineering" / "script-native-migration-matrix.md").read_text(
        encoding="utf-8"
    )

    assert "scripts/git_hygiene.py" in matrix
    assert "scripts/repo_cleanup.sh" in matrix
    assert "scripts/pr_queue_audit.py" in matrix
    assert "scripts/issue_queue_audit.py" in matrix
    ***REMOVED*** Decision keywords surface in the matrix body.
    assert "archived" in matrix.lower(), (
        "migration matrix lost the 'archived' decision keyword for "
        "scripts/git_hygiene.py / scripts/repo_cleanup.sh"
    )
    assert "keep custom audit wrapper" in matrix, (
        "migration matrix lost the 'keep custom audit wrapper' decision for "
        "pr_queue_audit.py / issue_queue_audit.py"
    )
