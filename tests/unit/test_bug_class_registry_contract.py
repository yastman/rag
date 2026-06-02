"""Contract locks for the YAML bug-class registry and guardrail standards.

The registry at ``.github/bug-classes.yml`` is the machine-readable source of
truth for recurring bug classes. ``docs/engineering/bug-classes.md`` is the
human-readable mirror. Every recurring bug discovered through issue triage or
regression must be registered in YAML so future PRs can reference it.

These contract tests lock the registry shape, required bug classes, and guardrail
terminology so silent drift is caught at CI time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
YAML_BUG_CLASSES = REPO_ROOT / ".github" / "bug-classes.yml"
DOC_BUG_CLASSES = REPO_ROOT / "docs" / "engineering" / "bug-classes.md"

# Bug classes the registry must always cover (worker prompt contract).
REQUIRED_BUG_CLASSES = {
    "Langfuse/OTEL/contextvars loss",
    "Observability trace-coverage drift",
    "uv .venv mutation",
    "Docker/compose drift",
    "RAG quality regression",
    "Testing hygiene/tautological assertions",
}

# Guardrail definitions that must appear in the standards section.
GUARDRAIL_TERMS = [
    "Regression-driven TDD",
    "guardrail",
    "quality gate",
    "guardrails",
    "permanent",
    "Every recurring bug must become a permanent guardrail",
]


# ------------- Existence and shape ------------------------------------------------


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


def _class_names() -> set[str]:
    names = {str(item.get("name", "")) for item in _bug_classes()}
    assert "" not in names, "every bug_classes entry must include a non-empty `name`."
    return names


def _entry(name: str) -> dict[str, Any]:
    for item in _bug_classes():
        if item.get("name") == name:
            return item
    raise AssertionError(f"missing bug class {name!r}")


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(v) for v in value)
    return str(value)


def test_bug_classes_yaml_exists() -> None:
    """The canonical machine-readable bug-class registry must exist."""
    assert YAML_BUG_CLASSES.exists(), (
        ".github/bug-classes.yml is missing; create the canonical machine-readable "
        "bug-class registry."
    )
    assert YAML_BUG_CLASSES.stat().st_size > 0, ".github/bug-classes.yml exists but is empty."


def test_bug_classes_yaml_has_required_shape() -> None:
    """The YAML registry must carry standards and registered classes."""
    data = _load_registry()
    assert data.get("version"), ".github/bug-classes.yml must include a version."
    assert isinstance(data.get("guardrail_standards"), dict), (
        ".github/bug-classes.yml must define `guardrail_standards`."
    )
    for item in _bug_classes():
        for field in (
            "name",
            "guardrail",
            "canonical_issue",
            "related_issues",
            "first_seen",
            "last_confirmed",
        ):
            assert field in item, f"bug class {item.get('name')!r} missing `{field}`."


def test_bug_classes_doc_exists() -> None:
    """The human-readable bug-class mirror must exist."""
    assert DOC_BUG_CLASSES.exists(), (
        "docs/engineering/bug-classes.md is missing; create the human-readable "
        "mirror of .github/bug-classes.yml."
    )
    assert DOC_BUG_CLASSES.stat().st_size > 0, (
        "docs/engineering/bug-classes.md exists but is empty."
    )


def test_bug_classes_doc_has_purpose_header() -> None:
    """The registry must declare its purpose explicitly."""
    text = DOC_BUG_CLASSES.read_text(encoding="utf-8")
    assert "## Purpose" in text, "docs/engineering/bug-classes.md is missing a ## Purpose section."


def test_bug_classes_doc_has_registry_table() -> None:
    """The registry must contain a table of registered bug classes."""
    text = DOC_BUG_CLASSES.read_text(encoding="utf-8")
    assert "Bug Class" in text, (
        "docs/engineering/bug-classes.md must contain a table with a 'Bug Class' column header."
    )
    assert "Guardrail" in text, (
        "docs/engineering/bug-classes.md must contain a table with a "
        "'Guardrail' column header linking each class to its permanent rule."
    )


def test_bug_classes_doc_has_guardrail_standards_section() -> None:
    """The registry must define the guardrail standards vocabulary."""
    text = DOC_BUG_CLASSES.read_text(encoding="utf-8")
    assert "## Guardrail Standards" in text, (
        "docs/engineering/bug-classes.md is missing a ## Guardrail Standards section."
    )


# ------------- Required bug classes ----------------------------------------------


@pytest.mark.parametrize(
    "bug_class",
    sorted(REQUIRED_BUG_CLASSES),
)
def test_registry_covers_every_required_bug_class(bug_class: str) -> None:
    """The seeded bug classes must all appear in the YAML registry."""
    assert bug_class in _class_names(), (
        f".github/bug-classes.yml must register '{bug_class}'; "
        "this bug class is part of the seeded registry contract."
    )


def test_registry_table_has_issue_column() -> None:
    """Every YAML entry must preserve concrete issue provenance."""
    for item in _bug_classes():
        assert "canonical_issue" in item, f"{item['name']} missing canonical issue provenance."


# ------------- Issue provenance for duplicated classes ---------------------------


@pytest.mark.parametrize(
    "bug_class, min_issue_refs",
    [
        ("Langfuse/OTEL/contextvars loss", ["#2246", "#2251", "#2301"]),
        ("Observability trace-coverage drift", ["#2215", "#2246", "#2256"]),
        ("uv .venv mutation", ["#2285", "#2289", "#2296"]),
        ("Docker/compose drift", ["#2123", "#2185", "#2188"]),
        ("Testing hygiene/tautological assertions", ["#1515", "#1539", "#1944"]),
    ],
)
def test_registry_includes_concrete_issue_refs(bug_class: str, min_issue_refs: list[str]) -> None:
    """Each recurrent bug class must cite concrete issue references from intake."""
    text = _flatten_text(_entry(bug_class))
    missing = [ref for ref in min_issue_refs if ref not in text]
    assert not missing, (
        f"Bug class '{bug_class}' in .github/bug-classes.yml "
        f"is missing concrete issue references: {missing}. "
        "Every recurrent bug class must cite real issue numbers."
    )


def test_rag_quality_regression_marked_preventive() -> None:
    """RAG quality regression has no duplicate cluster; must be marked preventive."""
    text = _flatten_text(_entry("RAG quality regression"))
    assert "preventive" in text.lower() or "backlog" in text.lower(), (
        ".github/bug-classes.yml must mark RAG quality regression "
        "as 'preventive/backlog' since no concrete duplicate cluster exists."
    )


# ------------- Testing hygiene guardrail factuality ---------------------------------


def test_testing_hygiene_guardrail_refers_to_factual_contract() -> None:
    """Testing hygiene guardrail must cite the actual ingestion assertion contract.

    The registry must not claim a global ``assert True`` denylist unless
    one exists and is proven. Instead it must reference the existing factual
    guardrails: ``tests/contract/test_ingestion_e2e_assertions_contract.py``
    and ``docs/engineering/test-writing-guide.md``.
    """
    text = _flatten_text(_entry("Testing hygiene/tautological assertions"))
    assert "test_ingestion_e2e_assertions_contract.py" in text, (
        ".github/bug-classes.yml Testing hygiene guardrail must "
        "reference tests/contract/test_ingestion_e2e_assertions_contract.py"
    )
    assert "test-writing-guide.md" in text, (
        ".github/bug-classes.yml Testing hygiene guardrail must "
        "reference docs/engineering/test-writing-guide.md"
    )


def test_observability_guardrail_refers_to_contextvars_contract() -> None:
    """Observability bug class must cite the context propagation contract test."""
    text = _flatten_text(_entry("Langfuse/OTEL/contextvars loss"))
    assert "test_observability_contextvars_contract.py" in text, (
        ".github/bug-classes.yml Langfuse/OTEL/contextvars row must "
        "reference tests/contract/test_observability_contextvars_contract.py"
    )


def test_uv_venv_mutation_guardrail_refers_to_review_safe_gates() -> None:
    """uv mutation guardrail must cite the actual no-sync review gates.

    The #2296 guardrail protects review/candidate workflows through
    ``check-frozen`` / ``candidate-check`` and ``UV_RUN_NO_SYNC``. The registry
    must not over-claim that every developer-friendly ``make check`` invocation
    is no-sync.
    """
    text = _flatten_text(_entry("uv .venv mutation"))
    assert "check-frozen" in text, (
        ".github/bug-classes.yml uv .venv mutation row must reference the check-frozen review gate."
    )
    assert "candidate-check" in text, (
        ".github/bug-classes.yml uv .venv mutation row must reference "
        "the candidate-check review gate."
    )
    assert "test_makefile_review_gate_no_autosync_contract.py" in text, (
        ".github/bug-classes.yml uv .venv mutation row must reference "
        "tests/contract/test_makefile_review_gate_no_autosync_contract.py."
    )
    assert "UV_RUN_NO_SYNC" in text, (
        ".github/bug-classes.yml uv .venv mutation row must cite "
        "UV_RUN_NO_SYNC / uv run --no-sync as the no-mutation mechanism."
    )


# ------------- Guardrail terminology --------------------------------------------


@pytest.mark.parametrize("term", GUARDRAIL_TERMS)
def test_registry_defines_guardrail_term(term: str) -> None:
    """Core guardrail terms must be present in the standards section."""
    text = _flatten_text(_load_registry().get("guardrail_standards", {}))
    assert term in text, (
        f".github/bug-classes.yml must define or reference '{term}' "
        "in the guardrail standards contract."
    )


def test_bug_classes_doc_mirrors_yaml_class_names() -> None:
    """The Markdown mirror must include every YAML bug class name."""
    text = DOC_BUG_CLASSES.read_text(encoding="utf-8")
    missing = sorted(name for name in _class_names() if name not in text)
    assert not missing, (
        "docs/engineering/bug-classes.md must mirror every YAML bug class name: "
        + ", ".join(missing)
    )


# ------------- PR template guardrail fields --------------------------------------


def test_pr_template_has_bug_class_field() -> None:
    """The PR template must include a 'Bug class' field for registry reference."""
    pr_template = REPO_ROOT / ".github" / "pull_request_template.md"
    text = pr_template.read_text(encoding="utf-8")
    assert "Bug class" in text, (
        ".github/pull_request_template.md must include a 'Bug class' field "
        "so contributors can reference the canonical YAML bug-class registry."
    )


def test_pr_template_has_regression_guardrail_field() -> None:
    """The PR template must include a 'Regression guardrail' field."""
    pr_template = REPO_ROOT / ".github" / "pull_request_template.md"
    text = pr_template.read_text(encoding="utf-8")
    assert "Regression guardrail:" in text, (
        ".github/pull_request_template.md must include a 'Regression guardrail' "
        "field in the same literal format enforced by validate_pr_guardrails.py."
    )


def test_pr_template_has_checks_run_field() -> None:
    """The PR template must include a 'Checks run' field."""
    pr_template = REPO_ROOT / ".github" / "pull_request_template.md"
    text = pr_template.read_text(encoding="utf-8")
    assert "Checks run" in text, (
        ".github/pull_request_template.md must include a 'Checks run' field "
        "so contributors document their validation ladder."
    )


def test_pr_template_has_duplicate_disposition_fields() -> None:
    """The PR template must capture duplicate/recurrence closure metadata."""
    pr_template = REPO_ROOT / ".github" / "pull_request_template.md"
    text = pr_template.read_text(encoding="utf-8")
    for field in (
        "Duplicate / Recurring Issue Handling",
        "Canonical issue:",
        "Related issues to close/update:",
        "Closing comment summary:",
    ):
        assert field in text, (
            ".github/pull_request_template.md must keep duplicate/recurrence "
            f"metadata field {field!r} so issue disposition is not lost."
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
