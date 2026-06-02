"""Contract tests for project Semgrep guardrails."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SEMGREP_CONFIG = REPO_ROOT / ".semgrep" / "project-guardrails.yml"
SEMGREP_VERSION = "1.163.0"
NAIVE_UTC_RULE_PATHS = {
    "/scripts/**",
    "/src/**",
    "/telegram_bot/**",
    "/mini_app/**",
    "/services/**",
}

REQUIRED_RULE_IDS = {
    "python.no-datetime-utcnow",
    "python.no-instructor-from-provider",
    "python.no-langfuse-set-current-trace-io",
    "python.no-langfuse-prompts-api-get",
    "python.no-qdrant-client-search",
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


def _rule_by_id(rule_id: str) -> dict[str, Any]:
    data = _load_yaml(SEMGREP_CONFIG)
    rules = data.get("rules")
    assert isinstance(rules, list), ".semgrep/project-guardrails.yml must define rules"

    matches = [rule for rule in rules if isinstance(rule, dict) and rule.get("id") == rule_id]
    assert len(matches) == 1, f"Expected exactly one Semgrep rule for {rule_id}"
    return matches[0]


def test_naive_utc_semgrep_rule_preserves_deleted_ast_contract_scope() -> None:
    """The Semgrep replacement must keep the old naive-UTC contract coverage."""
    rule = _rule_by_id("python.no-datetime-utcnow")
    pattern_either = rule.get("pattern-either")
    assert isinstance(pattern_either, list)
    patterns = {entry.get("pattern") for entry in pattern_either if isinstance(entry, dict)}
    assert "$X.utcnow(...)" in patterns
    assert "$X.utcfromtimestamp(...)" in patterns

    paths = rule.get("paths")
    assert isinstance(paths, dict)
    include = paths.get("include")
    assert isinstance(include, list)
    assert set(include) >= NAIVE_UTC_RULE_PATHS


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
    assert "mini_app" in commands
    assert "services" in commands


def test_ci_semgrep_job_uses_read_only_permissions() -> None:
    data = _load_yaml(CI_WORKFLOW)
    permissions = data["permissions"]
    assert permissions["contents"] == "read"
    assert all(value == "read" for value in permissions.values())
    assert "actions" not in permissions
    assert "id-token" not in permissions
    semgrep_job = data["jobs"]["semgrep"]
    assert semgrep_job.get("permissions") in (None, {"contents": "read"})
