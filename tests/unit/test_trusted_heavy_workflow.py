from __future__ import annotations

from pathlib import Path

import yaml


WORKFLOW = Path(".github/workflows/trusted-heavy.yml")


def _load_workflow() -> dict:
    assert WORKFLOW.exists(), "trusted-heavy.yml workflow must exist"
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    if "on" not in data and True in data:
        data["on"] = data[True]
    return data


def test_trusted_heavy_runs_only_on_builtin_linux_self_hosted_labels() -> None:
    """Self-hosted PR checks must use the pr-fast label group."""
    data = _load_workflow()
    for job_key, job in data["jobs"].items():
        if "self-hosted" not in str(job.get("runs-on", "")):
            continue
        labels = job.get("runs-on")
        assert labels == ["self-hosted", "Linux", "X64", "pr-fast"], (
            f"{job_key} must run on [self-hosted, Linux, X64, pr-fast], got {labels!r}"
        )


def test_trusted_heavy_self_hosted_jobs_have_timeout() -> None:
    """Every self-hosted job in trusted-heavy must declare timeout-minutes: 20."""
    data = _load_workflow()
    for job_key, job in data["jobs"].items():
        if "self-hosted" not in str(job.get("runs-on", "")):
            continue
        timeout = job.get("timeout-minutes")
        assert timeout == 20, f"{job_key} must set timeout-minutes: 20, got {timeout!r}"


def test_trusted_heavy_workflow_runs_for_all_prs() -> None:
    """Workflow must create stable check contexts even for docs-only PRs."""
    data = _load_workflow()
    pull_request = data["on"]["pull_request"]
    assert "paths" not in pull_request, (
        "trusted-heavy.yml must not use workflow-level path filters; required "
        "checks would otherwise be missing on docs-only PRs."
    )


def test_trusted_heavy_has_github_hosted_path_filter() -> None:
    """A lightweight GitHub-hosted job decides whether self-hosted tests run."""
    data = _load_workflow()
    changes = data["jobs"].get("changes")
    assert changes is not None, "trusted-heavy.yml must define the changes job"
    assert changes["name"] == "Trusted Heavy Path Filter"
    assert changes["runs-on"] == "ubuntu-latest"
    assert changes["outputs"]["run_heavy"] == "${{ steps.filter.outputs.run_heavy }}"


def test_trusted_heavy_path_filter_covers_risk_paths() -> None:
    """The path filter must match the same code/runtime/test surfaces as before."""
    data = _load_workflow()
    changes = data["jobs"]["changes"]
    filter_step = next(step for step in changes["steps"] if step.get("id") == "filter")
    script = filter_step["run"]

    assert "git diff --name-only" in script
    assert "run_heavy=true" in script
    for token in (
        "src/*",
        "telegram_bot/*",
        "mini_app/*",
        "services/*",
        "tests/*",
        "compose*.yml",
        "Makefile",
        "pyproject.toml",
        "uv.lock",
        ".github/workflows/*",
    ):
        assert token in script


def test_fast_tests_is_authoritative_for_trusted_risk_paths() -> None:
    """Fast Tests is the first self-hosted PR gate promoted out of shadow."""
    data = _load_workflow()
    fast = data["jobs"].get("fast-tests")
    assert fast is not None, "trusted-heavy.yml must define fast-tests"
    assert fast["name"] == "Fast Tests"
    assert fast["needs"] == "changes"
    assert fast.get("continue-on-error") is not True, (
        "Fast Tests must not stay shadow once promoted to a candidate required gate."
    )

    run_steps = [step for step in fast["steps"] if step.get("run") == "make test"]
    assert run_steps, "Fast Tests must run `make test`"
    assert all(step.get("continue-on-error") is not True for step in run_steps)


def test_fast_tests_runs_repo_compile_gate_before_make_test() -> None:
    """Fast Tests must catch repo-wide Python syntax drift before pytest."""
    data = _load_workflow()
    fast = data["jobs"].get("fast-tests")
    assert fast is not None, "trusted-heavy.yml must define fast-tests"

    run_commands = [
        step.get("run", "")
        for step in fast.get("steps", [])
        if isinstance(step.get("run", ""), str)
    ]
    assert "make compile-python" in run_commands, (
        "Fast Tests must run the repo-wide compile-python guardrail before make test."
    )
    assert "make test" in run_commands, "Fast Tests must still run `make test`."
    assert run_commands.index("make compile-python") < run_commands.index("make test")


def test_heavy_contract_tests_is_authoritative_for_trusted_risk_paths() -> None:
    """Heavy Contract Tests must fail the trusted PR gate on contract regressions."""
    data = _load_workflow()
    job = data["jobs"].get("heavy-contract-tests")
    assert job is not None, "trusted-heavy.yml must define heavy-contract-tests"
    assert job["name"] == "Heavy Contract Tests"
    assert job["needs"] == "changes"
    assert job.get("continue-on-error") is not True
    test_steps = [step for step in job.get("steps", []) if step.get("run") == "make test-contract"]
    assert test_steps, "heavy-contract-tests must run `make test-contract`"
    for step in test_steps:
        assert step.get("continue-on-error") is not True, (
            f"heavy-contract-tests step {step.get('name')!r} must fail on regressions"
        )


def test_trusted_heavy_skips_untrusted_fork_prs() -> None:
    """Self-hosted runner must not execute untrusted fork pull_request code."""
    data = _load_workflow()
    for job_key, job in data["jobs"].items():
        if "self-hosted" not in str(job.get("runs-on", "")):
            continue
        condition = str(job.get("if", ""))
        assert "github.event.pull_request.head.repo.full_name == github.repository" in condition, (
            f"{job_key} must restrict pull_request jobs to same-repository branches"
        )
        assert "needs.changes.outputs.run_heavy == 'true'" in condition, (
            f"{job_key} must run only when the path filter says heavy tests are needed"
        )


def test_trusted_heavy_contains_contract_and_fast_gate_jobs() -> None:
    """Trusted heavy workflow must cover both contract and fast tests."""
    data = _load_workflow()
    jobs = data["jobs"]
    assert "heavy-contract-tests" in jobs
    assert "heavy-contract-tests-shadow" not in jobs
    assert "fast-tests" in jobs

    commands = "\n".join(
        step.get("run", "")
        for job in jobs.values()
        for step in job.get("steps", [])
        if isinstance(step.get("run", ""), str)
    )
    assert "make test-contract" in commands
    assert "make test" in commands
