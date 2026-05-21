"""Unit tests for scripts/swarm_validate_signal.py."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.swarm_validate_signal import check_policy, validate_signal


FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "swarm"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# validate_signal tests
# ---------------------------------------------------------------------------


def test_valid_signal_returns_no_errors() -> None:
    # Arrange
    data = _load_fixture("valid_signal.json")

    # Act
    errors = validate_signal(data)

    # Assert
    assert errors == []


def test_missing_required_field_returns_error() -> None:
    # Arrange
    data = _load_fixture("malformed_signal_missing_status.json")

    # Act
    errors = validate_signal(data)

    # Assert
    assert len(errors) == 1
    assert "missing required field: status" in errors[0]


def test_invalid_status_enum_returns_error() -> None:
    # Arrange
    data = _load_fixture("malformed_signal_bad_enum.json")

    # Act
    errors = validate_signal(data)

    # Assert
    assert any("invalid status" in e for e in errors)


def test_pr_files_not_subset_of_reserved_files_returns_scope_drift_error() -> None:
    # Arrange
    data = _load_fixture("valid_signal.json")
    data["pr_files"] = ["scripts/foo.py", "scripts/bar.py"]

    # Act
    errors = validate_signal(data)

    # Assert
    assert any("scope drift" in e for e in errors)


def test_empty_command_evidence_returns_error() -> None:
    # Arrange
    data = _load_fixture("valid_signal.json")
    data["command_evidence"] = []

    # Act
    errors = validate_signal(data)

    # Assert
    assert any("command_evidence must not be empty" in e for e in errors)


def test_reserved_files_not_list_returns_error() -> None:
    # Arrange
    data = _load_fixture("valid_signal.json")
    data["reserved_files"] = "scripts/foo.py"

    # Act
    errors = validate_signal(data)

    # Assert
    assert any("reserved_files must be a list" in e for e in errors)


def test_branch_empty_string_returns_error() -> None:
    # Arrange
    data = _load_fixture("valid_signal.json")
    data["branch"] = ""

    # Act
    errors = validate_signal(data)

    # Assert
    assert any("branch must be a non-empty string" in e for e in errors)


def test_multiple_missing_fields_returns_all_errors() -> None:
    # Arrange
    data = {}

    # Act
    errors = validate_signal(data)

    # Assert
    assert len(errors) == len(
        ["status", "branch", "base", "prompt_hash", "agent", "model",
         "reserved_files", "pr_files", "command_evidence"]
    )


# ---------------------------------------------------------------------------
# check_policy tests
# ---------------------------------------------------------------------------


def test_check_policy_clean_signal_returns_no_errors() -> None:
    # Arrange
    data = _load_fixture("valid_signal.json")

    # Act
    errors = check_policy(data)

    # Assert
    assert errors == []


def test_check_policy_denied_command_pattern_returns_error() -> None:
    # Arrange
    data = _load_fixture("valid_signal.json")
    data["command_evidence"] = ["rm -rf / --no-preserve-root"]

    # Act
    errors = check_policy(data)

    # Assert
    assert any("denied command pattern" in e for e in errors)


def test_check_policy_disallowed_path_returns_error() -> None:
    # Arrange
    data = _load_fixture("valid_signal.json")
    data["reserved_files"] = ["/etc/passwd"]

    # Act
    errors = check_policy(data)

    # Assert
    assert any("path not in allowed prefixes" in e for e in errors)


def test_check_policy_sudo_command_returns_error() -> None:
    # Arrange
    data = _load_fixture("valid_signal.json")
    data["command_evidence"] = ["sudo apt-get install malware"]

    # Act
    errors = check_policy(data)

    # Assert
    assert any("sudo " in e for e in errors)
