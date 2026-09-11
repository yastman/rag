from pathlib import Path

import pytest


def test_legacy_hygiene_scripts_are_deleted() -> None:
    # Per #2891 the scripts are deleted outright; git history is the archive,
    # so scripts/archive/ must not exist either.
    assert not Path("scripts/git_hygiene.py").exists()
    assert not Path("scripts/repo_cleanup.sh").exists()
    assert not Path("scripts/archive/git_hygiene.py").exists()
    assert not Path("scripts/archive/repo_cleanup.sh").exists()


@pytest.mark.parametrize(
    "target",
    [
        "git-hygiene",
        "git-hygiene-fix",
        "pr-hygiene",
        "issue-hygiene",
        "repo-cleanup",
        "repo-cleanup-force",
    ],
)
def test_removed_hygiene_make_targets_stay_removed(target: str) -> None:
    """#3379 removed the hygiene Make DSL; these targets must not come back."""
    text = Path("Makefile").read_text(encoding="utf-8")
    assert f"\n{target}:" not in f"\n{text}", (
        f"Removed hygiene target `{target}` reappeared in the Makefile (#3379)"
    )
