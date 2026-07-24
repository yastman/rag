"""Contract locks for the YAML bug-class registry.

The registry at ``.github/bug-classes.yml`` is the machine-readable source of
truth for recurring bug classes. These contract tests lock the registry shape
and lightweight PR/issue template fields so silent drift is caught at CI time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
YAML_BUG_CLASSES = REPO_ROOT / ".github" / "bug-classes.yml"

# Guardrail definitions that must not reappear as active registry entries.
OBSOLETE_OBSERVABILITY_BUG_CLASSES = {
    "Langfuse/OTEL/contextvars loss",
    "Observability trace-coverage drift",
}


def _load_registry() -> dict[str, Any]:
    assert YAML_BUG_CLASSES.exists(), (
        ".github/bug-classes.yml is missing; create the canonical machine-readable "
        "bug-class registry."
    )
    data = yaml.safe_load(YAML_BUG_CLASSES.read_text(encoding="utf-8"))
    assert isinstance(data, dict), ".github/bug-classes.yml must contain a YAML mapping."
    return data


def _bug_classes() -> list[dict[str, Any]]:
    data = _load_registry()
    classes = data.get("bug_classes")
    assert isinstance(classes, list) and classes, (
        ".github/bug-classes.yml must define a non-empty `bug_classes` list."
    )
    for item in classes:
        assert isinstance(item, dict), "each bug_classes entry must be a mapping."
    return classes


def _class_ids() -> set[str]:
    ids = {str(item.get("id", "")) for item in _bug_classes()}
    assert "" not in ids, "every bug_classes entry must include a non-empty `id`."
    return ids


def test_bug_classes_yaml_exists() -> None:
    """The canonical machine-readable bug-class registry must exist."""
    assert YAML_BUG_CLASSES.exists(), (
        ".github/bug-classes.yml is missing; create the canonical machine-readable "
        "bug-class registry."
    )
    assert YAML_BUG_CLASSES.stat().st_size > 0, ".github/bug-classes.yml exists but is empty."


def test_bug_classes_yaml_has_required_shape() -> None:
    """The YAML registry must carry registered classes with required fields."""
    for item in _bug_classes():
        for field in ("id", "description", "canonical_issue", "guardrail"):
            assert field in item, f"bug class {item.get('id')!r} missing `{field}`."


def test_registry_table_has_issue_column() -> None:
    """Every YAML entry must preserve concrete issue provenance."""
    for item in _bug_classes():
        assert "canonical_issue" in item, f"{item.get('id')} missing canonical issue provenance."
        assert str(item["canonical_issue"]).strip(), (
            f"{item.get('id')} has empty canonical_issue provenance."
        )


def test_obsolete_observability_bug_classes_are_removed() -> None:
    """DEPS-13 removes Langfuse/OTel bug classes from the active registry."""
    names_and_ids = _class_ids()
    flattened = " ".join(
        f"{item.get('id', '')} {item.get('description', '')}" for item in _bug_classes()
    )
    for bug_class in OBSOLETE_OBSERVABILITY_BUG_CLASSES:
        assert bug_class not in names_and_ids
        assert bug_class not in flattened


def test_pr_template_has_validation_and_runtime_fields() -> None:
    """The PR template stays lightweight but still asks for checks and runtime impact."""
    pr_template = REPO_ROOT / ".github" / "pull_request_template.md"
    text = pr_template.read_text(encoding="utf-8")
    for field in ("Checks run", "Runtime Impact", "Reviewer Notes"):
        assert field in text, (
            f".github/pull_request_template.md must keep lightweight reviewer field {field!r}."
        )


def test_bug_issue_template_collects_duplicate_and_bug_class_metadata() -> None:
    """Bug reports must collect enough metadata for duplicate/recurrence triage."""
    issue_template = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml"
    text = issue_template.read_text(encoding="utf-8")
    for field in (
        "id: issue_kind",
        "id: possible_duplicates",
        "id: suspected_bug_class",
    ):
        assert field in text, (
            ".github/ISSUE_TEMPLATE/bug_report.yml must include duplicate and "
            f"bug-class triage field {field!r}."
        )
