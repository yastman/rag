"""Guardrail tests for the CI workflow (PR gate slice).

Covers:
- Job existence: pr-guardrails, uv-lock, compose-config
- Top-level permissions: contents: read
- No secrets requirement on pull_request
- Correct tool/mode usage per job
- No heavy/runtime/RAG/e2e jobs leaking into the PR gate
"""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _load_workflow() -> dict:
    assert CI_WORKFLOW.exists(), f"CI workflow not found at {CI_WORKFLOW}"
    data = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML still treats the GitHub Actions key `on` as a boolean in YAML 1.1.
    # Normalize it so tests do not accidentally skip trigger assertions.
    if "on" not in data and True in data:
        data["on"] = data[True]
    return data


def _read_workflow_text() -> str:
    assert CI_WORKFLOW.exists(), f"CI workflow not found at {CI_WORKFLOW}"
    return CI_WORKFLOW.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Job existence
# ---------------------------------------------------------------------------


def test_uv_lock_job_exists() -> None:
    """CI must include a `uv-lock` job for dependency freshness checks."""
    data = _load_workflow()
    assert "uv-lock" in data["jobs"], "missing 'uv-lock' job key"


def test_compose_config_job_exists() -> None:
    """CI must include a `compose-config` job for Docker Compose validation."""
    data = _load_workflow()
    assert "compose-config" in data["jobs"], "missing 'compose-config' job key"


def test_pr_guardrails_job_exists() -> None:
    """CI must include a `pr-guardrails` job for PR policy enforcement."""
    data = _load_workflow()
    assert "pr-guardrails" in data["jobs"], "missing 'pr-guardrails' job key"


# ---------------------------------------------------------------------------
# Top-level permissions
# ---------------------------------------------------------------------------


def test_top_level_permissions_contents_read() -> None:
    """Top-level permissions must include `contents: read` for least-privilege."""
    data = _load_workflow()
    permissions = data.get("permissions")
    assert permissions is not None, "missing top-level `permissions` key"
    assert permissions.get("contents") == "read", f"expected `contents: read`, got {permissions}"


# ---------------------------------------------------------------------------
# Job secrets safety
# ---------------------------------------------------------------------------


def test_pr_jobs_do_not_require_repo_secrets() -> None:
    """PR-triggered jobs must not reference repository secrets."""
    # Check that no PR-triggered job uses `secrets.` -- secrets must be
    # scoped to push/workflow_dispatch jobs only, not pull_request.
    # We verify by checking job-level `secrets` keys.
    data = _load_workflow()
    on = data.get("on", {})
    pr_config = on.get("pull_request")
    assert pr_config is not None, "CI workflow must remain pull_request-triggered"

    # Find which jobs are unconditionally defined (all of them run on PR).
    # Since the trigger is `on: pull_request`, all jobs run on PR.
    for job_key, job in data["jobs"].items():
        secrets_section = job.get("secrets", {})
        assert not secrets_section, (
            f"Job `{job_key}` declares `secrets` -- PR jobs must not require "
            f"secrets as they run from forks"
        )
        # Also check the raw text for `secrets.` references
        # in step env or with blocks for this job.
        # We'll do a rough check: no `secrets.` in the entire file
        # for the PR-trigger scenario is too broad. Instead check
        # that step `env` doesn't reference `secrets.`.

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


# ---------------------------------------------------------------------------
# uv-lock job specifics
# ---------------------------------------------------------------------------


def test_uv_lock_uses_frozen_behavior() -> None:
    """uv-lock job must verify the lockfile with `--frozen` or `--locked`."""
    data = _load_workflow()
    job = data["jobs"]["uv-lock"]
    steps = job.get("steps", [])
    commands: list[str] = []
    for step in steps:
        run = step.get("run", "")
        if isinstance(run, str):
            commands.append(run)
    combined = "\n".join(commands)
    assert "--frozen" in combined or "--locked" in combined, (
        "uv-lock job must use `--frozen` or `--locked` to verify lockfile integrity"
    )


def test_uv_lock_uses_github_hosted_runner() -> None:
    """uv-lock must run on a GitHub-hosted runner (not self-hosted)."""
    data = _load_workflow()
    job = data["jobs"]["uv-lock"]
    runs_on = job.get("runs-on")
    assert runs_on is not None, "uv-lock job missing `runs-on`"
    assert isinstance(runs_on, str) or (isinstance(runs_on, dict) and runs_on.get("labels")), (
        f"Unexpected runs-on shape: {runs_on!r}"
    )
    labels = [runs_on] if isinstance(runs_on, str) else runs_on.get("labels", [])
    label_str = " ".join(labels).lower()
    assert "self-hosted" not in label_str, f"uv-lock must use GitHub-hosted runner, got {runs_on!r}"
    assert "ubuntu" in label_str, f"uv-lock must use ubuntu runner, got {runs_on!r}"


# ---------------------------------------------------------------------------
# compose-config job specifics
# ---------------------------------------------------------------------------


def test_compose_config_uses_ci_env() -> None:
    """compose-config must use the CI env fixture for deterministic rendering."""
    data = _load_workflow()
    job = data["jobs"]["compose-config"]
    steps = job.get("steps", [])
    commands: list[str] = []
    for step in steps:
        run = step.get("run", "")
        if isinstance(run, str):
            commands.append(run)
    combined = "\n".join(commands)
    assert "compose.ci.env" in combined, (
        "compose-config job must use `tests/fixtures/compose.ci.env`"
    )
    assert "config" in combined, "compose-config job must run `docker compose config`"
    assert "--quiet" in combined, (
        "compose-config job must use `--quiet` to validate without noisy output"
    )


def test_compose_config_uses_github_hosted_runner() -> None:
    """compose-config must run on a GitHub-hosted runner."""
    data = _load_workflow()
    job = data["jobs"]["compose-config"]
    runs_on = job.get("runs-on")
    assert runs_on is not None, "compose-config job missing `runs-on`"
    labels = [runs_on] if isinstance(runs_on, str) else runs_on.get("labels", [])
    label_str = " ".join(labels).lower()
    assert "self-hosted" not in label_str, (
        f"compose-config must use GitHub-hosted runner, got {runs_on!r}"
    )


# ---------------------------------------------------------------------------
# pr-guardrails job specifics
# ---------------------------------------------------------------------------


def test_pr_guardrails_uses_validator_script() -> None:
    """pr-guardrails must invoke the project PR policy validator."""
    data = _load_workflow()
    job = data["jobs"]["pr-guardrails"]
    steps = job.get("steps", [])
    commands: list[str] = []
    for step in steps:
        run = step.get("run", "")
        if isinstance(run, str):
            commands.append(run)
    combined = "\n".join(commands)
    assert "scripts/ci/validate_pr_guardrails.py" in combined, (
        "pr-guardrails job must invoke scripts/ci/validate_pr_guardrails.py"
    )


def test_pr_guardrails_uses_github_hosted_runner() -> None:
    """pr-guardrails must run on a GitHub-hosted runner."""
    data = _load_workflow()
    job = data["jobs"]["pr-guardrails"]
    runs_on = job.get("runs-on")
    assert runs_on is not None, "pr-guardrails job missing `runs-on`"
    labels = [runs_on] if isinstance(runs_on, str) else runs_on.get("labels", [])
    label_str = " ".join(labels).lower()
    assert "self-hosted" not in label_str, (
        f"pr-guardrails must use GitHub-hosted runner, got {runs_on!r}"
    )


def test_contract_tests_not_required_in_light_ci_until_baseline_green() -> None:
    """Red contract baseline must not be required by the light PR workflow."""
    data = _load_workflow()
    assert "contract-tests" not in data["jobs"], (
        "make test-contract is currently a shadow self-hosted check; do not "
        "make it a light required CI job until the baseline is green."
    )


# ---------------------------------------------------------------------------
# No heavy/RAG/e2e jobs in PR gate
# ---------------------------------------------------------------------------


def test_no_e2e_or_rag_jobs_in_workflow() -> None:
    """PR CI must not include heavy e2e/RAG/runtime jobs in this slice."""
    data = _load_workflow()
    job_keys = list(data["jobs"].keys())
    forbidden = {"e2e", "rag", "smoke", "load", "benchmark", "integration"}
    for key in job_keys:
        key_lower = key.lower()
        assert not any(f in key_lower for f in forbidden), (
            f"Forbidden job key `{key}` -- heavy jobs must not leak into the PR CI slice"
        )


def test_no_deploy_jobs_in_workflow() -> None:
    """PR CI must not include deploy/ssh/VPS jobs."""
    data = _load_workflow()
    job_keys = list(data["jobs"].keys())
    forbidden = {"deploy", "ssh", "vps", "push"}
    for key in job_keys:
        key_lower = key.lower()
        assert not any(f in key_lower for f in forbidden), (
            f"Forbidden job key `{key}` -- deploy jobs must not leak into the PR CI slice"
        )
