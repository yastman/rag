"""Unit tests for scripts/swarm_reserved_guard.py."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.swarm_reserved_guard import check_overlaps, load_registry


FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "swarm"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# check_overlaps tests
# ---------------------------------------------------------------------------


def test_no_overlap_returns_empty_list() -> None:
    # Arrange
    fixture = _load_fixture("non_overlapping_reservations.json")
    new_worker = fixture["new_worker"]
    active_workers = fixture["active_workers"]

    # Act
    overlaps = check_overlaps(new_worker, active_workers)

    # Assert
    assert overlaps == []


def test_overlapping_files_returns_correct_details() -> None:
    # Arrange
    fixture = _load_fixture("overlapping_reservations.json")
    new_worker = fixture["new_worker"]
    active_workers = fixture["active_workers"]

    # Act
    overlaps = check_overlaps(new_worker, active_workers)

    # Assert
    assert len(overlaps) == 1
    assert overlaps[0]["worker_id"] == "w1"
    assert overlaps[0]["overlapping_files"] == ["src/a.py"]


def test_multiple_overlaps_across_multiple_workers() -> None:
    # Arrange
    new_worker = {"worker_id": "w5", "reserved_files": ["src/a.py", "src/c.py"]}
    active_workers = [
        {"worker_id": "w1", "reserved_files": ["src/a.py", "src/b.py"]},
        {"worker_id": "w2", "reserved_files": ["src/c.py", "src/d.py"]},
    ]

    # Act
    overlaps = check_overlaps(new_worker, active_workers)

    # Assert
    assert len(overlaps) == 2
    worker_ids = {o["worker_id"] for o in overlaps}
    assert worker_ids == {"w1", "w2"}


def test_allow_sequential_permits_overlap_with_sequential_worker() -> None:
    # Arrange
    new_worker = {"worker_id": "w3", "reserved_files": ["src/a.py"]}
    active_workers = [
        {"worker_id": "w1", "reserved_files": ["src/a.py"], "sequential": True},
    ]

    # Act
    overlaps = check_overlaps(new_worker, active_workers, allow_sequential=True)

    # Assert
    assert overlaps == []


def test_allow_sequential_still_detects_non_sequential_overlap() -> None:
    # Arrange
    new_worker = {"worker_id": "w3", "reserved_files": ["src/a.py"]}
    active_workers = [
        {"worker_id": "w1", "reserved_files": ["src/a.py"], "sequential": True},
        {"worker_id": "w2", "reserved_files": ["src/a.py"]},
    ]

    # Act
    overlaps = check_overlaps(new_worker, active_workers, allow_sequential=True)

    # Assert
    assert len(overlaps) == 1
    assert overlaps[0]["worker_id"] == "w2"


# ---------------------------------------------------------------------------
# load_registry tests
# ---------------------------------------------------------------------------


def test_load_registry_reads_jsonl(tmp_path: Path) -> None:
    # Arrange
    registry = tmp_path / "workers.jsonl"
    registry.write_text(
        '{"worker_id": "w1", "reserved_files": ["a.py"]}\n'
        '{"worker_id": "w2", "reserved_files": ["b.py"]}\n',
        encoding="utf-8",
    )

    # Act
    workers = load_registry(registry)

    # Assert
    assert len(workers) == 2
    assert workers[0]["worker_id"] == "w1"
    assert workers[1]["worker_id"] == "w2"


def test_load_registry_from_fixture() -> None:
    # Arrange
    path = FIXTURES / "active_workers.jsonl"

    # Act
    workers = load_registry(path)

    # Assert
    assert len(workers) == 3
    assert workers[0]["worker_id"] == "w1"


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


def test_cli_exits_zero_on_no_overlap(tmp_path: Path) -> None:
    # Arrange
    import subprocess

    new_worker_file = tmp_path / "new_worker.json"
    new_worker_file.write_text(
        json.dumps({"worker_id": "w5", "reserved_files": ["src/x.py"]}),
        encoding="utf-8",
    )
    registry_file = tmp_path / "registry.jsonl"
    registry_file.write_text(
        '{"worker_id": "w1", "reserved_files": ["src/a.py"]}\n',
        encoding="utf-8",
    )

    # Act
    result = subprocess.run(
        [
            "python",
            "-m",
            "scripts.swarm_reserved_guard",
            "--new-worker",
            str(new_worker_file),
            "--registry",
            str(registry_file),
        ],
        capture_output=True,
        text=True,
    )

    # Assert
    assert result.returncode == 0
    assert "OK" in result.stdout


def test_cli_exits_one_on_overlap(tmp_path: Path) -> None:
    # Arrange
    import subprocess

    new_worker_file = tmp_path / "new_worker.json"
    new_worker_file.write_text(
        json.dumps({"worker_id": "w5", "reserved_files": ["src/a.py"]}),
        encoding="utf-8",
    )
    registry_file = tmp_path / "registry.jsonl"
    registry_file.write_text(
        '{"worker_id": "w1", "reserved_files": ["src/a.py"]}\n',
        encoding="utf-8",
    )

    # Act
    result = subprocess.run(
        [
            "python",
            "-m",
            "scripts.swarm_reserved_guard",
            "--new-worker",
            str(new_worker_file),
            "--registry",
            str(registry_file),
        ],
        capture_output=True,
        text=True,
    )

    # Assert
    assert result.returncode == 1
    assert "OVERLAP" in result.stdout
