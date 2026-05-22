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
