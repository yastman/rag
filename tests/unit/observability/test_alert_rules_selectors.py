"""Tests for alert rule selectors - ensure stable {service=...} patterns."""

import re
from pathlib import Path

import pytest
import yaml


RULES_DIR = Path("docker/monitoring/rules")


def _load_all_rules() -> list[dict]:
    """Load all alert rules from YAML files in the rules directory."""
    rules = []
    for yaml_file in sorted(RULES_DIR.glob("*.yaml")):
        content = yaml.safe_load(yaml_file.read_text())
        if not content or "groups" not in content:
            continue
        for group in content["groups"]:
            for rule in group.get("rules", []):
                if "expr" in rule:
                    rules.append(
                        {
                            "file": yaml_file.name,
                            "alert": rule.get("alert", "unknown"),
                            "expr": rule["expr"],
                        }
                    )
    return rules


@pytest.fixture()
def all_rules() -> list[dict]:
    """Fixture providing all parsed alert rules."""
    return _load_all_rules()


def test_no_alert_rules_use_dev_container_selectors(all_rules: list[dict]) -> None:
    """No alert rule expr should contain container='dev-' pattern."""
    violations = []
    pattern = re.compile(r'container\s*[=~]+\s*"dev-')
    for rule in all_rules:
        if pattern.search(rule["expr"]):
            violations.append(f"{rule['file']}:{rule['alert']}")
    assert not violations, (
        f"Found {len(violations)} alert(s) still using container='dev-*' selectors: "
        + ", ".join(violations)
    )


def test_all_alert_rules_use_service_selectors(all_rules: list[dict]) -> None:
    """All alert exprs with log stream selectors should use service-based selectors."""
    # Match LogQL stream selectors: { ... = ... } (must contain at least one = sign)
    stream_selector_pattern = re.compile(r"\{[^}]*=[^}]+\}")
    service_pattern = re.compile(r"(service\s*[=~]+|compose_project\s*[=~]+)")

    violations = []
    for rule in all_rules:
        selectors = stream_selector_pattern.findall(rule["expr"])
        for selector in selectors:
            if not service_pattern.search(selector):
                violations.append(f"{rule['file']}:{rule['alert']} -> {selector}")
    assert not violations, (
        f"Found {len(violations)} selector(s) without service-based labels: "
        + ", ".join(violations)
    )
