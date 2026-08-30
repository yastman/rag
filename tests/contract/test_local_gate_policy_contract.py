"""Contracts for the authoritative local quality-gate ladder."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml


REPO = Path(__file__).resolve().parents[2]

_ALLOWED_HOSTED_ACTIONS = {
    "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd",
    "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b",
    "docker/build-push-action@f9f3042f7e2789586610d6e8b85c8f03e5195baf",
    "docker/login-action@650006c6eb7dba73a995cc03b0b2d7f5ca915bee",
    "docker/metadata-action@80c7e94dd9b9319bd5eb7a0e0fe9291e23a2a2e9",
    "docker/setup-buildx-action@d7f5e7f509e45cec5c76c4d5afdd7de93d0b3df5",
    "github/codeql-action/analyze@7211b7c8077ea37d8641b6271f6a365a22a5fbfa",
    "github/codeql-action/init@7211b7c8077ea37d8641b6271f6a365a22a5fbfa",
    "gitleaks/gitleaks-action@ff98106e4c7b2bc287b24eaf42907196329070c7",
}
_APPROVED_HOSTED_RUNS = {
    (".github/workflows/ci.yml", "semgrep", "Run project Semgrep guardrails"): (
        "uvx --from semgrep==1.163.0 semgrep scan "
        "--config .semgrep/project-guardrails.yml --error --metrics=off "
        "src telegram_bot scripts services .github/workflows compose.yml compose.dev.yml"
    ),
    (".github/workflows/ci.yml", "lint", "Ruff lint"): (
        "uvx --from ruff==0.15.20 ruff check "
        "src/ telegram_bot/ services/ scripts/ --output-format=github"
    ),
    (".github/workflows/ci.yml", "lint", "Ruff format check"): (
        "uvx --from ruff==0.15.20 ruff format --target-version py312 --check "
        "src/ telegram_bot/ services/ scripts/"
    ),
    (".github/workflows/ci.yml", "actionlint", "Install development tools"): (
        "uv sync --frozen --group dev"
    ),
    (".github/workflows/ci.yml", "actionlint", "Validate GitHub Actions workflows"): (
        "uv run --frozen pre-commit run actionlint --all-files --hook-stage pre-push"
    ),
    (".github/workflows/ci.yml", "uv-lock", "Verify lockfile integrity"): "uv lock --locked",
    (".github/workflows/ci.yml", "compose-config", "Validate Compose config"): (
        "docker compose --env-file tests/fixtures/compose.ci.env "
        "-f compose.yml -f compose.dev.yml config --quiet"
    ),
    (".github/workflows/ci.yml", "cve-scan", "Set up Python"): "uv python install 3.12",
    (".github/workflows/ci.yml", "cve-scan", "Install dependencies"): "uv sync --frozen",
    (
        ".github/workflows/ci.yml",
        "cve-scan",
        "Refresh OSV advisory cache (audit-deps-refresh)",
    ): "uvx pip-audit -s osv --progress-spinner off . > /dev/null 2>&1 || true",
    (".github/workflows/ci.yml", "cve-scan", "CVE gate (critical/high, severity-filtered)"): (
        "uv run --frozen python scripts/ci/cve_gate.py"
    ),
    (
        ".github/workflows/publish-internal-images.yml",
        "publish",
        "Resolve release tag",
    ): (
        'if [ -n "${INPUT_VERSION}" ]; then\n'
        '  VERSION="${INPUT_VERSION}"\n'
        "else\n"
        '  VERSION="${GITHUB_REF_NAME}"\n'
        "fi\n"
        'echo "value=${VERSION}" >> "${GITHUB_OUTPUT}"'
    ),
}


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


def _workflow_executors(
    path: str, workflow: str
) -> tuple[dict[tuple[str, str, str], str], tuple[str, ...], tuple[str, ...]]:
    parsed = yaml.safe_load(workflow)
    assert isinstance(parsed, dict), f"{path} must contain a workflow mapping"
    jobs = parsed.get("jobs")
    assert isinstance(jobs, dict), f"{path} must define jobs"

    runs: dict[tuple[str, str, str], str] = {}
    actions: list[str] = []
    reusable_jobs: list[str] = []
    for job_id, job in jobs.items():
        assert isinstance(job_id, str) and isinstance(job, dict)
        if isinstance(job.get("uses"), str):
            reusable_jobs.append(f"{path}:{job_id}:{job['uses']}")
        steps = job.get("steps", [])
        assert isinstance(steps, list), f"{path}:{job_id} steps must be a list"
        for step in steps:
            assert isinstance(step, dict), f"{path}:{job_id} step must be a mapping"
            run = step.get("run")
            uses = step.get("uses")
            assert not (isinstance(run, str) and isinstance(uses, str))
            if isinstance(run, str):
                name = step.get("name")
                assert isinstance(name, str) and name, f"{path}:{job_id} run step must be named"
                key = (path, job_id, name)
                assert key not in runs, f"duplicate hosted run step: {key}"
                runs[key] = run.strip()
            if isinstance(uses, str):
                actions.append(uses)
    return runs, tuple(actions), tuple(reusable_jobs)


def _assert_no_hosted_test_commands(
    workflows: dict[str, str],
    *,
    approved_runs: dict[tuple[str, str, str], str] | None = None,
    allowed_actions: set[str] | None = None,
) -> None:
    expected_runs = _APPROVED_HOSTED_RUNS if approved_runs is None else approved_runs
    expected_actions = _ALLOWED_HOSTED_ACTIONS if allowed_actions is None else allowed_actions
    actual_runs: dict[tuple[str, str, str], str] = {}
    actions: list[str] = []
    reusable_jobs: list[str] = []

    for path, workflow in workflows.items():
        runs, workflow_actions, workflow_reusable_jobs = _workflow_executors(path, workflow)
        duplicate_keys = actual_runs.keys() & runs.keys()
        assert not duplicate_keys, f"duplicate hosted run steps: {sorted(duplicate_keys)}"
        actual_runs.update(runs)
        actions.extend(workflow_actions)
        reusable_jobs.extend(workflow_reusable_jobs)

    missing = sorted(expected_runs.keys() - actual_runs.keys())
    extra = sorted(actual_runs.keys() - expected_runs.keys())
    changed = sorted(
        key
        for key in expected_runs.keys() & actual_runs.keys()
        if expected_runs[key] != actual_runs[key]
    )
    unknown_actions = sorted(set(actions) - expected_actions)
    assert not (missing or extra or changed), (
        "hosted workflows must not run local tests: approved run allowlist mismatch; "
        f"missing={missing}, extra={extra}, changed={changed}"
    )
    assert not unknown_actions, (
        f"hosted workflows must not run local tests: unapproved actions {unknown_actions}"
    )
    assert not reusable_jobs, (
        "hosted workflows must not run local tests: reusable workflow jobs require explicit policy "
        f"{reusable_jobs}"
    )


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
        "uv run --project . pytest tests/unit/ -q",
        "uvx --from pytest pytest tests/unit/ -q",
        "python -m pytest tests/contract/",
        "python -mpytest tests/contract/",
        "bash -c 'make test-core'",
        "bash -lc 'pytest tests/unit/'",
        "pwsh -Command 'python -m pytest tests/unit/'",
        "pwsh -Command '& scripts/windows_preflight.ps1 -M Tests'",
        "command -- pytest tests/unit/",
        "env -u PYTEST_ADDOPTS pytest tests/unit/",
        "echo setup\npython -m pytest tests/unit/",
        "echo setup\nmake test",
        "pwsh -File scripts/windows_preflight.ps1 -Mode Tests",
        'pwsh -File scripts/windows_preflight.ps1 -Mode "Tests"',
        "pwsh -File scripts/windows_preflight.ps1 -Mode `\nTests",
        "pwsh -File scripts/windows_preflight.ps1 Tests",
        "pwsh -File scripts/windows_preflight.ps1 -M Tests",
        "pwsh -File scripts/windows_preflight.ps1 -Mode:Tests",
        "pwsh -File scripts/windows_preflight.ps1 -Mode Full",
        r"pwsh -File .\scripts\windows_preflight.ps1 -Mode Tests",
        r".\.venv\Scripts\pytest.exe tests/unit/ -q",
        "py.test tests/unit/ -q",
        "make test",
        "gmake test-core",
        "make -j 2 test-core",
        "make -j test",
        "make -O test",
        "make \\\ntest-contract",
        "make candidate-check",
        "make local-pr-ready",
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
        _assert_no_hosted_test_commands(
            {".github/workflows/example.yml": workflow},
            approved_runs={},
            allowed_actions=set(),
        )


def test_hosted_test_command_contract_allows_static_commands() -> None:
    workflow = """
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - name: Pytest policy comment
        run: echo "# pytest remains local"
      - name: Makefile option value
        run: make --file=test.mk lint
      - name: Make variable assignment
        run: make MODE=test lint
      - name: Benign preflight argument text
        run: echo scripts/windows_preflight.ps1 Tests
      - name: Benign preflight fixture path
        run: pwsh -File scripts/windows_preflight.ps1 -Mode Static -OperatorEnvFile Tests
"""

    _assert_no_hosted_test_commands(
        {".github/workflows/example.yml": workflow},
        approved_runs={
            (".github/workflows/example.yml", "lint", "Pytest policy comment"): (
                'echo "# pytest remains local"'
            ),
            (".github/workflows/example.yml", "lint", "Makefile option value"): (
                "make --file=test.mk lint"
            ),
            (".github/workflows/example.yml", "lint", "Make variable assignment"): (
                "make MODE=test lint"
            ),
            (".github/workflows/example.yml", "lint", "Benign preflight argument text"): (
                "echo scripts/windows_preflight.ps1 Tests"
            ),
            (".github/workflows/example.yml", "lint", "Benign preflight fixture path"): (
                "pwsh -File scripts/windows_preflight.ps1 -Mode Static -OperatorEnvFile Tests"
            ),
        },
        allowed_actions=set(),
    )


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
