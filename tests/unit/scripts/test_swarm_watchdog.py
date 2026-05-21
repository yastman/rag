# tests/unit/scripts/test_swarm_watchdog.py
"""Unit tests for ``scripts/swarm_watchdog.py``.

Issue #1275 argues that the orchestrator (Codex) should not waste tokens
polling ``.signals/`` and ``git status`` in a loop while waiting for
workers. Instead a single observation should give a complete state
snapshot when the orchestrator chooses to look (or when a worker wakes
the orchestrator via tmux send-keys).

This module pins the contract of the read-only watchdog used to produce
that snapshot. The watchdog reads ``.signals/active-workers.jsonl`` plus
each worker's signal/heartbeat files and emits one compact JSON event
per worker. The orchestrator can call it once on resume, or run it in a
``--watch`` loop in a sidecar tmux pane.

Behavioural pins:

1. ``load_active_workers(path)`` parses a JSONL registry into a list of
   dicts with required keys ``worker``, ``signal_file``, optional
   ``heartbeat_file``, ``branch``, ``base``, ``started_at``.
   Malformed/blank lines are skipped without raising.
2. ``inspect_worker(worker, now=...)`` returns a per-worker observation:
   ``phase`` is one of ``active``, ``done``, ``failed``, ``blocked``,
   ``stale``; ``signal_exists`` is a bool; ``heartbeat_age_s`` is a
   float (or ``None`` if no heartbeat is registered/present).
3. ``scan(active_workers_path, now=...)`` returns a snapshot dict with
   ``timestamp``, ``signals_dir``, and ``workers`` (list of observations).
4. CLI ``--once`` prints the snapshot as a single JSON line and exits 0.
5. CLI emits an ``[ALL_DONE]`` line on stdout when every worker reaches
   a terminal phase, so a tmux watcher can consume it without parsing
   JSON.

Refs #1275, #1721 (worker -> orchestrator wake-up via tmux send-keys).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "swarm_watchdog.py"


@pytest.fixture(scope="module")
def watchdog_module():
    """Load ``scripts/swarm_watchdog.py`` as a module."""
    spec = importlib.util.spec_from_file_location("_swarm_watchdog", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None, SCRIPT_PATH
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses + other machinery that look up
    # cls.__module__ in sys.modules can find it.
    sys.modules["_swarm_watchdog"] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop("_swarm_watchdog", None)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _write_registry(path: Path, entries: list[dict]) -> None:
    """Write ``entries`` to ``path`` as JSONL. Creates parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


def _write_signal(path: Path, status: str = "done") -> None:
    """Write a worker signal JSON file with the given status."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "worker": path.stem,
                "status": status,
                "completed_at": "2026-05-21T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )


def _write_heartbeat(path: Path, *, age_s: float = 0.0) -> None:
    """Write a heartbeat JSON file with mtime ``now - age_s``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"worker": path.stem, "phase": "running"}),
        encoding="utf-8",
    )
    if age_s > 0:
        mtime = time.time() - age_s
        import os

        os.utime(path, (mtime, mtime))


# ---------------------------------------------------------------------------
# load_active_workers
# ---------------------------------------------------------------------------


class TestLoadActiveWorkers:
    def test_returns_empty_list_when_registry_does_not_exist(self, watchdog_module, tmp_path):
        registry = tmp_path / ".signals" / "active-workers.jsonl"
        # Do not create the file.
        result = watchdog_module.load_active_workers(registry)
        assert result == []

    def test_parses_one_worker_entry(self, watchdog_module, tmp_path):
        registry = tmp_path / ".signals" / "active-workers.jsonl"
        entry = {
            "worker": "W-foo",
            "signal_file": str(tmp_path / ".signals" / "worker-W-foo.json"),
            "branch": "kiro/1234-foo",
            "base": "dev",
            "started_at": "2026-05-21T11:00:00Z",
        }
        _write_registry(registry, [entry])

        result = watchdog_module.load_active_workers(registry)

        assert result == [entry]

    def test_skips_blank_lines_and_malformed_json(self, watchdog_module, tmp_path):
        registry = tmp_path / ".signals" / "active-workers.jsonl"
        registry.parent.mkdir(parents=True)
        registry.write_text(
            "\n"
            + json.dumps({"worker": "W-ok", "signal_file": "/tmp/W-ok.json"})
            + "\n"
            + "{not valid json}\n"
            + "\n"
            + json.dumps({"worker": "W-also", "signal_file": "/tmp/W-also.json"})
            + "\n"
        )

        result = watchdog_module.load_active_workers(registry)

        assert [w["worker"] for w in result] == ["W-ok", "W-also"]


# ---------------------------------------------------------------------------
# inspect_worker
# ---------------------------------------------------------------------------


class TestInspectWorker:
    def test_active_when_signal_missing_and_no_heartbeat(self, watchdog_module, tmp_path):
        worker = {
            "worker": "W-running",
            "signal_file": str(tmp_path / "worker-W-running.json"),
        }

        obs = watchdog_module.inspect_worker(worker, now=time.time())

        assert obs["worker"] == "W-running"
        assert obs["phase"] == "active"
        assert obs["signal_exists"] is False
        assert obs["heartbeat_age_s"] is None

    def test_done_when_signal_present_with_status_done(self, watchdog_module, tmp_path):
        signal_path = tmp_path / "worker-W-done.json"
        _write_signal(signal_path, status="done")
        worker = {"worker": "W-done", "signal_file": str(signal_path)}

        obs = watchdog_module.inspect_worker(worker, now=time.time())

        assert obs["phase"] == "done"
        assert obs["signal_exists"] is True

    def test_failed_when_signal_status_failed(self, watchdog_module, tmp_path):
        signal_path = tmp_path / "worker-W-fail.json"
        _write_signal(signal_path, status="failed")
        worker = {"worker": "W-fail", "signal_file": str(signal_path)}

        obs = watchdog_module.inspect_worker(worker, now=time.time())

        assert obs["phase"] == "failed"

    def test_blocked_when_signal_status_blocked(self, watchdog_module, tmp_path):
        signal_path = tmp_path / "worker-W-block.json"
        _write_signal(signal_path, status="blocked")
        worker = {"worker": "W-block", "signal_file": str(signal_path)}

        obs = watchdog_module.inspect_worker(worker, now=time.time())

        assert obs["phase"] == "blocked"

    def test_stale_when_heartbeat_older_than_threshold(self, watchdog_module, tmp_path):
        hb = tmp_path / "heartbeat-W-stale.json"
        _write_heartbeat(hb, age_s=900.0)  # 15 minutes
        worker = {
            "worker": "W-stale",
            "signal_file": str(tmp_path / "worker-W-stale.json"),
            "heartbeat_file": str(hb),
        }

        obs = watchdog_module.inspect_worker(worker, now=time.time(), stale_threshold_s=600.0)

        assert obs["phase"] == "stale"
        assert obs["heartbeat_age_s"] is not None
        assert obs["heartbeat_age_s"] > 600

    def test_active_when_heartbeat_recent(self, watchdog_module, tmp_path):
        hb = tmp_path / "heartbeat-W-fresh.json"
        _write_heartbeat(hb, age_s=10.0)
        worker = {
            "worker": "W-fresh",
            "signal_file": str(tmp_path / "worker-W-fresh.json"),
            "heartbeat_file": str(hb),
        }

        obs = watchdog_module.inspect_worker(worker, now=time.time(), stale_threshold_s=600.0)

        assert obs["phase"] == "active"
        assert obs["heartbeat_age_s"] is not None
        assert 9 <= obs["heartbeat_age_s"] <= 12

    def test_signal_takes_precedence_over_stale_heartbeat(self, watchdog_module, tmp_path):
        """A stale heartbeat plus a DONE signal must report ``done`` (terminal)."""
        signal_path = tmp_path / "worker-W-finished.json"
        _write_signal(signal_path, status="done")
        hb = tmp_path / "heartbeat-W-finished.json"
        _write_heartbeat(hb, age_s=900.0)

        worker = {
            "worker": "W-finished",
            "signal_file": str(signal_path),
            "heartbeat_file": str(hb),
        }

        obs = watchdog_module.inspect_worker(worker, now=time.time(), stale_threshold_s=600.0)

        # Terminal status wins over stale liveness check.
        assert obs["phase"] == "done"

    def test_handles_corrupt_signal_file_gracefully(self, watchdog_module, tmp_path):
        signal_path = tmp_path / "worker-W-corrupt.json"
        signal_path.write_text("{not valid json}", encoding="utf-8")
        worker = {"worker": "W-corrupt", "signal_file": str(signal_path)}

        obs = watchdog_module.inspect_worker(worker, now=time.time())

        # Corrupt signal must be reported, not crash.
        assert obs["phase"] == "failed"
        assert obs["signal_exists"] is True
        assert "error" in obs


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------


class TestScan:
    def test_scan_returns_snapshot_with_required_fields(self, watchdog_module, tmp_path):
        registry = tmp_path / ".signals" / "active-workers.jsonl"
        _write_registry(
            registry,
            [
                {
                    "worker": "W-a",
                    "signal_file": str(tmp_path / ".signals" / "worker-W-a.json"),
                },
                {
                    "worker": "W-b",
                    "signal_file": str(tmp_path / ".signals" / "worker-W-b.json"),
                },
            ],
        )
        _write_signal(tmp_path / ".signals" / "worker-W-a.json", status="done")
        # W-b has no signal yet -> active.

        snap = watchdog_module.scan(registry)

        assert "timestamp" in snap
        assert "signals_dir" in snap
        assert {w["worker"] for w in snap["workers"]} == {"W-a", "W-b"}
        phases = {w["worker"]: w["phase"] for w in snap["workers"]}
        assert phases == {"W-a": "done", "W-b": "active"}

    def test_scan_with_empty_registry(self, watchdog_module, tmp_path):
        registry = tmp_path / ".signals" / "active-workers.jsonl"
        # File doesn't exist.

        snap = watchdog_module.scan(registry)

        assert snap["workers"] == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_once_mode_emits_single_json_line_to_stdout(self, tmp_path):
        registry = tmp_path / ".signals" / "active-workers.jsonl"
        _write_registry(
            registry,
            [
                {
                    "worker": "W-a",
                    "signal_file": str(tmp_path / ".signals" / "worker-W-a.json"),
                }
            ],
        )

        result = self._run("--once", "--registry", str(registry))

        assert result.returncode == 0, result.stderr
        # Stdout: one JSON snapshot line + optional [ALL_DONE] line.
        json_lines = [
            line
            for line in result.stdout.splitlines()
            if line.startswith("{") and line.endswith("}")
        ]
        assert len(json_lines) == 1, result.stdout
        snap = json.loads(json_lines[0])
        assert snap["workers"][0]["worker"] == "W-a"
        assert snap["workers"][0]["phase"] == "active"

    def test_once_mode_prints_all_done_marker_when_terminal(self, tmp_path):
        registry = tmp_path / ".signals" / "active-workers.jsonl"
        signal = tmp_path / ".signals" / "worker-W-x.json"
        _write_registry(
            registry,
            [{"worker": "W-x", "signal_file": str(signal)}],
        )
        _write_signal(signal, status="done")

        result = self._run("--once", "--registry", str(registry))

        assert result.returncode == 0, result.stderr
        assert "[ALL_DONE]" in result.stdout

    def test_once_mode_with_no_workers_exits_zero(self, tmp_path):
        registry = tmp_path / ".signals" / "active-workers.jsonl"
        # Empty registry path.

        result = self._run("--once", "--registry", str(registry))

        assert result.returncode == 0, result.stderr
        # When there are no workers, ALL_DONE is the natural state.
        assert "[ALL_DONE]" in result.stdout

    def test_once_mode_with_only_partial_done_omits_all_done(self, tmp_path):
        registry = tmp_path / ".signals" / "active-workers.jsonl"
        _write_registry(
            registry,
            [
                {
                    "worker": "W-a",
                    "signal_file": str(tmp_path / ".signals" / "worker-W-a.json"),
                },
                {
                    "worker": "W-b",
                    "signal_file": str(tmp_path / ".signals" / "worker-W-b.json"),
                },
            ],
        )
        _write_signal(tmp_path / ".signals" / "worker-W-a.json", status="done")
        # W-b still active.

        result = self._run("--once", "--registry", str(registry))

        assert result.returncode == 0, result.stderr
        assert "[ALL_DONE]" not in result.stdout
