"""Contract tests for project Semgrep guardrails."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SEMGREP_CONFIG = REPO_ROOT / ".semgrep" / "project-guardrails.yml"
SEMGREP_VERSION = "1.163.0"

REQUIRED_RULE_IDS = {
    "python.no-datetime-utcnow",
    "python.no-subprocess-shell-true",
    "python.no-os-system",
    "github-actions.no-pull-request-target",
    "compose.no-latest-image",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    assert path.exists(), f"Missing expected YAML file: {path}"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if path == CI_WORKFLOW and "on" not in data and True in data:
        data["on"] = data[True]
    assert isinstance(data, dict), f"{path} must contain a YAML mapping"
    return data


def test_semgrep_config_contains_required_rule_ids() -> None:
    data = _load_yaml(SEMGREP_CONFIG)
    rules = data.get("rules")
    assert isinstance(rules, list), ".semgrep/project-guardrails.yml must define rules"

    actual = {rule.get("id") for rule in rules if isinstance(rule, dict)}
    assert actual >= REQUIRED_RULE_IDS


def test_semgrep_rules_are_errors() -> None:
    data = _load_yaml(SEMGREP_CONFIG)
    for rule in data["rules"]:
        assert rule["severity"] == "ERROR", f"{rule['id']} must block CI"


def test_ci_has_semgrep_job() -> None:
    data = _load_yaml(CI_WORKFLOW)
    job = data["jobs"].get("semgrep")
    assert job is not None, "CI workflow must define the semgrep job"
    assert job["name"] == "Semgrep"
    assert job["runs-on"] == "ubuntu-latest"


def test_ci_semgrep_job_uses_pinned_cli_and_project_rules() -> None:
    data = _load_yaml(CI_WORKFLOW)
    job = data["jobs"]["semgrep"]
    commands = "\n".join(
        step.get("run", "") for step in job.get("steps", []) if isinstance(step.get("run", ""), str)
    )

    assert f"semgrep=={SEMGREP_VERSION}" in commands
    assert "semgrep scan" in commands
    assert "--config .semgrep/project-guardrails.yml" in commands
    assert "--error" in commands
    assert "--metrics=off" in commands


def test_ci_semgrep_job_uses_read_only_permissions() -> None:
    data = _load_yaml(CI_WORKFLOW)
    assert data["permissions"] == {"contents": "read"}
    semgrep_job = data["jobs"]["semgrep"]
    assert semgrep_job.get("permissions") in (None, {"contents": "read"})
