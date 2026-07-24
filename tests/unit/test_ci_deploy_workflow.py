from pathlib import Path

import yaml


LINT_PATHS = ("src/", "telegram_bot/", "services/", "scripts/")


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


def test_static_validation_jobs_exist() -> None:
    """PR CI keeps static validation jobs but no PR-body guardrail job."""
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    for job_key in ("uv-lock", "compose-config"):
        assert job_key in data["jobs"], f"missing '{job_key}' job in CI workflow"
    assert "pr-guardrails" not in data["jobs"], "PR-body guardrail job was removed by CORE-011"


def test_top_level_permissions_present() -> None:
    """CI workflow must declare top-level `permissions: contents: read`."""
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    permissions = data.get("permissions")
    assert permissions is not None, "missing top-level `permissions` key"
    assert permissions.get("contents") == "read", (
        f"expected `permissions.contents: read`, got {permissions}"
    )


def test_ci_workflow_uses_github_hosted_runner() -> None:
    """CI workflow must use GitHub-hosted runners (ubuntu-latest).

    Static PR checks must stay on GitHub-hosted runners.
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
        "CI workflow must not use self-hosted runners. "
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
