from pathlib import Path

import yaml


LINT_PATHS = ("src/", "telegram_bot/", "mini_app/", "services/", "scripts/")


def test_workflow_name_is_ci() -> None:
    """Workflow exposes the standard CI name."""
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["name"] == "CI"


def test_no_deploy_to_vps_job() -> None:
    """No job deploys to VPS; public CI must not expose deployment targets."""
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    job_names = [j.get("name") for j in data["jobs"].values()]
    assert "Deploy to VPS" not in job_names


def test_no_sensitive_deploy_patterns() -> None:
    """Workflow must not contain secrets, hostnames, or deploy actions that
    would leak deployment internals in a public repository."""
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    forbidden = [
        "SERVER_HOST",
        "SERVER_USER",
        "SSH_PRIVATE_KEY",
        "/opt/rag-fresh",
        "git reset --hard",
        "appleboy/ssh-action",
    ]
    for pattern in forbidden:
        assert pattern not in text, f"forbidden pattern in workflow: {pattern!r}"


def test_validation_jobs_exist() -> None:
    """Core validation: the Lint job runs."""
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert "lint" in data["jobs"], "missing 'lint' job key"
    assert data["jobs"]["lint"].get("name") == "Lint"


def test_ruff_lint_runs() -> None:
    """Linting runs as part of CI."""
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "ruff check" in text
    for path in LINT_PATHS:
        assert path in text


def test_makefile_lint_covers_telegram_bot() -> None:
    """Makefile lint target must cover telegram_bot/ to match CI."""
    text = Path("Makefile").read_text(encoding="utf-8")
    assert "LINT_PATHS :=" in text
    assert "ruff check $(LINT_PATHS)" in text
    for path in LINT_PATHS:
        assert path in text


def test_pre_push_gate_excludes_baseline_type_check() -> None:
    """pre-push must stay runnable even while the repo has baseline MyPy drift."""
    text = Path("Makefile").read_text(encoding="utf-8")
    line = next(line for line in text.splitlines() if line.startswith("pre-push:"))
    assert "lint" in line
    assert "format-check" in line
    assert "type-check" not in line


def test_guardrail_jobs_exist() -> None:
    """PR CI must include pr-guardrails, uv-lock, and compose-config jobs."""
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    for job_key in ("pr-guardrails", "uv-lock", "compose-config"):
        assert job_key in data["jobs"], f"missing '{job_key}' job in CI workflow"


def test_top_level_permissions_present() -> None:
    """CI workflow must declare top-level `permissions: contents: read`."""
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    permissions = data.get("permissions")
    assert permissions is not None, "missing top-level `permissions` key"
    assert permissions.get("contents") == "read", (
        f"expected `permissions.contents: read`, got {permissions}"
    )


# Self-hosted runner policy
# Light PR checks must run on GitHub-hosted runners. Self-hosted labels
# are only for trusted heavy/runtime/nightly checks with no secrets.


def test_runbook_documents_contents_read_permission_policy() -> None:
    """Runbook must document ``permissions: contents: read`` as the default.

    The self-hosted runner policy runbook owns the permission documentation
    for this slice. It must explicitly state that ``contents: read`` is the
    required default so that any future CI workflow changes in the
    guardrails-ci slice are bound by this documented policy.
    """
    runbook = Path("docs/runbooks/SELF_HOSTED_RUNNER.md")
    if not runbook.exists():
        return  # skip - covered by contract test

    text = runbook.read_text(encoding="utf-8")
    assert "contents: read" in text, (
        "SELF_HOSTED_RUNNER.md must document the 'permissions: contents: read' "
        "policy so that light-tier workflows are bound to this default."
    )


def test_ci_workflow_uses_github_hosted_runner() -> None:
    """CI workflow must use GitHub-hosted runners (ubuntu-latest).

    Self-hosted runners are only for trusted heavy/runtime/nightly checks.
    Light PR checks (lint, format, etc.) must stay on GitHub-hosted runners
    so they cannot be hijacked by forks or malicious PRs.
    """
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)

    runs_on_values: set[str] = set()
    for job_def in data.get("jobs", {}).values():
        if isinstance(job_def, dict) and "runs-on" in job_def:
            runs_on = job_def["runs-on"]
            if isinstance(runs_on, str):
                runs_on_values.add(runs_on)

    assert "self-hosted" not in runs_on_values, (
        "CI workflow must not use self-hosted runners. Self-hosted runners "
        "are only for trusted heavy/runtime/nightly checks (nightly-heavy.yml). "
        f"Found runs-on values: {sorted(runs_on_values)!r}"
    )

    assert "ubuntu-latest" in runs_on_values, (
        "CI workflow must use GitHub-hosted runner 'ubuntu-latest' for "
        "light PR checks. Found runs-on values: {sorted(runs_on_values)!r}"
    )


def test_ci_workflow_no_secrets_for_untrusted_pr_jobs() -> None:
    """CI workflow must not reference repository secrets that would leak to forks.

    In a public repository, ``pull_request`` events from forks do not have
    access to repository secrets. The one allowed exception is the ephemeral
    ``GITHUB_TOKEN`` consumed by the dedicated secret scan action.
    """
    data = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    allowed = {"${{ secrets.GITHUB_TOKEN }}"}
    for job_key, job in data["jobs"].items():
        for step in job.get("steps", []):
            env = step.get("env", {})
            for value in env.values():
                if isinstance(value, str) and "secrets." in value:
                    assert value in allowed and job_key == "secret-scan", (
                        f"Job `{job_key}` references non-allowed secret {value!r}; "
                        "PR-triggered jobs may only use the ephemeral GITHUB_TOKEN "
                        "for the secret-scan action."
                    )


def test_nightly_heavy_uses_self_hosted_for_heavy_tier() -> None:
    """Nightly heavy workflow must keep the expensive tier on self-hosted
    with the nightly-heavy label group.

    The self-hosted runner policy: GitHub-hosted for light PR checks,
    self-hosted for expensive heavy/runtime/nightly checks.
    """
    text = Path(".github/workflows/nightly-heavy.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)

    jobs = data.get("jobs", {})
    assert jobs, "nightly-heavy.yml must define at least one job"

    heavy_job = jobs.get("heavy-tier")
    assert heavy_job is not None, "nightly-heavy.yml must define heavy-tier"
    runs_on = heavy_job.get("runs-on", "")
    assert runs_on == ["self-hosted", "Linux", "X64", "nightly-heavy"], (
        "Job 'heavy-tier' in nightly-heavy.yml must use "
        "'[self-hosted, Linux, X64, nightly-heavy]' per self-hosted runner policy. "
        f"Got '{runs_on}'."
    )


def test_nightly_heavy_permissions_are_read_only() -> None:
    """Nightly heavy must declare top-level ``permissions: contents: read``."""
    text = Path(".github/workflows/nightly-heavy.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    permissions = data.get("permissions")
    assert permissions is not None, "nightly-heavy.yml must have a top-level permissions key"
    assert permissions.get("contents") == "read", (
        f"nightly-heavy.yml permissions.contents must be 'read', got {permissions}"
    )


def test_nightly_heavy_cancel_in_progress_is_true() -> None:
    """Nightly heavy must set ``concurrency.cancel-in-progress: true``."""
    text = Path(".github/workflows/nightly-heavy.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    concurrency = data.get("concurrency", {})
    assert concurrency.get("cancel-in-progress") is True, (
        f"nightly-heavy.yml concurrency.cancel-in-progress must be true, got {concurrency}"
    )


def test_nightly_heavy_jobs_have_timeouts() -> None:
    """Nightly-full and heavy-tier must declare appropriate timeout-minutes."""
    text = Path(".github/workflows/nightly-heavy.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)

    jobs = data.get("jobs", {})
    nightly_full = jobs.get("nightly-full")
    assert nightly_full is not None, "nightly-heavy.yml must define nightly-full"

    heavy_tier = jobs.get("heavy-tier")
    assert heavy_tier is not None, "nightly-heavy.yml must define heavy-tier"

    assert nightly_full.get("timeout-minutes") == 45, (
        f"nightly-full must set timeout-minutes: 45, got {nightly_full.get('timeout-minutes')!r}"
    )
    assert heavy_tier.get("timeout-minutes") == 180, (
        f"heavy-tier must set timeout-minutes: 180, got {heavy_tier.get('timeout-minutes')!r}"
    )


def test_nightly_full_runs_repo_compile_gate_before_test_suites() -> None:
    """Nightly full must use the same repo-wide syntax gate as PR fast-lane."""
    data = yaml.safe_load(Path(".github/workflows/nightly-heavy.yml").read_text(encoding="utf-8"))
    nightly_full = data["jobs"].get("nightly-full")
    assert nightly_full is not None, "nightly-heavy.yml must define nightly-full"

    run_commands = [
        step.get("run", "")
        for step in nightly_full.get("steps", [])
        if isinstance(step.get("run", ""), str)
    ]
    assert "make compile-python" in run_commands, (
        "nightly-full must run the repo-wide compile-python guardrail before suites."
    )
    suite_run_index = next(
        i for i, command in enumerate(run_commands) if "uv run pytest" in command
    )
    assert run_commands.index("make compile-python") < suite_run_index


def test_runbook_documents_runner_policy_essentials() -> None:
    """Runbook must document: permissions, workspace cleanup, no-secrets rule."""
    runbook = Path("docs/runbooks/SELF_HOSTED_RUNNER.md")
    if not runbook.exists():
        return  # skip - covered by contract test

    text = runbook.read_text(encoding="utf-8")

    missing = []
    if "permissions" not in text.lower():
        missing.append("permissions model")
    if "cleanup" not in text.lower() and "clean" not in text.lower():
        missing.append("workspace/cache cleanup")
    if "no secrets" not in text.lower() and "untrusted" not in text.lower():
        missing.append("no-secrets-for-untrusted-jobs")

    assert not missing, (
        "SELF_HOSTED_RUNNER.md must document these runner policy essentials: " + ", ".join(missing)
    )
