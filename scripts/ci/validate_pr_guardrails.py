#!/usr/bin/env python3
"""Validate PR-level anti-regression guardrails.

This check is intentionally metadata/diff based. It catches missing guardrail
evidence before review and does not depend on agents reading AGENTS.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BUGFIX_RE = re.compile(r"\b(fix|bug|bugfix|regression|hotfix)\b", re.IGNORECASE)
FIXES_RE = re.compile(r"\b(fixes|closes|resolves)\s+#\d+\b", re.IGNORECASE)
DUPLICATE_RE = re.compile(r"\b(duplicate|duplicates|dup)\b", re.IGNORECASE)

DEPENDENCY_FILES = {
    "pyproject.toml",
    "uv.lock",
    "requirements.txt",
    "requirements-dev.txt",
}

WORKFLOW_POLICY_TESTS = {
    "tests/unit/test_ci_workflow_guardrails.py",
    "tests/unit/test_ci_deploy_workflow.py",
    "tests/unit/test_codeowners_contract.py",
}

BUG_CLASS_REGISTRY = Path("docs/engineering/bug-classes.md")


@dataclass(frozen=True)
class PullRequest:
    title: str
    body: str
    labels: tuple[str, ...]
    base_sha: str | None = None
    head_sha: str | None = None


def _load_event(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _pull_request_from_event(event: dict[str, Any]) -> PullRequest | None:
    raw_pr = event.get("pull_request")
    if not isinstance(raw_pr, dict):
        return None
    labels = tuple(
        label.get("name", "") for label in raw_pr.get("labels", []) if isinstance(label, dict)
    )
    base = raw_pr.get("base") if isinstance(raw_pr.get("base"), dict) else {}
    head = raw_pr.get("head") if isinstance(raw_pr.get("head"), dict) else {}
    return PullRequest(
        title=str(raw_pr.get("title") or ""),
        body=str(raw_pr.get("body") or ""),
        labels=labels,
        base_sha=base.get("sha"),
        head_sha=head.get("sha"),
    )


def _changed_files_from_env(value: str | None) -> list[str]:
    if not value:
        return []
    files: list[str] = []
    for line in value.replace(",", "\n").splitlines():
        item = line.strip()
        if item:
            files.append(item)
    return sorted(set(files))


def _changed_files_from_git(base_sha: str | None, head_sha: str | None) -> list[str]:
    if not base_sha:
        return []
    end = head_sha or "HEAD"
    cmd = ["git", "diff", "--name-only", f"{base_sha}..{end}"]
    result = subprocess.run(  # nosec B603
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def _changed_files(args: argparse.Namespace, pr: PullRequest | None) -> list[str]:
    from_arg = _changed_files_from_env(args.changed_files)
    if from_arg:
        return from_arg
    from_env = _changed_files_from_env(os.environ.get("PR_GUARDRAILS_CHANGED_FILES"))
    if from_env:
        return from_env
    if pr is not None:
        from_git = _changed_files_from_git(pr.base_sha, pr.head_sha)
        if from_git:
            return from_git
    return []


def _is_bugfix(pr: PullRequest) -> bool:
    haystack = " ".join((pr.title, pr.body, " ".join(pr.labels)))
    return bool(BUGFIX_RE.search(haystack) or FIXES_RE.search(haystack))


def _is_duplicate_or_bug_class(pr: PullRequest) -> bool:
    haystack = " ".join((pr.title, pr.body, " ".join(pr.labels)))
    return bool(DUPLICATE_RE.search(haystack) or "Bug class:" in pr.body)


def _has_filled_field(body: str, field: str) -> bool:
    pattern = re.compile(rf"(?im)^\s*>?\s*{re.escape(field)}\s*:\s*(.+)$")
    match = pattern.search(body)
    if match is None:
        return False
    value = match.group(1).strip()
    return bool(value and value not in {"-", "n/a", "N/A", "none", "None"})


def _has_filled_any_field(body: str, fields: tuple[str, ...]) -> bool:
    return any(_has_filled_field(body, field) for field in fields)


def _field_value(body: str, field: str) -> str | None:
    pattern = re.compile(rf"(?im)^\s*>?\s*{re.escape(field)}\s*:\s*(.+)$")
    match = pattern.search(body)
    if match is None:
        return None
    value = match.group(1).strip()
    if not value or value in {"-", "n/a", "N/A", "none", "None"}:
        return None
    return value


def _registered_bug_classes(path: Path = BUG_CLASS_REGISTRY) -> set[str]:
    if not path.exists():
        return set()

    classes: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith(("| Bug Class", "|---")):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells:
            classes.add(cells[0])
    return classes


def _has_no_test_reason(body: str) -> bool:
    return _has_filled_field(body, "No regression test")


def _has_test_change(files: list[str]) -> bool:
    return any(path.startswith("tests/") for path in files)


def _has_dependency_change(files: list[str]) -> bool:
    return any(path in DEPENDENCY_FILES for path in files)


def _has_lockfile_change(files: list[str]) -> bool:
    return "uv.lock" in files


def _is_compose_file(path: str) -> bool:
    name = Path(path).name
    return name == "compose.yml" or (name.startswith("compose.") and name.endswith(".yml"))


def _has_compose_or_workflow_change(files: list[str]) -> bool:
    return any(_is_compose_file(path) or path.startswith(".github/workflows/") for path in files)


def _has_policy_test_change(files: list[str]) -> bool:
    changed = set(files)
    return bool(changed & WORKFLOW_POLICY_TESTS) or any(
        path.startswith("tests/contract/") for path in files
    )


def _has_large_change(files: list[str], threshold: int) -> bool:
    return len(files) >= threshold


def validate(pr: PullRequest | None, files: list[str], *, large_threshold: int) -> list[str]:
    failures: list[str] = []
    if pr is None:
        return failures

    bugfix = _is_bugfix(pr)
    if bugfix:
        if not _has_filled_any_field(pr.body, ("Regression guardrail", "Guardrail")):
            failures.append("bugfix PR must fill `Regression guardrail:` in the PR body")
        if not _has_filled_field(pr.body, "Checks run"):
            failures.append("bugfix PR must fill `Checks run:` in the PR body")
        if not _has_test_change(files) and not _has_no_test_reason(pr.body):
            failures.append(
                "bugfix PR must change `tests/**` or include `No regression test:` reason"
            )

    if _is_duplicate_or_bug_class(pr):
        bug_class = _field_value(pr.body, "Bug class")
        if bug_class is None:
            failures.append("duplicate/bug-class PR must fill `Bug class:`")
        elif "docs/engineering/bug-classes.md" not in files:
            registered = _registered_bug_classes()
            if registered and bug_class not in registered:
                failures.append(
                    f"Bug class `{bug_class}` is not registered in "
                    "docs/engineering/bug-classes.md; use an existing canonical "
                    "class or update the registry"
                )

    if _has_dependency_change(files) and not _has_lockfile_change(files):
        failures.append("dependency changes must include `uv.lock`")

    if _has_compose_or_workflow_change(files) and not _has_policy_test_change(files):
        failures.append(
            "compose/workflow changes must include workflow/compose policy tests or contract tests"
        )

    if _has_large_change(files, large_threshold) and not (
        _has_filled_field(pr.body, "Plan") or _has_filled_field(pr.body, "Spec")
    ):
        failures.append(f"large PR ({len(files)} files) must include `Plan:` or `Spec:` in PR body")

    return failures


def main(argv: list[str] | None = None) -> int:
    default_event_path = os.environ.get("GITHUB_EVENT_PATH")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--event-path",
        type=Path,
        default=Path(default_event_path) if default_event_path else None,
    )
    parser.add_argument("--changed-files", default=None)
    parser.add_argument("--large-threshold", type=int, default=25)
    args = parser.parse_args(argv)

    event = _load_event(args.event_path)
    pr = _pull_request_from_event(event)
    files = _changed_files(args, pr)
    failures = validate(pr, files, large_threshold=args.large_threshold)

    if pr is None:
        print("No pull_request payload found; PR guardrails skipped for this event.")
        return 0
    if not files:
        print("No changed-file list available; diff-based PR guardrails skipped.")

    if failures:
        print("PR guardrails failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("PR guardrails passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
