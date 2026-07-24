import subprocess
from pathlib import Path


def test_agents_declares_workspace_isolation_policy() -> None:
    text = Path("AGENTS.md").read_text(encoding="utf-8")
    assert "phase/<phase-id>" in text
    assert "one worktree per" in text
    assert "git worktree list --porcelain" in text


def test_agents_declares_hooks_static_tests_local_policy() -> None:
    text = Path("AGENTS.md").read_text(encoding="utf-8")
    assert "make dev-setup" in text
    assert "commit and push hooks" in text
    assert "make test-core" in text
    assert "make candidate-check" in text
    assert "GitHub runs no pytest" in text


def test_gitignore_allows_superpowers_plan_documents() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")
    assert "docs/superpowers/" in text
    assert "!docs/superpowers/plans/" in text
    assert "!docs/superpowers/plans/*.md" in text


def test_gitignore_allows_only_superpowers_plan_markdown_files() -> None:
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "docs/superpowers/plans/generated.txt"],
        check=False,
    )
    assert ignored.returncode == 0

    nested = subprocess.run(
        ["git", "check-ignore", "-q", "docs/superpowers/plans/nested/generated.md"],
        check=False,
    )
    assert nested.returncode == 0

    allowed = subprocess.run(
        ["git", "check-ignore", "-q", "docs/superpowers/plans/handwritten.md"],
        check=False,
    )
    assert allowed.returncode == 1
