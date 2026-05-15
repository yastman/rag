from pathlib import Path

import yaml


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
    """Core validation: the Lint & Type Check job runs."""
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert "lint" in data["jobs"], "missing 'lint' job key"
    assert data["jobs"]["lint"].get("name") == "Lint & Type Check"


def test_ruff_lint_runs() -> None:
    """Linting runs as part of CI."""
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "ruff check src/ telegram_bot/" in text
