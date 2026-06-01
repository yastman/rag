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
    """Heavy PR checks must use built-in Linux self-hosted runner labels."""
    data = _load_workflow()
    for job_key, job in data["jobs"].items():
        labels = job.get("runs-on")
        assert labels == ["self-hosted", "Linux", "X64"], (
            f"{job_key} must run on [self-hosted, Linux, X64], got {labels!r}"
        )


def test_trusted_heavy_is_shadow_mode_until_baseline_green() -> None:
    """Heavy checks stay non-authoritative until contract/test baseline is green."""
    data = _load_workflow()
    for job_key, job in data["jobs"].items():
        assert job.get("continue-on-error") is True, (
            f"{job_key} must stay shadow mode until baseline is green"
        )
        test_steps = [
            step for step in job.get("steps", []) if str(step.get("name", "")).startswith("Run ")
        ]
        assert test_steps, f"{job_key} must include a test execution step"
        for step in test_steps:
            assert step.get("continue-on-error") is True, (
                f"{job_key} step {step.get('name')!r} must not redline the PR in shadow mode"
            )


def test_trusted_heavy_skips_untrusted_fork_prs() -> None:
    """Self-hosted runner must not execute untrusted fork pull_request code."""
    data = _load_workflow()
    for job_key, job in data["jobs"].items():
        condition = str(job.get("if", ""))
        assert "github.event.pull_request.head.repo.full_name == github.repository" in condition, (
            f"{job_key} must restrict pull_request jobs to same-repository branches"
        )


def test_trusted_heavy_contains_contract_and_fast_shadow_jobs() -> None:
    """Trusted heavy workflow must cover both contract and fast tests."""
    data = _load_workflow()
    jobs = data["jobs"]
    assert "heavy-contract-tests-shadow" in jobs
    assert "fast-tests-shadow" in jobs

    commands = "\n".join(
        step.get("run", "")
        for job in jobs.values()
        for step in job.get("steps", [])
        if isinstance(step.get("run", ""), str)
    )
    assert "make test-contract" in commands
    assert "make test" in commands
