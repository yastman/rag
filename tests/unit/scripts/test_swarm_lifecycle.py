"""Unit tests for scripts/swarm_lifecycle.py."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.swarm_lifecycle import (
    ALLOWED_TRANSITIONS,
    transition_worker,
    validate_transition,
)


FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "swarm"


def _load_transitions_fixture() -> dict:
    return json.loads((FIXTURES / "lifecycle_transitions.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# validate_transition tests
# ---------------------------------------------------------------------------


def test_all_valid_transitions_succeed() -> None:
    # Arrange
    fixture = _load_transitions_fixture()

    # Act / Assert
    for current, target in fixture["valid"]:
        assert validate_transition(current, target), f"{current} -> {target} should be valid"


def test_all_invalid_transitions_are_rejected() -> None:
    # Arrange
    fixture = _load_transitions_fixture()

    # Act / Assert
    for current, target in fixture["invalid"]:
        assert not validate_transition(current, target), f"{current} -> {target} should be invalid"


def test_done_to_active_is_invalid() -> None:
    # Act
    result = validate_transition("done", "active")

    # Assert
    assert result is False


def test_active_to_done_is_valid() -> None:
    # Act
    result = validate_transition("active", "done")

    # Assert
    assert result is True


def test_terminal_states_have_no_transitions() -> None:
    # Assert
    assert ALLOWED_TRANSITIONS["merged"] == []
    assert ALLOWED_TRANSITIONS["closed"] == []


# ---------------------------------------------------------------------------
# transition_worker tests
# ---------------------------------------------------------------------------


def test_transition_worker_updates_state(tmp_path: Path) -> None:
    # Arrange
    worker_file = tmp_path / "worker.json"
    worker_file.write_text(
        json.dumps({"state": "active", "worker_id": "w1"}),
        encoding="utf-8",
    )

    # Act
    result = transition_worker(worker_file, "done")

    # Assert
    assert result["state"] == "done"
    assert "updated_at" in result


def test_transition_worker_writes_file(tmp_path: Path) -> None:
    # Arrange
    worker_file = tmp_path / "worker.json"
    worker_file.write_text(
        json.dumps({"state": "active", "worker_id": "w1"}),
        encoding="utf-8",
    )

    # Act
    transition_worker(worker_file, "done")

    # Assert
    written = json.loads(worker_file.read_text(encoding="utf-8"))
    assert written["state"] == "done"
    assert "updated_at" in written


def test_transition_worker_updates_timestamp(tmp_path: Path) -> None:
    # Arrange
    worker_file = tmp_path / "worker.json"
    worker_file.write_text(
        json.dumps({"state": "active", "worker_id": "w1"}),
        encoding="utf-8",
    )

    # Act
    result = transition_worker(worker_file, "done")

    # Assert
    # ISO format timestamp should contain 'T' and timezone info
    assert "T" in result["updated_at"]


def test_transition_worker_invalid_transition_raises(tmp_path: Path) -> None:
    # Arrange
    worker_file = tmp_path / "worker.json"
    worker_file.write_text(
        json.dumps({"state": "done", "worker_id": "w1"}),
        encoding="utf-8",
    )

    # Act / Assert
    import pytest

    with pytest.raises(ValueError, match="invalid transition"):
        transition_worker(worker_file, "active")


def test_transition_worker_defaults_to_active_state(tmp_path: Path) -> None:
    # Arrange - worker file without explicit state
    worker_file = tmp_path / "worker.json"
    worker_file.write_text(
        json.dumps({"worker_id": "w1"}),
        encoding="utf-8",
    )

    # Act
    result = transition_worker(worker_file, "done")

    # Assert
    assert result["state"] == "done"


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


def test_cli_exits_zero_on_valid_transition(tmp_path: Path) -> None:
    # Arrange
    import subprocess

    worker_file = tmp_path / "worker.json"
    worker_file.write_text(
        json.dumps({"state": "active", "worker_id": "w1"}),
        encoding="utf-8",
    )

    # Act
    result = subprocess.run(
        ["python", "-m", "scripts.swarm_lifecycle", str(worker_file), "done"],
        capture_output=True,
        text=True,
    )

    # Assert
    assert result.returncode == 0
    assert "OK" in result.stdout


def test_cli_exits_one_on_invalid_transition(tmp_path: Path) -> None:
    # Arrange
    import subprocess

    worker_file = tmp_path / "worker.json"
    worker_file.write_text(
        json.dumps({"state": "done", "worker_id": "w1"}),
        encoding="utf-8",
    )

    # Act
    result = subprocess.run(
        ["python", "-m", "scripts.swarm_lifecycle", str(worker_file), "active"],
        capture_output=True,
        text=True,
    )

    # Assert
    assert result.returncode == 1
    assert "ERROR" in result.stdout
