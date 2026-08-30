"""Contracts for the authoritative local quality-gate ladder."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


def _workflow_step_run(workflow: str, step_name: str) -> str:
    matches = re.findall(
        rf"^[ \t]+- name: {re.escape(step_name)}[ \t]*\n[ \t]+run:[ \t]+(.+)$",
        workflow,
        re.MULTILINE,
    )
    assert len(matches) == 1, f"workflow must define exactly one {step_name!r} step"
    return matches[0].strip()


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
