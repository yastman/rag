"""Contract locks for the native-git script migration (closes #1726 partial).

Destructive decisions that are easy to regress accidentally:

1. ``scripts/git_hygiene.py`` was removed outright (closes #2891). The
   ``scripts/archive/`` directory was deleted too — git history is
   the archive. The ``git-hygiene`` Make targets were removed by #3379
   (entrypoint convergence); native git commands are run directly.
2. ``scripts/repo_cleanup.sh`` was removed for the same reason.

A future PR that "fixes" git hygiene by reintroducing a python helper
would silently restart the audit cycle. These locks prevent that.

The audit-kept scripts (``pr_queue_audit.py``, ``issue_queue_audit.py``)
remain on disk for direct ``uv run`` use; their Make wrappers were removed
by #3379 and must not reappear.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
SCRIPTS = REPO_ROOT / "scripts"
ARCHIVE = SCRIPTS / "archive"


# ------------- Archive contract ------------------------------------------------


def test_audited_script_deleted() -> None:
    """Both scripts deleted outright; git history is the archive (#2891)."""
    assert not (SCRIPTS / "git_hygiene.py").exists(), (
        "scripts/git_hygiene.py reappeared at the active path. "
        "This script is deleted (#2891). Use the native-git path or a new audit decision."
    )
    assert not (SCRIPTS / "repo_cleanup.sh").exists(), (
        "scripts/repo_cleanup.sh reappeared at the active path. This script is deleted (#2891)."
    )
    assert not (ARCHIVE / "git_hygiene.py").exists(), (
        "scripts/archive/git_hygiene.py reappeared. Per #2891 the "
        "scripts/archive/ directory is deleted and git history is the archive."
    )
    assert not (ARCHIVE / "repo_cleanup.sh").exists(), (
        "scripts/archive/repo_cleanup.sh reappeared. Per #2891 the "
        "scripts/archive/ directory is deleted and git history is the archive."
    )


# ------------- Removed hygiene Make DSL stays removed (#3379) -------------------


def test_removed_git_hygiene_targets_stay_removed() -> None:
    """#3379 removed the git-hygiene/repo-cleanup Make targets; do not resurrect."""
    text = MAKEFILE.read_text(encoding="utf-8")
    for target in ("git-hygiene", "git-hygiene-fix", "repo-cleanup", "repo-cleanup-force"):
        assert f"\n{target}:" not in f"\n{text}", (
            f"Removed target `{target}` reappeared in the Makefile (#3379)"
        )


def test_audit_kept_scripts_stay_on_disk_without_make_wrappers() -> None:
    """The audit-kept scripts stay directly runnable; no Make wiring returns."""
    assert (SCRIPTS / "pr_queue_audit.py").exists()
    assert (SCRIPTS / "issue_queue_audit.py").exists()
    text = MAKEFILE.read_text(encoding="utf-8")
    for target in ("pr-hygiene", "issue-hygiene"):
        assert f"\n{target}:" not in f"\n{text}", (
            f"Removed target `{target}` reappeared in the Makefile (#3379)"
        )
