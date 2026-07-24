"""Contract locks for the native-git script migration (closes #1726 partial).

Destructive decisions that are easy to regress accidentally:

1. ``scripts/git_hygiene.py`` was removed outright (closes #2891). The
   ``scripts/archive/`` directory was deleted too — git history is the
   archive. The Makefile target ``git-hygiene`` is now native git
   (``git fetch --prune``, ``git branch --merged``, ``git for-each-ref``,
   ``git worktree list --porcelain``, ``git ls-files --others``).
2. ``scripts/repo_cleanup.sh`` was removed for the same reason.

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


# ------------- Archive contract ------------------------------------------------


@pytest.mark.parametrize(
    "active_path,archived_name",
    [
        (SCRIPTS / "git_hygiene.py", "git_hygiene.py"),
        (SCRIPTS / "repo_cleanup.sh", "repo_cleanup.sh"),
    ],
)
def test_audited_script_deleted(active_path: Path, archived_name: str) -> None:
    """Both scripts deleted outright; git history is the archive (#2891)."""
    assert not active_path.exists(), (
        f"{active_path.relative_to(REPO_ROOT)} reappeared at the active path. "
        f"This script is deleted (#2891). Use the native-git path or a new audit decision."
    )
    archived = ARCHIVE / archived_name
    assert not archived.exists(), (
        f"scripts/archive/{archived_name} reappeared. Per #2891 the "
        f"scripts/archive/ directory is deleted and git history is the archive."
    )


# ------------- git-hygiene target uses native git --------------------------------


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
        f"This target must call git directly (#2891)."
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


# ------------- Audit-kept scripts stay wired -------------------------------------


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
