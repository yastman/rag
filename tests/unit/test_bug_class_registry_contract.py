"""Contract locks for the canonical bug-class registry and guardrail standards.

The registry at ``docs/engineering/bug-classes.md`` is the single source of truth
for recurring bug classes. Every recurring bug discovered through issue triage or
regression must be registered there so future PRs can reference it.

These contract tests lock the registry shape, required bug classes, and guardrail
terminology so silent drift is caught at CI time.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_BUG_CLASSES = REPO_ROOT / "docs" / "engineering" / "bug-classes.md"

# Bug classes the registry must always cover (worker prompt contract).
REQUIRED_BUG_CLASSES = {
    "Langfuse/OTEL/contextvars loss",
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


def test_bug_classes_doc_exists() -> None:
    """The canonical bug-class registry must exist."""
    assert DOC_BUG_CLASSES.exists(), (
        "docs/engineering/bug-classes.md is missing; create the canonical "
        "bug-class registry per the anti-regression guardrails worker contract."
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
    """The seeded bug classes must all appear in the registry."""
    text = DOC_BUG_CLASSES.read_text(encoding="utf-8")
    assert bug_class in text, (
        f"docs/engineering/bug-classes.md must register '{bug_class}'; "
        "this bug class is part of the seeded registry contract."
    )


def test_registry_table_has_issue_column() -> None:
    """The registry table must have a column for issue provenance."""
    text = DOC_BUG_CLASSES.read_text(encoding="utf-8")
    assert "Canonical Issue" in text or "Issues" in text, (
        "docs/engineering/bug-classes.md registry table must include a "
        "'Canonical Issue' or 'Issues' column for concrete issue provenance."
    )


# ------------- Issue provenance for duplicated classes ---------------------------


@pytest.mark.parametrize(
    "bug_class, min_issue_refs",
    [
        ("Langfuse/OTEL/contextvars loss", ["#2301", "#2302", "#2246"]),
        ("uv .venv mutation", ["#2285", "#2289", "#2296"]),
        ("Docker/compose drift", ["#2123", "#2185", "#2188"]),
        ("Testing hygiene/tautological assertions", ["#1515", "#1539", "#1944"]),
    ],
)
def test_registry_includes_concrete_issue_refs(bug_class: str, min_issue_refs: list[str]) -> None:
    """Each recurrent bug class must cite concrete issue references from intake."""
    text = DOC_BUG_CLASSES.read_text(encoding="utf-8")
    missing = [ref for ref in min_issue_refs if ref not in text]
    assert not missing, (
        f"Bug class '{bug_class}' in docs/engineering/bug-classes.md "
        f"is missing concrete issue references: {missing}. "
        "Every recurrent bug class must cite real issue numbers."
    )


def test_rag_quality_regression_marked_preventive() -> None:
    """RAG quality regression has no duplicate cluster; must be marked preventive."""
    text = DOC_BUG_CLASSES.read_text(encoding="utf-8")
    assert "preventive" in text.lower() or "backlog" in text.lower(), (
        "docs/engineering/bug-classes.md must mark RAG quality regression "
        "as 'preventive/backlog' since no concrete duplicate cluster exists."
    )
    assert "RAG quality regression" in text


# ------------- Testing hygiene guardrail factuality ---------------------------------


def test_testing_hygiene_guardrail_refers_to_factual_contract() -> None:
    """Testing hygiene guardrail must cite the actual ingestion assertion contract.

    The registry must not claim a global ``assert True`` denylist unless
    one exists and is proven. Instead it must reference the existing factual
    guardrails: ``tests/contract/test_ingestion_e2e_assertions_contract.py``
    and ``docs/engineering/test-writing-guide.md``.
    """
    text = DOC_BUG_CLASSES.read_text(encoding="utf-8")
    assert "test_ingestion_e2e_assertions_contract.py" in text, (
        "docs/engineering/bug-classes.md Testing hygiene guardrail must "
        "reference tests/contract/test_ingestion_e2e_assertions_contract.py"
    )
    assert "test-writing-guide.md" in text, (
        "docs/engineering/bug-classes.md Testing hygiene guardrail must "
        "reference docs/engineering/test-writing-guide.md"
    )


def test_observability_guardrail_refers_to_contextvars_contract() -> None:
    """Observability bug class must cite the context propagation contract test."""
    text = DOC_BUG_CLASSES.read_text(encoding="utf-8")
    assert "test_observability_contextvars_contract.py" in text, (
        "docs/engineering/bug-classes.md Langfuse/OTEL/contextvars row must "
        "reference tests/contract/test_observability_contextvars_contract.py"
    )


# ------------- Guardrail terminology --------------------------------------------


@pytest.mark.parametrize("term", GUARDRAIL_TERMS)
def test_registry_defines_guardrail_term(term: str) -> None:
    """Core guardrail terms must be present in the standards section."""
    text = DOC_BUG_CLASSES.read_text(encoding="utf-8")
    assert term in text, (
        f"docs/engineering/bug-classes.md must define or reference '{term}' "
        "in the guardrail standards contract."
    )


# ------------- PR template guardrail fields --------------------------------------


def test_pr_template_has_bug_class_field() -> None:
    """The PR template must include a 'Bug class' field for registry reference."""
    pr_template = REPO_ROOT / ".github" / "pull_request_template.md"
    text = pr_template.read_text(encoding="utf-8")
    assert "Bug class" in text, (
        ".github/pull_request_template.md must include a 'Bug class' field "
        "so contributors can reference the canonical bug-class registry."
    )


def test_pr_template_has_regression_guardrail_field() -> None:
    """The PR template must include a 'Regression guardrail' field."""
    pr_template = REPO_ROOT / ".github" / "pull_request_template.md"
    text = pr_template.read_text(encoding="utf-8")
    assert "Regression guardrail" in text, (
        ".github/pull_request_template.md must include a 'Regression guardrail' "
        "field so contributors document which guardrail their fix enforces."
    )


def test_pr_template_has_checks_run_field() -> None:
    """The PR template must include a 'Checks run' field."""
    pr_template = REPO_ROOT / ".github" / "pull_request_template.md"
    text = pr_template.read_text(encoding="utf-8")
    assert "Checks run" in text, (
        ".github/pull_request_template.md must include a 'Checks run' field "
        "so contributors document their validation ladder."
    )
