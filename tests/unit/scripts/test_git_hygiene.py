from pathlib import Path


def test_legacy_hygiene_scripts_are_archived() -> None:
    assert not Path("scripts/git_hygiene.py").exists()
    assert not Path("scripts/repo_cleanup.sh").exists()
    assert Path("scripts/archive/git_hygiene.py").exists()
    assert Path("scripts/archive/repo_cleanup.sh").exists()


def test_makefile_hygiene_targets_use_native_git_commands() -> None:
    text = Path("Makefile").read_text(encoding="utf-8")
    assert "scripts/git_hygiene.py" not in text
    assert "scripts/repo_cleanup.sh" not in text
    assert "git fetch --prune origin" in text
    assert "git for-each-ref --format=" in text
    assert "git worktree prune --dry-run" in text


def test_native_runbook_documents_safety_rules() -> None:
    text = Path("docs/runbooks/GIT_PR_ISSUE_NATIVE.md").read_text(encoding="utf-8")
    assert 'BASE_BRANCH="${REPO_BASE_BRANCH:-dev}"' in text
    assert 'MAIN_BRANCH="${MAIN_BRANCH:-dev}"' in text
    assert "Do not delete the current branch." in text
    assert "Do not remove dirty worktrees" in text
    assert "Check open PRs before deleting remote branches." in text


def test_force_cleanup_filters_current_and_worktree_branches() -> None:
    text = Path("Makefile").read_text(encoding="utf-8")
    assert "CURRENT_BRANCH=$$(git branch --show-current)" in text
    assert "WORKTREE_BRANCHES=$$(git worktree list --porcelain" in text
    assert '[ "$$branch" = "main" ] && continue' in text
    assert '[ "$$branch" = "master" ] && continue' in text
    assert '[ "$$branch" = "develop" ] && continue' in text
    assert '[ "$$branch" = "$$CURRENT_BRANCH" ] && continue' in text
    assert 'grep -Fxq "$$branch" && continue' in text
