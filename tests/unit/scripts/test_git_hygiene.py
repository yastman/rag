import subprocess
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
    assert "BASE_REF=origin/$$MAIN_BRANCH" in text
    assert "CURRENT_BRANCH=$$(git branch --show-current)" in text
    assert "WORKTREE_BRANCHES=$$(git worktree list --porcelain" in text
    assert 'git merge-base --is-ancestor "$$branch" "$$BASE_REF"' in text
    assert 'git branch -D "$$branch"' in text
    assert '[ "$$branch" = "main" ] && continue' in text
    assert '[ "$$branch" = "master" ] && continue' in text
    assert '[ "$$branch" = "develop" ] && continue' in text
    assert '[ "$$branch" = "$$CURRENT_BRANCH" ] && continue' in text
    assert 'grep -Fxq "$$branch" && continue' in text


def test_force_cleanup_deletes_branch_merged_into_base_from_other_head(tmp_path) -> None:
    repo_root = Path.cwd()
    bare = tmp_path / "origin.git"
    repo = tmp_path / "repo"

    subprocess.run(["git", "init", "--bare", "--initial-branch=dev", str(bare)], check=True)
    subprocess.run(["git", "init", "--initial-branch=dev", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(bare)], check=True)

    (repo / "file.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "file.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "base"], check=True)

    subprocess.run(["git", "-C", str(repo), "checkout", "-b", "feature/merged"], check=True)
    (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "feature.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feature"], check=True)

    subprocess.run(["git", "-C", str(repo), "checkout", "dev"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "merge", "--no-ff", "feature/merged", "-m", "merge feature"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "push", "-u", "origin", "dev"], check=True)

    subprocess.run(
        ["git", "-C", str(repo), "checkout", "-b", "operator/worktree", "dev~1"], check=True
    )

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "-f",
            str(repo_root / "Makefile"),
            "repo-cleanup-force",
            "MAIN_BRANCH=dev",
        ],
        cwd=repo,
        input="y\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    branches = subprocess.run(
        ["git", "-C", str(repo), "branch", "--format=%(refname:short)"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    assert "feature/merged" not in branches
