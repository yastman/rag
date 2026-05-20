from pathlib import Path


def test_agents_declares_workspace_isolation_policy() -> None:
    text = Path("AGENTS.md").read_text(encoding="utf-8")
    assert "Do not start non-trivial edits in a dirty checkout" in text
    assert "Use an isolated git worktree" in text
    assert "docs/engineering/repo-hygiene-runbook.md" in text


def test_agents_declares_hooks_static_tests_local_policy() -> None:
    text = Path("AGENTS.md").read_text(encoding="utf-8")
    assert "Git hooks and push gates run lint/static guardrails only" in text
    assert "Run tests explicitly as local validation" in text
    assert "docs/LOCAL-DEVELOPMENT.md" in text


def test_gitignore_allows_superpowers_plan_documents() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")
    assert "docs/superpowers/" in text
    assert "!docs/superpowers/plans/" in text
    assert "!docs/superpowers/plans/*.md" in text


def test_repo_hygiene_runbook_documents_worktree_start_rule() -> None:
    text = Path("docs/engineering/repo-hygiene-runbook.md").read_text(encoding="utf-8")
    assert "Before Starting New Work" in text
    assert "make git-hygiene" in text
    assert "git worktree add .worktrees/<branch>" in text
