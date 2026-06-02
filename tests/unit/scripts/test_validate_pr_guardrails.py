from __future__ import annotations

import json
from unittest.mock import patch

from scripts.ci.validate_pr_guardrails import (
    PullRequest,
    _pull_request_from_event,
    _refresh_pull_request_from_github,
    validate,
)


def _pr(title: str, body: str, labels: tuple[str, ...] = ()) -> PullRequest:
    return PullRequest(title=title, body=body, labels=labels)


def test_refresh_pull_request_from_github_uses_current_body_and_keeps_event_shas(
    monkeypatch,
) -> None:
    event = {
        "pull_request": {
            "url": "https://api.github.com/repos/acme/rag/pulls/123",
            "title": "fix: stale event",
            "body": "Fixes #123",
            "labels": [{"name": "bug"}],
            "base": {"sha": "base-sha"},
            "head": {"sha": "head-sha"},
        }
    }
    event_pr = _pull_request_from_event(event)
    assert event_pr is not None
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "title": "fix: stale event",
                    "body": (
                        "Fixes #123\n"
                        "Bug class: Observability trace-family coverage drift\n"
                        "Regression guardrail: tests/unit/test_validate_pr_guardrails.py\n"
                        "Checks run: pytest tests/unit/scripts/test_validate_pr_guardrails.py\n"
                    ),
                    "labels": [{"name": "bug"}, {"name": "observability"}],
                }
            ).encode()

    with patch("scripts.ci.validate_pr_guardrails.urllib.request.urlopen", return_value=Response()):
        refreshed = _refresh_pull_request_from_github(event, event_pr)

    assert refreshed is not None
    assert refreshed.body != event_pr.body
    assert "Regression guardrail:" in refreshed.body
    assert refreshed.labels == ("bug", "observability")
    assert refreshed.base_sha == "base-sha"
    assert refreshed.head_sha == "head-sha"


def test_bugfix_requires_regression_guardrail_checks_and_test_change() -> None:
    failures = validate(
        _pr("fix: repair retrieval regression", "Fixes #123"),
        ["telegram_bot/services/search.py"],
        large_threshold=25,
    )

    assert "bugfix PR must fill `Regression guardrail:` in the PR body" in failures
    assert "bugfix PR must fill `Checks run:` in the PR body" in failures
    assert "bugfix PR must change `tests/**` or include `No regression test:` reason" in failures


def test_bugfix_with_guardrail_and_test_change_passes() -> None:
    failures = validate(
        _pr(
            "fix: repair retrieval regression",
            "Fixes #123\n\n"
            "> Bug class: RAG quality regression\n"
            "> Regression guardrail: tests/contract/test_rag_contract.py\n"
            "> Checks run: uv run pytest tests/contract/test_rag_contract.py -q\n",
        ),
        ["telegram_bot/services/search.py", "tests/contract/test_rag_contract.py"],
        large_threshold=25,
    )

    assert failures == []


def test_bugfix_accepts_legacy_guardrail_alias_from_template_drift() -> None:
    """Older PR bodies that used `Guardrail:` must not fail the regression gate."""
    failures = validate(
        _pr(
            "fix: repair retrieval regression",
            "Fixes #123\n\n"
            "> Bug class: RAG quality regression\n"
            "> Guardrail: tests/contract/test_rag_contract.py\n"
            "> Checks run: uv run pytest tests/contract/test_rag_contract.py -q\n",
        ),
        ["telegram_bot/services/search.py", "tests/contract/test_rag_contract.py"],
        large_threshold=25,
    )

    assert failures == []


def test_bugfix_can_explain_no_regression_test() -> None:
    failures = validate(
        _pr(
            "fix: docs typo in issue link",
            "Fixes #123\n\n"
            "Regression guardrail: docs link check\n"
            "Checks run: python3 scripts/check_markdown_links.py\n"
            "No regression test: documentation-only correction\n",
        ),
        ["docs/engineering/README.md"],
        large_threshold=25,
    )

    assert failures == []


def test_dependency_change_requires_uv_lock() -> None:
    failures = validate(
        _pr("chore: add dependency", "Checks run: uv lock --locked"),
        ["pyproject.toml"],
        large_threshold=25,
    )

    assert "dependency changes must include `uv.lock`" in failures


def test_pyproject_tooling_change_does_not_require_uv_lock(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.ci.validate_pr_guardrails._pyproject_dependency_metadata_changed",
        lambda _base_sha, _head_sha: False,
    )

    failures = validate(
        _pr(
            "test: classify service dependency markers",
            "Regression guardrail: tests/contract/test_service_dependency_markers_contract.py\n"
            "Checks run: pytest service marker contract\n",
        ),
        ["pyproject.toml", "tests/contract/test_service_dependency_markers_contract.py"],
        large_threshold=25,
    )

    assert "dependency changes must include `uv.lock`" not in failures


def test_workflow_change_requires_policy_test() -> None:
    failures = validate(
        _pr("ci: update workflow", "Checks run: yaml lint"),
        [".github/workflows/ci.yml"],
        large_threshold=25,
    )

    assert (
        "compose/workflow changes must include workflow/compose policy tests or contract tests"
    ) in failures


def test_workflow_change_with_policy_test_passes() -> None:
    failures = validate(
        _pr("ci: update workflow", "Checks run: pytest policy tests"),
        [".github/workflows/ci.yml", "tests/unit/test_ci_workflow_guardrails.py"],
        large_threshold=25,
    )

    assert failures == []


def test_workflow_change_with_semgrep_policy_test_passes() -> None:
    failures = validate(
        _pr("ci: add semgrep workflow", "Checks run: pytest semgrep policy tests"),
        [".github/workflows/ci.yml", "tests/unit/test_semgrep_guardrails.py"],
        large_threshold=25,
    )

    assert failures == []


def test_workflow_change_with_trusted_heavy_policy_test_passes() -> None:
    failures = validate(
        _pr("ci: update trusted heavy workflow", "Checks run: pytest trusted-heavy policy tests"),
        [
            ".github/workflows/trusted-heavy.yml",
            "tests/unit/test_trusted_heavy_workflow.py",
        ],
        large_threshold=25,
    )

    assert failures == []


def test_compose_change_with_compose_runtime_policy_test_passes() -> None:
    failures = validate(
        _pr(
            "fix: repair compose runtime contract",
            "Regression guardrail: tests/unit/test_compose_runtime_contract.py\n"
            "Checks run: pytest compose policy tests",
        ),
        ["compose.yml", "tests/unit/test_compose_runtime_contract.py"],
        large_threshold=25,
    )

    assert failures == []


def test_duplicate_work_requires_bug_class() -> None:
    failures = validate(
        _pr("fix: duplicate Langfuse context loss", "Fixes #2302", labels=("bug",)),
        ["src/observability.py", "tests/contract/test_observability_contextvars_contract.py"],
        large_threshold=25,
    )

    assert "duplicate/bug-class PR must fill `Bug class:`" in failures


def test_duplicate_process_wording_without_disposition_does_not_require_bug_class() -> None:
    failures = validate(
        _pr(
            "ci: add project guardrail",
            "This keeps project-specific duplicate/root-cause logic in Python.",
        ),
        [".github/workflows/ci.yml", "tests/unit/test_semgrep_guardrails.py"],
        large_threshold=25,
    )

    assert "duplicate/bug-class PR must fill `Bug class:`" not in failures


def test_duplicate_disposition_type_requires_bug_class() -> None:
    failures = validate(
        _pr("docs: close issue cluster", "Type: duplicate\nBug class: ___________"),
        ["docs/engineering/issue-triage.md"],
        large_threshold=25,
    )

    assert "duplicate/bug-class PR must fill `Bug class:`" in failures


def test_duplicate_work_requires_registered_bug_class() -> None:
    failures = validate(
        _pr(
            "fix: duplicate unknown failure",
            "Fixes #2302\n\n"
            "Bug class: random local wording\n"
            "Regression guardrail: tests/contract/test_unknown.py\n"
            "Checks run: pytest tests/contract/test_unknown.py\n",
            labels=("bug",),
        ),
        ["src/observability.py", "tests/contract/test_unknown.py"],
        large_threshold=25,
    )

    assert (
        "Bug class `random local wording` is not registered in "
        ".github/bug-classes.yml; use an existing canonical "
        "class or update the registry"
    ) in failures


def test_duplicate_work_may_add_new_bug_class_registry_entry() -> None:
    failures = validate(
        _pr(
            "fix: duplicate unknown failure",
            "Fixes #2302\n\n"
            "Bug class: random local wording\n"
            "Regression guardrail: tests/contract/test_unknown.py\n"
            "Checks run: pytest tests/contract/test_unknown.py\n",
            labels=("bug",),
        ),
        [
            "src/observability.py",
            "tests/contract/test_unknown.py",
            ".github/bug-classes.yml",
        ],
        large_threshold=25,
    )

    assert failures == []


def test_large_pr_requires_plan_or_spec() -> None:
    files = [f"src/file_{idx}.py" for idx in range(25)]
    failures = validate(
        _pr("feat: broad migration", "Checks run: focused tests"),
        files,
        large_threshold=25,
    )

    assert "large PR (25 files) must include `Plan:` or `Spec:` in PR body" in failures
