"""Tests for scripts/validate_done_json.py schema validator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path("scripts/validate_done_json.py")

***REMOVED*** Import the validate function directly for unit tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from validate_done_json import extra_fields, validate


def _valid_done() -> dict:
    """Return a minimal valid DONE JSON payload."""
    return {
        "status": "DONE",
        "worker": "w1",
        "task": "t1",
        "worktree": "/tmp/wt",
        "branch": "feat/thing",
        "head_sha": "abc123def456",
        "reserved_files": ["src/main.py"],
        "changed_files": ["src/main.py"],
        "superpowers_used": [],
        "skipped_superpowers": [],
        "evidence_commands": ["make check"],
    }


def test_valid_done_json_passes() -> None:
    """A complete valid DONE JSON passes validation."""
    errors = validate(_valid_done())
    assert errors == []


@pytest.mark.parametrize(
    "field",
    [
        "status",
        "worker",
        "task",
        "worktree",
        "branch",
        "head_sha",
        "reserved_files",
        "changed_files",
        "superpowers_used",
        "skipped_superpowers",
        "evidence_commands",
    ],
)
def test_missing_required_field_fails(field: str) -> None:
    """Removing any required field causes validation failure."""
    data = _valid_done()
    del data[field]
    errors = validate(data)
    assert any(field in e for e in errors)


def test_invalid_status_fails() -> None:
    """A status value not in DONE/FAILED/BLOCKED causes failure."""
    data = _valid_done()
    data["status"] = "INVALID"
    errors = validate(data)
    assert any("invalid status" in e for e in errors)


def test_changed_files_non_string_fails() -> None:
    """changed_files with nested dict entries should fail."""
    data = _valid_done()
    data["changed_files"] = [{"path": "a.py", "lines": 10}]
    errors = validate(data)
    assert any("changed_files" in e and "string" in e for e in errors)


def test_empty_lists_valid() -> None:
    """All list fields can be empty lists and still pass."""
    data = _valid_done()
    data["reserved_files"] = []
    data["changed_files"] = []
    data["superpowers_used"] = []
    data["skipped_superpowers"] = []
    data["evidence_commands"] = []
    errors = validate(data)
    assert errors == []


def test_cli_stdin_valid() -> None:
    """CLI accepts valid JSON via stdin and exits 0."""
    import json

    payload = json.dumps(_valid_done())
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "-"],
        input=payload,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "OK" in result.stdout


def test_cli_invalid_exits_nonzero() -> None:
    """CLI exits non-zero for invalid JSON schema."""
    import json

    data = _valid_done()
    del data["status"]
    payload = json.dumps(data)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "-"],
        input=payload,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "ERROR" in result.stderr


def test_extra_fields_do_not_cause_validation_failure() -> None:
    """Extra fields in valid JSON still pass validation (no errors)."""
    data = _valid_done()
    data["unexpected_field"] = "some value"
    data["another_extra"] = 42
    errors = validate(data)
    assert errors == []


def test_extra_fields_detected() -> None:
    """extra_fields() returns the names of fields not in REQUIRED_FIELDS."""
    data = _valid_done()
    data["statux"] = "typo"
    data["bonus"] = True
    result = extra_fields(data)
    assert "statux" in result
    assert "bonus" in result
    ***REMOVED*** Required fields should not appear in extra_fields output
    assert "status" not in result


def test_cli_extra_fields_warns_but_exits_zero() -> None:
    """CLI outputs a warning for extra fields but still exits 0."""
    import json

    data = _valid_done()
    data["extra_key"] = "oops"
    payload = json.dumps(data)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "-"],
        input=payload,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "OK" in result.stdout
    assert "WARNING" in result.stderr
    assert "extra_key" in result.stderr
