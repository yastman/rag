"""Execute Make orchestration; actual tool gates run separately on the candidate.

The local uv interceptor records argv and exits without running tools, preventing
recursive pytest and dependency sync. This proves dispatch, not tool outcomes or
real environment immutability; those require the full candidate/adapter runs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def run_make(tmp_path):
    make = shutil.which("make")
    assert make, "GNU make is required for the executable Make contracts"
    shell = shutil.which("bash")
    if os.name == "nt":
        git = shutil.which("git")
        assert git, "Git Bash is required for Make recipes on Windows"
        shell = next(
            (
                str(parent / "bin" / "bash.exe")
                for parent in Path(git).resolve().parents
                if (parent / "bin" / "bash.exe").is_file()
            ),
            None,
        )
    assert shell and Path(shell).is_file(), "Bash is required for Make recipes"
    recorder = tmp_path / "record.py"
    recorder.write_text(
        "import json, os, sys\n"
        "with open(os.environ['MAKE_TEST_LOG'], 'a', encoding='utf-8') as log:\n"
        "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "sys.exit(23 if os.environ.get('MAKE_TEST_FAIL') in sys.argv[1:] else 0)\n",
        encoding="utf-8",
    )
    uv = tmp_path / "uv"
    uv.write_text('#!/bin/sh\nexec "$MAKE_TEST_PYTHON" "$MAKE_TEST_RECORDER" "$@"\n')
    uv.chmod(0o755)
    log = tmp_path / "commands.jsonl"
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "MAKE_TEST_PYTHON": sys.executable,
        "MAKE_TEST_RECORDER": str(recorder),
        "MAKE_TEST_LOG": str(log),
    }
    for variable in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKE_TEST_FAIL"):
        env.pop(variable, None)

    def run(target, *overrides, fail=None):
        log.write_text("")
        # Force shell execution: native Windows Make otherwise bypasses PATH scripts.
        result = subprocess.run(
            [
                make,
                "--no-print-directory",
                "-j1",
                f"SHELL={shell}",
                ".SHELLFLAGS=-o pipefail -c",
                target,
                *overrides,
            ],
            cwd=ROOT,
            env={**env, "MAKE_TEST_FAIL": fail or ""},
            capture_output=True,
            text=True,
            timeout=20,
        )
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        return result, calls

    return run


def test_candidate_dispatches_read_only_quality_and_test_lanes(run_make):
    result, calls = run_make("candidate-check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls[0][0] == "sync" and {"--frozen", "--check"} <= set(calls[0])
    runs = calls[1:]
    assert runs and all(call[:2] == ["run", "--no-sync"] for call in runs)
    for tool in ("ruff", "mypy"):
        tool_calls = [call for call in runs if tool in call]
        assert tool_calls
        assert all(
            {"src/", "telegram_bot/", "services/", "scripts/"} <= set(call) for call in tool_calls
        )
    assert any("format" in call and "--check" in call for call in runs)
    tests = [call for call in runs if "pytest" in call]
    for lane in (
        "tests/unit/core/",
        "tests/unit/runtime/",
        "tests/integration",
        "tests/smoke",
        "tests/contract/",
    ):
        assert any(lane in call for call in tests), lane
    assert all("tests/unit/" not in call and "tests/unit/dialogs" not in call for call in tests)


def test_candidate_propagates_tool_failure_before_test_lanes(run_make):
    result, calls = run_make("candidate-check", fail="mypy")
    assert result.returncode != 0
    assert any("mypy" in call for call in calls)
    assert not any("pytest" in call for call in calls)


def test_telegram_adapter_selects_its_dependencies_and_tests(run_make):
    result, calls = run_make("test-telegram-adapter")
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls[0][0] == "sync"
    assert calls[0][calls[0].index("--extra") + 1] == "telegram"
    tests = [call for call in calls[1:] if "pytest" in call]
    assert len(tests) == 1
    assert {"tests/unit/dialogs", "tests/unit/handlers", "tests/unit/keyboards"} <= set(tests[0])


@pytest.mark.parametrize("target", ["test-contract", "test-unit", "test-store-durations"])
def test_parallel_override_and_runtime_authority_reach_pytest(run_make, target):
    pin = (ROOT / ".python-version").read_text().strip()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pin in SpecifierSet(project["project"]["requires-python"])
    result, calls = run_make(target, "PYTEST_PARALLEL_ARGS=-n 2 --dist=worksteal")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(calls) == 1
    args = calls[0]
    assert args[:2] == ["run", "--no-sync"] and "pytest" in args
    assert args.count("-n") == 1 and args[args.index("-n") + 1] == "2"
    assert "--dist=worksteal" in args
    if target != "test-contract":
        assert args[args.index("--python") + 1] == pin
