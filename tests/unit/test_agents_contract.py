import subprocess
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


def test_repo_hygiene_runbook_documents_worktree_start_rule() -> None:
    text = Path("docs/engineering/repo-hygiene-runbook.md").read_text(encoding="utf-8")
    assert "Before Starting New Work" in text
    assert "make git-hygiene" in text
    assert "git worktree add .worktrees/<branch>" in text


def test_codex_web_prompt_defines_worker_pack_as_queue() -> None:
    text = Path("docs/engineering/codex-web-prompt.md").read_text(encoding="utf-8")
    assert "Worker Pack" in text
    assert "queue, not a PR scope" in text
    assert "one issue = one branch = one PR" in text


def test_codex_web_prompt_requires_duplicate_pr_preflight() -> None:
    text = Path("docs/engineering/codex-web-prompt.md").read_text(encoding="utf-8")
    assert "Search open PRs" in text
    assert "do not create a duplicate PR" in text


def test_codex_web_prompt_requires_validation_matrix() -> None:
    text = Path("docs/engineering/codex-web-prompt.md").read_text(encoding="utf-8")
    assert "Required Validation Matrix" in text
    assert "make test-core" in text
    assert "make test-contract" in text


def test_test_deletion_requires_coverage_preservation_map() -> None:
    worker = Path("docs/engineering/codex-web-prompt.md").read_text(encoding="utf-8")
    reviewer = Path("docs/engineering/gh-pr-review.md").read_text(encoding="utf-8")
    template = Path(".github/pull_request_template.md").read_text(encoding="utf-8")

    combined_guidance = "\n".join([worker, reviewer, template])

    assert "coverage-preservation map" in worker
    assert "coverage-preservation map" in reviewer
    assert "coverage-preservation map" in template

    for action in ("deleting", "moving", "skipping", "xfail-ing", "retargeting", "weakening"):
        assert action in combined_guidance

    for required_field in (
        "deleted test path",
        "old assertion / behavior / contract",
        "whether behavior still exists on current `dev`",
        "current adjacent surfaces checked",
        "replacement or preserved coverage",
        "focused validation command",
        "follow-up issue if coverage is intentionally deferred",
    ):
        assert required_field in template

    for owner in (
        "worker prompt",
        "TDD/focused tests",
        "PR body",
        "reviewer",
        "no-code closeout",
        "orchestrator close decision",
    ):
        assert owner in combined_guidance
