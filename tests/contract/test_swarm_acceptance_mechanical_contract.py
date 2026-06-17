"""Contract tests for #2305 P0: remove the "two-truths" acceptance.

Pins the boundary agreed in SWARM_AUDIT_REPORT.md:

- Rails (`accept_worker_report.py`, `launch_kiro_worker.sh`) may emit only
  MECHANICAL facts. They must NOT emit a semantic acceptance verdict
  (`decision=accepted` / `merge_ready`) and must NOT auto-create a PR.
  The semantic accept/PR/merge decision belongs to the orchestrator
  (`swarm-acceptance`).
- `schema-valid != accepted`: structural validation is a mechanical fact.
- `scripts/worker_report_schema.py` is the single code-level source of truth
  for worker-report fields; its required code-changing field set must match the
  steering contract (`.kiro/steering/swarm-worker-contract.md`).
- The steering "Pinned by" reference must point to a test file that exists.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
STEERING = REPO_ROOT / ".kiro" / "steering" / "swarm-worker-contract.md"

# The six fields acceptance tooling scans verbatim (steering §"Worker Report Schema").
STEERING_CORE_FIELDS = {
    "superpowers_used",
    "skipped_superpowers",
    "changed_files",
    "tests_run",
    "verification_evidence",
    "evidence_commands",
}


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / filename)
    assert spec is not None and spec.loader is not None, f"cannot load {filename}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample_report(tmp_path: Path) -> Path:
    report = tmp_path / "REPORT.sample-worker.md"
    report.write_text(
        "# Worker Report: sample-worker\n"
        "status: done\n"
        "worker: sample-worker\n"
        "changed_files:\n- src/foo.py\n"
        "tests_run:\n- tests/test_foo.py: 3 passed\n"
        "verification_evidence: ran focused tests, all green\n"
        "evidence_commands:\n- uv run pytest tests/test_foo.py\n",
        encoding="utf-8",
    )
    return report


# --- P0: no semantic decision in the rail scripts ---


def test_accept_script_does_not_emit_semantic_decision(tmp_path: Path) -> None:
    report = _sample_report(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "accept_worker_report.py"),
            "--report",
            str(report),
            "--role",
            "implementation",
        ],
        capture_output=True,
        text=True,
    )
    out = result.stdout + result.stderr
    assert "decision=accepted" not in out, (
        f"rail script must not emit a semantic acceptance verdict; got:\n{out}"
    )
    assert "merge_ready" not in out


def test_accept_script_emits_mechanical_facts(tmp_path: Path) -> None:
    report = _sample_report(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "accept_worker_report.py"),
            "--report",
            str(report),
            "--role",
            "implementation",
        ],
        capture_output=True,
        text=True,
    )
    out = result.stdout
    assert "report_found=1" in out, f"expected mechanical facts, got:\n{out}"
    assert "mechanical_checks_passed=" in out


def test_accept_script_reports_missing_fields_mechanically(tmp_path: Path) -> None:
    bad = tmp_path / "REPORT.bad.md"
    bad.write_text("# Worker Report: bad\nstatus: done\nworker: bad\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "accept_worker_report.py"),
            "--report",
            str(bad),
            "--role",
            "implementation",
        ],
        capture_output=True,
        text=True,
    )
    out = result.stdout
    # Missing required fields => mechanical_checks_passed=0, still NOT a verdict.
    assert "mechanical_checks_passed=0" in out
    assert "decision=accepted" not in out


def test_launcher_has_no_auto_acceptance_or_auto_pr() -> None:
    text = (SCRIPTS_DIR / "launch_kiro_worker.sh").read_text(encoding="utf-8")
    assert "accept_worker_report.py" not in text, (
        "launcher must not run semantic acceptance; orchestrator owns that"
    )
    assert "create_pr.sh" not in text, "launcher must not auto-create a PR from acceptance"
    assert "KIRO_AUTO_PR" not in text, "auto-PR flag must be removed from the launcher"


# --- P1 foundation: single code-level schema source of truth ---


def test_worker_report_schema_module_exists_and_matches_steering() -> None:
    module = _load("worker_report_schema", "worker_report_schema.py")
    assert hasattr(module, "WorkerReport"), "expected a WorkerReport pydantic model"
    assert hasattr(module, "code_changing_required_fields"), (
        "expected a code_changing_required_fields() helper"
    )
    fields = set(module.code_changing_required_fields())
    assert fields == STEERING_CORE_FIELDS, (
        f"schema required fields drifted from steering contract: {fields ^ STEERING_CORE_FIELDS}"
    )


def test_schema_fields_present_in_steering_doc() -> None:
    steering_text = STEERING.read_text(encoding="utf-8")
    module = _load("worker_report_schema", "worker_report_schema.py")
    for field in module.code_changing_required_fields():
        assert field in steering_text, f"schema field {field!r} missing from steering doc"


# --- F6: the steering pin must point to a real test ---


def test_steering_pin_points_to_existing_test() -> None:
    steering_text = STEERING.read_text(encoding="utf-8")
    import re

    refs = re.findall(r"tests/contract/test_[\w/]+\.py", steering_text)
    assert refs, "steering must reference a pinning contract test"
    for ref in refs:
        assert (REPO_ROOT / ref).exists(), f"steering references a non-existent test file: {ref}"


# --- P3: legacy JSON validators are gated behind KIRO_STRICT_REPORT=1 ---


@pytest.mark.parametrize(
    "script,args",
    [
        ("validate_done_json.py", ["/nonexistent.json"]),
        ("validate_worker_signal.py", ["--role", "quick", "--signal", "/nonexistent.json"]),
    ],
)
def test_legacy_json_validator_is_noop_without_strict_env(script: str, args: list[str]) -> None:
    env = {k: v for k, v in os.environ.items() if k != "KIRO_STRICT_REPORT"}
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script), *args],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, (
        f"{script} must be a no-op (exit 0) without KIRO_STRICT_REPORT=1; "
        f"rc={result.returncode} out={result.stdout} err={result.stderr}"
    )
    assert "SKIP" in result.stdout, f"{script} should announce the skip; got {result.stdout!r}"


@pytest.mark.parametrize("script", ["validate_done_json.py", "validate_worker_signal.py"])
def test_legacy_json_validator_marked_legacy_in_docstring(script: str) -> None:
    text = (SCRIPTS_DIR / script).read_text(encoding="utf-8")
    assert "LEGACY" in text and "KIRO_STRICT_REPORT" in text, (
        f"{script} must be marked LEGACY and reference KIRO_STRICT_REPORT"
    )


# --- pr-review acceptance role (read-only review reports) ---


def test_schema_exposes_pr_review_required_fields() -> None:
    module = _load("worker_report_schema", "worker_report_schema.py")
    fields = set(module.required_fields_for_role("pr-review"))
    # A review report carries a decision + head + replayable evidence, NOT
    # superpowers (it is read-only, the PR_REVIEW shape has no such fields).
    assert fields == {"review_decision", "head_sha", "evidence_commands"}, fields
    assert "superpowers_used" not in fields


def test_accept_pr_review_report_passes_mechanically(tmp_path: Path) -> None:
    report = tmp_path / "PR_REVIEW.sample.md"
    report.write_text(
        "# PR_REVIEW\n"
        "status: done\n"
        "pr: 2582\n"
        "head_sha: 64ad9ad226\n"
        "review_decision: merge_ready\n"
        "evidence_commands:\n- gh pr diff 2582\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "accept_worker_report.py"),
            "--report",
            str(report),
            "--role",
            "pr-review",
        ],
        capture_output=True,
        text=True,
    )
    out = result.stdout
    assert "decision=accepted" not in out
    assert "required_fields_present=1" in out, out
    assert "mechanical_checks_passed=1" in out, out
