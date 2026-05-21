"""Contract: no stale infra directories at repo root (***REMOVED***1526, ***REMOVED***1527).

Two cleanup themes share the same shape — leftover throwaway scratch
directories that drifted into the working tree from past swarm /
orchestration sessions and never got pruned:

- Three ``tmp.<random>/`` directories left over from March 2026 swarm
  work (***REMOVED***1526):

  - ``tmp.CwOPYeK8wR/``
  - ``tmp.QApjFztnuW/``
  - ``tmp.vS0FKeuPSl/``

  ``tmp.*`` is gitignored at ``.gitignore`` line 290, but the
  directories themselves were never removed from the working tree on
  every developer's clone. They are not tracked, but they show up in
  ``git status`` as untracked noise and make ``ls`` at the repo root
  confusing.

- ``.github/workflows.disabled/`` (***REMOVED***1527): an old duplicate of the
  active CI workflows, gitignored at ``.gitignore`` line 248. Like the
  ``tmp.*`` dirs, it is gitignored but not tracked, so it survives on
  developer machines where it was created before the gitignore rule
  landed.

This contract guards the cleanup: if any of these directories reappear
at the repo root (tracked or untracked), the test fails. Re-introducing
one of them on a future branch will be caught in CI.

The check uses ``Path.exists()`` rather than ``git ls-files`` so that
it catches both tracked reintroductions and untracked-on-disk
reappearances inside CI checkouts and developer worktrees.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN: tuple[Path, ...] = (
    REPO_ROOT / "tmp.CwOPYeK8wR",
    REPO_ROOT / "tmp.QApjFztnuW",
    REPO_ROOT / "tmp.vS0FKeuPSl",
    REPO_ROOT / ".github" / "workflows.disabled",
)


@pytest.mark.parametrize(
    "path",
    FORBIDDEN,
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_stale_root_dir_is_absent(path: Path) -> None:
    """Each forbidden infra directory must not exist at the repo root.

    The companion ``.gitignore`` entries (``tmp.*`` and
    ``.github/workflows.disabled/``) prevent accidental re-tracking,
    but the directories must also be physically absent from the
    working tree to keep ``git status`` clean and the root tidy
    (***REMOVED***1526, ***REMOVED***1527).
    """
    if path.exists():
        rel = path.relative_to(REPO_ROOT)
        raise AssertionError(
            f"Stale infra directory '{rel}' has reappeared at the repo root. "
            "These directories are leftover scratch space from prior swarm / "
            "orchestration sessions and must not be reintroduced. Remove the "
            "directory (it is already gitignored) and, if a tool created it, "
            "fix the tool to write under a temp dir outside the working tree "
            "(***REMOVED***1526, ***REMOVED***1527)."
        )
