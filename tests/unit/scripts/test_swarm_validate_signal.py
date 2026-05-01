"""Unit tests for scripts/swarm_validate_signal.py."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.swarm_validate_signal import load_registry, validate_signal


FIXTURES = Path("tests/fixtures/swarm")
REGISTRY = FIXTURES / "active_workers.jsonl"
VALID_SIGNAL = FIXTURES / "valid_signal.json"


@pytest.fixture
def registry():
    return load_registry(REGISTRY)


@pytest.fixture
def valid_signal():
    return json.loads(VALID_SIGNAL.read_text(encoding="utf-8"))


@pytest.fixture
def registry_entry(registry):
    return registry["W-1279"]


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------
def test_load_registry_returns_dict_of_workers(registry):
    assert "W-1279" in registry
    assert registry["W-1279"]["worker"] == "W-1279"


# ---------------------------------------------------------------------------
# Valid signal
# ---------------------------------------------------------------------------
def test_valid_signal_returns_no_errors(registry_entry, valid_signal):
    errors = validate_signal(registry_entry, valid_signal, VALID_SIGNAL.resolve())
    assert errors == []


def test_cli_valid_signal_exits_zero():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/swarm_validate_signal.py",
            "--registry",
            str(REGISTRY),
            "--signal",
            str(VALID_SIGNAL),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.startswith("OK:")


# ---------------------------------------------------------------------------
# Worker not registered
# ---------------------------------------------------------------------------
def test_worker_not_registered():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/swarm_validate_signal.py",
            "--registry",
            str(REGISTRY),
            "--signal",
            str(FIXTURES / "invalid_worker_not_registered.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "not registered" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Signal path mismatch
# ---------------------------------------------------------------------------
def test_signal_path_mismatch(registry_entry, valid_signal, tmp_path):
    wrong_path = tmp_path / "wrong.json"
    wrong_path.write_text(json.dumps(valid_signal))
    errors = validate_signal(registry_entry, valid_signal, wrong_path)
    assert any("path mismatch" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Signal file outside registered worktree .signals/
# ---------------------------------------------------------------------------
def test_signal_outside_worktree_signals(registry_entry, tmp_path):
    outside_path = tmp_path / "outside.json"
    outside_path.write_text(json.dumps({"status": "done", "worker": "W-1279"}))
    # Temporarily point registry signal_file to this outside path so path match passes
    modified_entry = dict(registry_entry)
    modified_entry["signal_file"] = str(outside_path)
    errors = validate_signal(modified_entry, {"status": "done", "worker": "W-1279"}, outside_path)
    assert any("outside" in e.lower() and ".signals" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Field mismatches
# ---------------------------------------------------------------------------
def test_prompt_hash_mismatch(registry_entry, valid_signal):
    signal = dict(valid_signal)
    signal["prompt_sha256"] = "wrong"
    errors = validate_signal(registry_entry, signal, VALID_SIGNAL.resolve())
    assert any("prompt" in e.lower() and "mismatch" in e.lower() for e in errors)


def test_branch_mismatch(registry_entry, valid_signal):
    signal = dict(valid_signal)
    signal["branch"] = "wrong-branch"
    signal["head_ref"] = "wrong-branch"
    errors = validate_signal(registry_entry, signal, VALID_SIGNAL.resolve())
    assert any("branch" in e.lower() and "mismatch" in e.lower() for e in errors)


def test_base_mismatch(registry_entry, valid_signal):
    signal = dict(valid_signal)
    signal["base"] = "main"
    errors = validate_signal(registry_entry, signal, VALID_SIGNAL.resolve())
    assert any("base" in e.lower() and "mismatch" in e.lower() for e in errors)


def test_agent_mismatch(registry_entry, valid_signal):
    signal = dict(valid_signal)
    signal["agent"] = "wrong-agent"
    errors = validate_signal(registry_entry, signal, VALID_SIGNAL.resolve())
    assert any("agent" in e.lower() and "mismatch" in e.lower() for e in errors)


def test_model_mismatch(registry_entry, valid_signal):
    signal = dict(valid_signal)
    signal["model"] = "wrong-model"
    errors = validate_signal(registry_entry, signal, VALID_SIGNAL.resolve())
    assert any("model" in e.lower() and "mismatch" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# changed_files / pr_files outside reserved_files
# ---------------------------------------------------------------------------
def test_changed_files_outside_reserved(registry_entry, valid_signal):
    signal = dict(valid_signal)
    signal["changed_files"] = [
        "scripts/swarm_validate_signal.py",
        "telegram_bot/agents/rag_pipeline.py",
    ]
    errors = validate_signal(registry_entry, signal, VALID_SIGNAL.resolve())
    assert any("changed" in e.lower() and "reserved" in e.lower() for e in errors)


def test_pr_files_outside_reserved(registry_entry, valid_signal):
    signal = dict(valid_signal)
    signal["pr_files"] = ["scripts/swarm_validate_signal.py", "telegram_bot/agents/rag_pipeline.py"]
    errors = validate_signal(registry_entry, signal, VALID_SIGNAL.resolve())
    assert any("pr" in e.lower() and "reserved" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Commands structure
# ---------------------------------------------------------------------------
def test_commands_not_objects():
    signal = json.loads((FIXTURES / "invalid_commands_not_objects.json").read_text())
    registry = load_registry(REGISTRY)
    entry = registry["W-1279"]
    errors = validate_signal(entry, signal, FIXTURES / "invalid_commands_not_objects.json")
    assert any("commands" in e.lower() and "object" in e.lower() for e in errors)


def test_required_command_missing_exit(registry_entry, valid_signal):
    signal = dict(valid_signal)
    signal["commands"] = [
        {"cmd": "make check", "status": "passed", "required": True, "summary": "passed"}
    ]
    errors = validate_signal(registry_entry, signal, VALID_SIGNAL.resolve())
    assert any("exit" in e.lower() and "missing" in e.lower() for e in errors)


def test_required_command_missing_status(registry_entry, valid_signal):
    signal = dict(valid_signal)
    signal["commands"] = [{"cmd": "make check", "exit": 0, "required": True, "summary": "passed"}]
    errors = validate_signal(registry_entry, signal, VALID_SIGNAL.resolve())
    assert any("status" in e.lower() and "missing" in e.lower() for e in errors)


def test_required_command_missing_required(registry_entry, valid_signal):
    signal = dict(valid_signal)
    signal["commands"] = [{"cmd": "make check", "exit": 0, "status": "passed", "summary": "passed"}]
    errors = validate_signal(registry_entry, signal, VALID_SIGNAL.resolve())
    assert any("required" in e.lower() and "missing" in e.lower() for e in errors)


def test_required_command_missing_summary(registry_entry, valid_signal):
    signal = dict(valid_signal)
    signal["commands"] = [{"cmd": "make check", "exit": 0, "status": "passed", "required": True}]
    errors = validate_signal(registry_entry, signal, VALID_SIGNAL.resolve())
    assert any("summary" in e.lower() and "missing" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Required command skipped or failed
# ---------------------------------------------------------------------------
def test_required_command_failed(registry_entry, valid_signal):
    signal = dict(valid_signal)
    signal["commands"] = [
        {"cmd": "make check", "exit": 1, "status": "failed", "required": True, "summary": "failed"}
    ]
    errors = validate_signal(registry_entry, signal, VALID_SIGNAL.resolve())
    assert any("failed" in e.lower() and "required" in e.lower() for e in errors)


def test_required_command_skipped(registry_entry, valid_signal):
    signal = dict(valid_signal)
    signal["commands"] = [
        {
            "cmd": "make check",
            "exit": None,
            "status": "skipped",
            "required": True,
            "summary": "skipped",
        }
    ]
    errors = validate_signal(registry_entry, signal, VALID_SIGNAL.resolve())
    assert any("skipped" in e.lower() and "required" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# CLI error codes
# ---------------------------------------------------------------------------
def test_cli_missing_registry():
    result = subprocess.run(
        [sys.executable, "scripts/swarm_validate_signal.py", "--signal", str(VALID_SIGNAL)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2


def test_cli_missing_signal():
    result = subprocess.run(
        [sys.executable, "scripts/swarm_validate_signal.py", "--registry", str(REGISTRY)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2


def test_cli_bad_registry():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/swarm_validate_signal.py",
            "--registry",
            "nonexistent.jsonl",
            "--signal",
            str(VALID_SIGNAL),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2


def test_cli_bad_signal():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/swarm_validate_signal.py",
            "--registry",
            str(REGISTRY),
            "--signal",
            "nonexistent.json",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
