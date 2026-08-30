"""Contracts for the authoritative local quality-gate ladder."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml


REPO = Path(__file__).resolve().parents[2]

_HOSTED_TEST_COMMANDS = (
    ("pytest", re.compile(r"(?<![\w.-])pytest(?:\.exe)?\b", re.IGNORECASE)),
    (
        "Windows test preflight",
        re.compile(
            r"windows_preflight\.ps1\b[\s\S]*?-Mode\s+['\"]?(?:Tests|Full|Live)['\"]?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Make test target",
        re.compile(
            r"\b(?:g?make)(?:\.exe)?\b(?:(?![;&|\r\n]).)*?"
            r"(?<![-\w])(?:test(?:-[\w-]+)?|candidate-check|pre-push)(?![-\w])",
            re.IGNORECASE,
        ),
    ),
)


def _text(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


def _workflow_step_run(workflow: str, step_name: str) -> str:
    parsed = yaml.safe_load(workflow)
    jobs = parsed.get("jobs", {}) if isinstance(parsed, dict) else {}
    matches = [
        step
        for job in jobs.values()
        if isinstance(job, dict)
        for step in job.get("steps", [])
        if isinstance(step, dict) and step.get("name") == step_name
    ]
    assert len(matches) == 1, f"workflow must define exactly one {step_name!r} step"
    run = matches[0].get("run")
    assert isinstance(run, str), f"workflow step {step_name!r} must define a run command"
    return run.strip()


def _workflow_run_commands(workflow: str) -> tuple[str, ...]:
    parsed = yaml.safe_load(workflow)
    jobs = parsed.get("jobs", {}) if isinstance(parsed, dict) else {}
    return tuple(
        run.strip()
        for job in jobs.values()
        if isinstance(job, dict)
        for step in job.get("steps", [])
        if isinstance(step, dict)
        for run in (step.get("run"),)
        if isinstance(run, str)
    )


def _normalize_workflow_command(command: str) -> str:
    return re.sub(r"(?:\\|`|\^)\r?\n[ \t]*", "", command)


def _assert_no_hosted_test_commands(workflows: dict[str, str]) -> None:
    violations = [
        f"{path}: {label}: {command}"
        for path, workflow in workflows.items()
        for command in _workflow_run_commands(workflow)
        for normalized in (_normalize_workflow_command(command),)
        for label, pattern in _HOSTED_TEST_COMMANDS
        if pattern.search(normalized)
    ]
    assert not violations, "hosted workflows must not run local tests:\n" + "\n".join(violations)


def test_workflow_step_run_rejects_duplicate_with_intervening_keys() -> None:
    workflow = """
jobs:
  lint:
    steps:
      - name: Ruff lint
        run: pinned-command
      - name: Ruff lint
        shell: bash
        env:
          EXAMPLE: duplicate
        run: floating-command
"""

    with pytest.raises(AssertionError, match="exactly one 'Ruff lint' step"):
        _workflow_step_run(workflow, "Ruff lint")


@pytest.mark.parametrize(
    "command",
    (
        "uv run --no-sync pytest tests/unit/ -q",
        "python -m pytest tests/contract/",
        "pwsh -File scripts/windows_preflight.ps1 -Mode Tests",
        'pwsh -File scripts/windows_preflight.ps1 -Mode "Tests"',
        "pwsh -File scripts/windows_preflight.ps1 -Mode `\nTests",
        "pwsh -File scripts/windows_preflight.ps1 -Mode Full",
        "make test",
        "gmake test-core",
        "make -j 2 test-core",
        "make \\\ntest-contract",
        "make candidate-check",
        "make pre-push",
        "py\\\ntest tests/unit/ -q",
    ),
)
def test_hosted_test_command_contract_rejects_direct_and_wrapped_routes(command: str) -> None:
    command_block = command.replace("\n", "\n          ")
    workflow = f"""
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - name: Prohibited hosted test
        run: |-
          {command_block}
"""

    with pytest.raises(AssertionError, match="hosted workflows must not run local tests"):
        _assert_no_hosted_test_commands({".github/workflows/example.yml": workflow})


def test_hosted_test_command_contract_allows_static_commands() -> None:
    workflow = """
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - name: Ruff lint
        run: uvx --from ruff==0.15.20 ruff check src/
      - name: Windows static preflight
        run: pwsh -File scripts/windows_preflight.ps1 -Mode Static
"""

    _assert_no_hosted_test_commands({".github/workflows/example.yml": workflow})


def test_active_github_workflows_do_not_run_local_tests() -> None:
    workflow_paths = sorted(
        {
            *REPO.glob(".github/workflows/*.yml"),
            *REPO.glob(".github/workflows/*.yaml"),
        }
    )
    assert workflow_paths, "repository must define at least one active GitHub workflow"

    _assert_no_hosted_test_commands(
        {
            path.relative_to(REPO).as_posix(): path.read_text(encoding="utf-8")
            for path in workflow_paths
        }
    )


def test_makefile_local_gate_ladder() -> None:
    makefile = _text("Makefile")

    lint_paths = re.search(r"^LINT_PATHS\s*:=\s*(.+)$", makefile, re.MULTILINE)
    assert lint_paths
    assert "mini_app/" not in lint_paths.group(1)
    assert re.search(
        r"^dev-setup:\s+install-dev\s+setup-hooks\s+docker-up\b", makefile, re.MULTILINE
    )
    assert re.search(
        r"^candidate-check:\s+check-frozen\s+test\s+test-contract\b",
        makefile,
        re.MULTILINE,
    )
    assert re.search(r"^pre-push:\s+lint\s+format-check\s+test-core\b", makefile, re.MULTILINE)


def test_ci_ruff_paths_match_makefile_lint_paths() -> None:
    makefile = _text("Makefile")
    workflow = _text(".github/workflows/ci.yml")
    lockfile = tomllib.loads(_text("uv.lock"))

    lint_paths_match = re.search(r"^LINT_PATHS\s*:=\s*(.+)$", makefile, re.MULTILINE)
    assert lint_paths_match, "Makefile must define LINT_PATHS"
    lint_paths = lint_paths_match.group(1).strip()
    ruff_versions = [
        package["version"] for package in lockfile["package"] if package.get("name") == "ruff"
    ]
    assert len(ruff_versions) == 1, "uv.lock must contain exactly one Ruff package"
    ruff_command = f"uvx --from ruff=={ruff_versions[0]} ruff"

    assert _workflow_step_run(workflow, "Ruff lint") == (
        f"{ruff_command} check {lint_paths} --output-format=github"
    )
    assert _workflow_step_run(workflow, "Ruff format check") == (
        f"{ruff_command} format --target-version py312 --check {lint_paths}"
    )


def test_pre_push_core_hook_is_cross_platform_and_read_only() -> None:
    config = _text(".pre-commit-config.yaml")
    hook = re.search(
        r"^\s*- id: core-tests\b.*?(?=^\s*- id:|^\S|\Z)",
        config,
        re.MULTILINE | re.DOTALL,
    )
    assert hook, "pre-commit must define a local core-tests hook"
    block = hook.group(0)
    assert "language: system" in block
    assert re.search(r"entry:\s*>-\s+uv run --no-sync", block)
    assert "pytest" in block
    for selector in (
        "tests/unit/core/",
        "tests/unit/runtime/",
        "tests/regression/",
        "tests/characterization/",
        "tests/contract/test_runtime_no_telegram_bot_coupling_contract.py",
        "tests/contract/test_layering_no_telegram_bot_imports_contract.py",
    ):
        assert selector in block
    assert "pass_filenames: false" in block
    assert "always_run: true" in block
    assert "stages: [pre-push]" in block
    assert "make " not in block


def test_docs_define_candidate_check_as_delivery_gate() -> None:
    for path in (
        "AGENTS.md",
        "README.md",
        "CONTRIBUTING.md",
        "docs/LOCAL-DEVELOPMENT.md",
        "tests/README.md",
    ):
        text = _text(path)
        assert "candidate-check" in text, f"{path} must name candidate-check"
        assert "delivery" in text.lower(), f"{path} must identify the delivery gate"


def test_docs_keep_pytest_local_and_name_linux_portability_route() -> None:
    local_development = _text("docs/LOCAL-DEVELOPMENT.md")
    assert re.search(r"GitHub[^\n]*no pytest", local_development, re.IGNORECASE)
    assert "WSL" in local_development
    assert "container" in local_development.lower()
