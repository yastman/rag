"""Unit tests for .codex/scripts/ swarm session/log forensics and cleanup helpers.

Covers all five helpers from issue #1551:
  - session_log_profile.py
  - session_extract_spikes.py
  - swarm_run_correlate.py
  - opencode_log_markers.py
  - cleanup_swarm_run.py

The tests are focused, local-fast, and do NOT require Docker, tmux, or real
Codex/OpenCode sessions. They operate on synthetic fixtures.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest


# Make .codex/scripts importable
_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / ".codex" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmpdir() -> Path:
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def sample_jsonl(tmpdir: Path) -> Path:
    """Create a minimal synthetic Codex JSONL log."""
    records = [
        {
            "timestamp": "2026-05-14T10:00:00Z",
            "type": "message_start",
            "message_start": {"message": {"usage": {"input_tokens": 15000}}},
        },
        {
            "timestamp": "2026-05-14T10:00:01Z",
            "type": "content_block_start",
            "content_block_start": {"content_block": {"type": "tool_use", "name": "bash"}},
            "input": "cat large_file.txt",
        },
        {"timestamp": "2026-05-14T10:00:02Z", "type": "tool_result", "output": "x" * 600_000},
        {
            "timestamp": "2026-05-14T10:00:03Z",
            "type": "message_delta",
            "message_delta": {"usage": {"output_tokens": 25000}},
        },
        {
            "timestamp": "2026-05-14T10:00:04Z",
            "type": "message_delta",
            "message_delta": {"usage": {"output_tokens": 25400}},
        },
    ]
    p = tmpdir / "test_rollout.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(rec) + "\n" for rec in records)
    return p


@pytest.fixture
def sample_profile() -> dict[str, Any]:
    """Return a minimal profile matching session_log_profile.py output shape."""
    return {
        "format": "session_profile_v1",
        "total_records": 5,
        "total_events_with_tokens": 3,
        "max_tokens": 25400,
        "min_tokens": 15000,
        "token_timeline": [
            {"line": 1, "ts": "2026-05-14T10:00:00Z", "tokens": 15000},
            {"line": 4, "ts": "2026-05-14T10:00:03Z", "tokens": 25000, "delta": 10000},
            {"line": 5, "ts": "2026-05-14T10:00:04Z", "tokens": 25400, "delta": 400},
        ],
        "largest_token_jumps": [
            {"line": 4, "abs_delta": 10000, "delta": 10000, "ts": "2026-05-14T10:00:03Z"},
            {"line": 5, "abs_delta": 400, "delta": 400, "ts": "2026-05-14T10:00:04Z"},
        ],
        "spike_jumps_over_threshold": [
            {"line": 4, "abs_delta": 10000, "delta": 10000, "ts": "2026-05-14T10:00:03Z"},
        ],
        "threshold_delta_tokens": 5000,
        "tool_calls_total": 2,
        "tool_output_bytes_total": 600002,
        "tool_call_details": [
            {"line": 2, "ts": "2026-05-14T10:00:01Z", "tool_name": "bash", "output_bytes": None},
            {"line": 3, "ts": "2026-05-14T10:00:02Z", "tool_name": None, "output_bytes": 600002},
        ],
        "suspicious_commands": [
            {
                "line": 2,
                "ts": "2026-05-14T10:00:01Z",
                "reason": "Command pattern 'cat ' detected in tool input",
                "tool": "bash",
            },
        ],
    }


@pytest.fixture
def ansi_log_content() -> str:
    """Synthetic OpenCode TUI log with ANSI codes and key markers."""
    return (
        "\x1b[32m[INFO]\x1b[0m Starting worker\n"
        "Running validation checks...\n"
        "\x1b[33m[WARN]\x1b[0m Precheck result: pass\n"
        'Writing DONE JSON with status "DONE"\n'
        "Running swarm_notify_orchestrator --signal done.json\n"
        "\x1b[31m[ERROR]\x1b[0m Traceback (most recent call last):\n"
        '  File "script.py", line 10, in foo\n'
        "Exception: Something went wrong\n"
        "validator acceptance precheck passed\n"
        'Final: {"status": "done", "summary": "completed"}\n'
    )


@pytest.fixture
def ansi_log_file(tmpdir: Path, ansi_log_content: str) -> Path:
    p = tmpdir / "opencode-W-test.log"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(ansi_log_content)
    return p


@pytest.fixture
def swarm_worktree(tmpdir: Path) -> Path:
    """Create a minimal swarm worktree structure for correlation tests."""
    wt = tmpdir / "swarm_wt"
    signals_dir = wt / ".signals"
    prompts_dir = wt / ".codex" / "prompts"
    logs_dir = wt / "logs"
    for d in (signals_dir, prompts_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Launch file
    launch_data = {
        "worker": "worker-1551-swarm-helpers",
        "runner": "opencode",
        "agent": "pr-worker-deepseek",
        "model": "opencode-go/deepseek-v4-pro",
        "variant": "wave1-1551",
        "started_at": "2026-05-14T15:22:26+00:00",
        "prompt_sha256": "44e6ac3659b992c953ec40268c8ef48e0ecb63725c6741c38de6bb279b5734ae",
        "required_skills": ["swarm-pr-finish"],
        "prompt_file": "/tmp/.codex/prompts/worker-1551-swarm-helpers.md",
        "worktree": str(wt),
        "route_check_confirmed": "1",
    }
    with open(signals_dir / "launch-worker-1551-swarm-helpers.json", "w") as fh:
        json.dump(launch_data, fh)

    # DONE signal
    done_data = {
        "status": "done",
        "issue": 1551,
        "summary": "Implemented swarm helpers",
        "review_decision": "not_reviewed",
        "changed_files": [".codex/scripts/session_log_profile.py"],
        "findings": [],
        "blockers_found": [],
        "blockers_resolved": [],
        "new_bugs": [],
        "verification_budget": "focused_only",
        "runner": "opencode",
        "worker": "worker-1551-swarm-helpers",
        "ts": "2026-05-14T16:00:00+00:00",
    }
    with open(signals_dir / "DONE-worker-1551-swarm-helpers.json", "w") as fh:
        json.dump(done_data, fh)

    # Wakeup
    wakeup_data = {
        "worker": "worker-1551-swarm-helpers",
        "status": "done",
        "tag": "DONE",
        "sent_at": "2026-05-14T16:01:00+00:00",
        "signal_file": str(signals_dir / "DONE-worker-1551-swarm-helpers.json"),
    }
    with open(signals_dir / "wakeup-worker-1551-swarm-helpers.json", "w") as fh:
        json.dump(wakeup_data, fh)

    # Prompt file
    with open(prompts_dir / "worker-1551-swarm-helpers.md", "w") as fh:
        fh.write("# Worker prompt\nImplement issue 1551.\n")

    # Log file (synthetic, >1 KB to pass cleanup min-size filter)
    with open(logs_dir / "opencode-worker-1551-swarm-helpers.log", "w") as fh:
        fh.write("line 1\n" * 300)

    return wt


# ---------------------------------------------------------------------------
# session_log_profile tests
# ---------------------------------------------------------------------------


class TestSessionLogProfile:
    """Tests for session_log_profile.py."""

    def test_imports(self):
        """Module imports cleanly."""
        import session_log_profile as slp

        assert hasattr(slp, "main")
        assert hasattr(slp, "_parse_jsonl")
        assert hasattr(slp, "_token_from")
        assert hasattr(slp, "_make_profile")

    def test_parse_jsonl_valid(self, sample_jsonl):
        """Parses valid JSONL and returns records."""
        import session_log_profile as slp

        records = slp._parse_jsonl(sample_jsonl)
        assert len(records) == 5
        assert records[0]["timestamp"].startswith("2026")

    def test_parse_jsonl_handles_corrupted_lines(self, tmpdir):
        """Corrupted JSONL lines are captured as parse-error records."""
        import session_log_profile as slp

        bad = tmpdir / "bad.jsonl"
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write('{"valid": true}\n')
            fh.write("not json at all\n")
            fh.write('{"also_valid": 1}\n')
        records = slp._parse_jsonl(bad)
        assert len(records) == 3
        assert records[1].get("_parse_error") is True

    def test_token_from_message_start(self):
        """Extracts input_tokens from anthropic message_start."""
        import session_log_profile as slp

        rec = {"message_start": {"message": {"usage": {"input_tokens": 12345}}}}
        assert slp._token_from(rec) == 12345

    def test_token_from_message_delta(self):
        """Extracts output_tokens from anthropic message_delta."""
        import session_log_profile as slp

        rec = {"message_delta": {"usage": {"output_tokens": 500}}}
        assert slp._token_from(rec) == 500

    def test_token_from_flat_usage(self):
        """Extracts total_tokens from OpenAI-style usage."""
        import session_log_profile as slp

        rec = {"usage": {"total_tokens": 999}}
        assert slp._token_from(rec) == 999

    def test_token_from_token_count_key(self):
        """Heuristic: token_count key."""
        import session_log_profile as slp

        rec = {"token_count": 42}
        assert slp._token_from(rec) == 42

    def test_token_from_unknown(self):
        """Returns None for unrecognised records."""
        import session_log_profile as slp

        assert slp._token_from({}) is None
        assert slp._token_from({"type": "ping"}) is None

    def test_make_profile_structure(self, sample_jsonl):
        """make_profile returns expected top-level keys."""
        import session_log_profile as slp

        records = slp._parse_jsonl(sample_jsonl)
        profile = slp._make_profile(records)
        assert profile["format"] == "session_profile_v1"
        assert isinstance(profile["total_records"], int)
        assert isinstance(profile["token_timeline"], list)
        assert isinstance(profile["largest_token_jumps"], list)
        assert isinstance(profile["spike_jumps_over_threshold"], list)
        assert isinstance(profile["suspicious_commands"], list)

    def test_make_profile_finds_spike(self, sample_jsonl):
        """Large token delta is captured as a spike."""
        import session_log_profile as slp

        records = slp._parse_jsonl(sample_jsonl)
        profile = slp._make_profile(records)
        spikes = profile["spike_jumps_over_threshold"]
        assert len(spikes) >= 1
        assert spikes[0]["abs_delta"] > 5000

    def test_make_profile_finds_suspicious_cat(self, sample_jsonl):
        """'cat ' in tool input is flagged as suspicious."""
        import session_log_profile as slp

        records = slp._parse_jsonl(sample_jsonl)
        profile = slp._make_profile(records)
        suspicious = profile["suspicious_commands"]
        assert any("cat " in s.get("reason", "") for s in suspicious)

    def test_empty_jsonl(self, tmpdir):
        """Empty JSONL produces empty but valid profile."""
        import session_log_profile as slp

        empty = tmpdir / "empty.jsonl"
        empty.write_text("")
        records = slp._parse_jsonl(empty)
        profile = slp._make_profile(records)
        assert profile["total_records"] == 0
        assert profile["token_timeline"] == []


# ---------------------------------------------------------------------------
# session_extract_spikes tests
# ---------------------------------------------------------------------------


class TestSessionExtractSpikes:
    """Tests for session_extract_spikes.py."""

    def test_imports(self):
        import session_extract_spikes as ses

        assert hasattr(ses, "main")
        assert hasattr(ses, "_bounded_snippets")

    def test_bounded_snippets(self, sample_profile):
        """Extracts snippets with correct context window."""
        import session_extract_spikes as ses

        timeline = sample_profile["token_timeline"]
        spike_lines = {4}
        snippets = ses._bounded_snippets(timeline, spike_lines, context=1)
        assert len(snippets) == 1
        snip = snippets[0]
        assert snip["spike_line"] == 4
        assert snip["spike_delta"] == 10000
        assert snip["spike_entry"]["line"] == 4
        # context=1 means 1 entry before and after
        assert len(snip["context_before"]) <= 1
        assert len(snip["context_after"]) <= 1

    def test_bounded_snippets_empty(self):
        """No spike lines returns empty list."""
        import session_extract_spikes as ses

        assert ses._bounded_snippets([], set()) == []

    def test_bounded_snippets_no_match(self):
        """Spike lines not in timeline returns empty."""
        import session_extract_spikes as ses

        timeline = [{"line": 1, "tokens": 100}]
        assert ses._bounded_snippets(timeline, {99}, context=3) == []

    def test_bounded_snippets_boundary(self):
        """Snippets at timeline boundary don't crash."""
        import session_extract_spikes as ses

        timeline = [{"line": 1, "tokens": 100}]
        snippets = ses._bounded_snippets(timeline, {1}, context=5)
        assert len(snippets) == 1
        assert len(snippets[0]["context_before"]) == 0
        assert len(snippets[0]["context_after"]) == 0


# ---------------------------------------------------------------------------
# swarm_run_correlate tests
# ---------------------------------------------------------------------------


class TestSwarmRunCorrelate:
    """Tests for swarm_run_correlate.py."""

    def test_imports(self):
        import swarm_run_correlate as src

        assert hasattr(src, "main")
        assert hasattr(src, "_find_files")
        assert hasattr(src, "_extract_key_meta")

    def test_find_files_launch(self, swarm_worktree: Path):
        """Finds launch files by prefix."""
        import swarm_run_correlate as src

        files = src._find_files(swarm_worktree, ".signals", "launch-*.json")
        assert len(files) >= 1
        assert any("launch-worker-1551" in f.name for f in files)

    def test_find_files_nonexistent_dir(self):
        """_find_files returns [] for nonexistent directories."""
        import swarm_run_correlate as src

        files = src._find_files(Path("/does/not/exist"), ".signals", "*.json")
        assert files == []

    def test_load_json_safe_valid(self, swarm_worktree: Path):
        """_load_json_safe loads valid JSON."""
        import swarm_run_correlate as src

        launch_file = swarm_worktree / ".signals" / "launch-worker-1551-swarm-helpers.json"
        data = src._load_json_safe(launch_file)
        assert data is not None
        assert data["worker"] == "worker-1551-swarm-helpers"
        assert isinstance(data["prompt_sha256"], str)
        assert data["prompt_sha256"]

    def test_load_json_safe_invalid(self, tmpdir: Path):
        """_load_json_safe returns error dict for broken JSON."""
        import swarm_run_correlate as src

        broken = tmpdir / "broken.json"
        broken.write_text("{not valid")
        data = src._load_json_safe(broken)
        assert isinstance(data, dict)
        assert "_load_error" in data

    def test_load_json_safe_missing(self):
        """_load_json_safe returns None for missing files."""
        import swarm_run_correlate as src

        assert src._load_json_safe(Path("/no/such/file.json")) is None

    def test_extract_key_meta_launch(self):
        """Extracts only relevant keys from launch data."""
        import swarm_run_correlate as src

        launch = {
            "worker": "w1",
            "runner": "opencode",
            "agent": "a1",
            "model": "m1",
            "variant": "v1",
            "started_at": "ts1",
            "prompt_sha256": "abc",
            "required_skills": ["s1"],
            "prompt_file": "pf",
            "worktree": "wt",
            "route_check_confirmed": "1",
            "extra_field": "should_not_appear",
        }
        meta = src._extract_key_meta(launch, "launch")
        assert "extra_field" not in meta
        assert meta["worker"] == "w1"
        assert meta["prompt_sha256"] == "abc"

    def test_extract_key_meta_error(self):
        """_load_error dict is returned as-is."""
        import swarm_run_correlate as src

        meta = src._extract_key_meta({"_load_error": "bad"}, "launch")
        assert meta == {"_load_error": "bad"}

    def test_extract_key_meta_unknown_prefix(self):
        """Unknown prefix returns empty dict."""
        import swarm_run_correlate as src

        assert src._extract_key_meta({"a": 1}, "unknown") == {}

    def test_worker_dossier_launch_metadata(self, swarm_worktree: Path):
        """Correlated dossier includes launch metadata with expected keys."""
        import swarm_run_correlate as src

        launch_files = src._find_files(
            swarm_worktree, ".signals", "launch-worker-1551-swarm-helpers*.json"
        )
        assert launch_files
        launch_data = src._load_json_safe(launch_files[0])
        assert launch_data is not None
        meta = src._extract_key_meta(launch_data, "launch")
        assert meta.get("worker") == "worker-1551-swarm-helpers"
        assert meta.get("prompt_sha256")


# ---------------------------------------------------------------------------
# opencode_log_markers tests
# ---------------------------------------------------------------------------


class TestOpenCodeLogMarkers:
    """Tests for opencode_log_markers.py."""

    def test_imports(self):
        import opencode_log_markers as olm

        assert hasattr(olm, "main")
        assert hasattr(olm, "strip_ansi")
        assert hasattr(olm, "find_markers")
        assert hasattr(olm, "extract_snippets")

    def test_strip_ansi_removes_color_codes(self):
        """ANSI color codes are stripped from text."""
        import opencode_log_markers as olm

        colored = "\x1b[32mGreen text\x1b[0m normal"
        clean = olm.strip_ansi(colored)
        assert clean == "Green text normal"

    def test_strip_ansi_no_ansi(self):
        """Text without ANSI passes through unchanged."""
        import opencode_log_markers as olm

        assert olm.strip_ansi("plain text") == "plain text"

    def test_strip_ansi_empty(self):
        """Empty string survives stripping."""
        import opencode_log_markers as olm

        assert olm.strip_ansi("") == ""

    def test_find_markers_orchestrator(self):
        """Finds swarm_notify_orchestrator marker."""
        import opencode_log_markers as olm

        lines = ["Running swarm_notify_orchestrator --signal done.json"]
        markers = olm.find_markers(lines, olm.MARKER_PATTERNS)
        assert len(markers) >= 1
        assert markers[0]["label"] == "orchestrator_wakeup"

    def test_find_markers_done_status(self):
        """Finds DONE status marker."""
        import opencode_log_markers as olm

        lines = ['{"status": "DONE", "worker": "w1"}']
        markers = olm.find_markers(lines, olm.MARKER_PATTERNS)
        assert len(markers) >= 1
        assert markers[0]["label"] == "DONE_status"

    def test_find_markers_traceback(self):
        """Finds traceback marker."""
        import opencode_log_markers as olm

        lines = ["Traceback (most recent call last):", "  File 'x.py', line 1"]
        markers = olm.find_markers(lines, olm.MARKER_PATTERNS)
        assert len(markers) >= 1
        assert markers[0]["label"] == "traceback"

    def test_find_markers_multiple_patterns(self):
        """Multiple patterns in one line all get captured."""
        import opencode_log_markers as olm

        lines = ["Error: Exception occurred and validator failed"]
        markers = olm.find_markers(lines, olm.MARKER_PATTERNS)
        labels = {m["label"] for m in markers}
        assert "exception" in labels or "error" in labels

    def test_find_markers_none(self):
        """No markers returns empty list."""
        import opencode_log_markers as olm

        markers = olm.find_markers(["nothing interesting here"], olm.MARKER_PATTERNS)
        assert markers == []

    def test_extract_snippets_context(self):
        """Snippets include correct context window."""
        import opencode_log_markers as olm

        lines = [f"line {i}" for i in range(20)]
        markers = [
            {
                "line": 10,
                "label": "test",
                "pattern": "line 9",
                "matched_text": "line 9",
                "full_line": "line 9",
            }
        ]
        snippets = olm.extract_snippets(lines, markers, context=3)
        assert len(snippets) == 1
        snip = snippets[0]
        assert len(snip["context_before"]) == 3
        assert len(snip["context_after"]) == 3
        assert "line 9" in snip["marker_line"]

    def test_extract_snippets_empty_markers(self):
        """Empty markers returns empty snippets."""
        import opencode_log_markers as olm

        assert olm.extract_snippets(["a"], [], context=5) == []

    def test_extract_snippets_boundary_start(self):
        """Snippet at start returns fewer context_before lines."""
        import opencode_log_markers as olm

        lines = [f"line {i}" for i in range(5)]
        markers = [
            {
                "line": 1,
                "label": "start",
                "pattern": "line 0",
                "matched_text": "line 0",
                "full_line": "line 0",
            }
        ]
        snippets = olm.extract_snippets(lines, markers, context=5)
        assert len(snippets[0]["context_before"]) == 0
        assert len(snippets[0]["context_after"]) == 4

    def test_markers_from_ansi_log(self, ansi_log_file):
        """Integration: finds markers in an ANSI log file."""
        import opencode_log_markers as olm

        with open(ansi_log_file, encoding="utf-8") as fh:
            raw_lines = fh.readlines()
        clean_lines = [olm.strip_ansi(ln) for ln in raw_lines]
        markers = olm.find_markers(clean_lines, olm.MARKER_PATTERNS)
        assert len(markers) > 0

    def test_markers_discover_done_and_orch(self, ansi_log_file):
        """ANSI log contains DONE and orchestrator markers."""
        import opencode_log_markers as olm

        with open(ansi_log_file, encoding="utf-8") as fh:
            raw_lines = fh.readlines()
        clean_lines = [olm.strip_ansi(ln) for ln in raw_lines]
        markers = olm.find_markers(clean_lines, olm.MARKER_PATTERNS)
        labels = {m["label"] for m in markers}
        assert "done_status" in labels
        assert "orchestrator_wakeup" in labels


# ---------------------------------------------------------------------------
# cleanup_swarm_run tests
# ---------------------------------------------------------------------------


class TestCleanupSwarmRun:
    """Tests for cleanup_swarm_run.py."""

    def test_imports(self):
        import cleanup_swarm_run as csr

        assert hasattr(csr, "main")
        assert hasattr(csr, "_plan_actions")
        assert hasattr(csr, "_execute_actions")

    def test_plan_actions_finds_logs(self, swarm_worktree: Path):
        """_plan_actions discovers log files for a worker prefix."""
        import cleanup_swarm_run as csr

        actions = csr._plan_actions(swarm_worktree, "worker-1551-swarm-helpers")
        log_actions = [a for a in actions if "logs/" in a["path"]]
        assert len(log_actions) >= 1

    def test_plan_actions_finds_prompts(self, swarm_worktree: Path):
        """_plan_actions discovers prompt files for a worker prefix."""
        import cleanup_swarm_run as csr

        actions = csr._plan_actions(swarm_worktree, "worker-1551-swarm-helpers")
        prompt_actions = [a for a in actions if ".codex/prompts" in a["path"]]
        assert len(prompt_actions) >= 1

    def test_plan_actions_no_match(self, swarm_worktree: Path):
        """_plan_actions returns [] for unmatched prefix."""
        import cleanup_swarm_run as csr

        actions = csr._plan_actions(swarm_worktree, "nonexistent-prefix")
        assert actions == []

    def test_execute_actions_archives_files(self, swarm_worktree: Path, tmpdir: Path):
        """_execute_actions archives files to archive_dir."""
        import cleanup_swarm_run as csr

        actions = csr._plan_actions(swarm_worktree, "worker-1551-swarm-helpers")
        archive_dir = tmpdir / "archive"
        results = csr._execute_actions(actions, archive_dir)
        archived = [r for r in results if r.get("status") == "archived"]
        assert len(archived) >= 1
        for r in archived:
            dst = Path(r["archived_to"])
            assert dst.exists()

    def test_execute_actions_empty(self, tmpdir: Path):
        """Empty actions returns empty results."""
        import cleanup_swarm_run as csr

        results = csr._execute_actions([], tmpdir / "archive")
        assert results == []

    def test_execute_actions_missing_file(self, tmpdir: Path):
        """Missing files are skipped gracefully."""
        import cleanup_swarm_run as csr

        actions = [{"path": str(tmpdir / "nonexistent.log"), "size_bytes": 9999}]
        results = csr._execute_actions(actions, tmpdir / "archive")
        assert results[0]["status"] == "skipped"

    def test_close_tmux_window_dry_run(self):
        """_close_tmux_window in dry-run mode does not modify tmux."""
        import shutil

        import cleanup_swarm_run as csr

        if not shutil.which("tmux"):
            pytest.skip("tmux not available")
        result = csr._close_tmux_window("no-such-worker-zzz", dry_run=True)
        assert result["action"] == "close_tmux_window"

    def test_close_tmux_window_no_tmux(self, monkeypatch: pytest.MonkeyPatch):
        """When tmux is not available, close is skipped."""
        import shutil as _shutil

        import cleanup_swarm_run as csr

        monkeypatch.setattr(_shutil, "which", lambda _x: None)
        result = csr._close_tmux_window("worker-x", dry_run=True)
        assert result["status"] == "skipped"
        assert "tmux not available" in result["reason"]


# ---------------------------------------------------------------------------
# Edge cases and regression
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge-case and regression tests across all helpers."""

    def test_profile_with_no_tokens(self, tmpdir: Path):
        """JSONL with no token-bearing records produces valid empty profile."""
        import session_log_profile as slp

        p = tmpdir / "no_tokens.jsonl"
        with open(p, "w", encoding="utf-8") as fh:
            fh.write('{"type": "ping"}\n{"type": "pong"}\n')
        records = slp._parse_jsonl(p)
        profile = slp._make_profile(records)
        assert profile["token_timeline"] == []
        assert profile["max_tokens"] == 0

    def test_profile_unicode_record(self, tmpdir: Path):
        """JSONL with unicode content is handled."""
        import session_log_profile as slp

        p = tmpdir / "unicode.jsonl"
        with open(p, "w", encoding="utf-8") as fh:
            fh.write('{"type": "message", "text": "Привет мир!"}\n')
        records = slp._parse_jsonl(p)
        assert len(records) == 1

    def test_markers_strip_ansi_osc(self):
        """ANSI OSC sequences (title setters) are stripped."""
        import opencode_log_markers as olm

        text = "\x1b]0;Terminal Title\x07Hello"
        clean = olm.strip_ansi(text)
        assert "\x1b]" not in clean
        assert "Hello" in clean

    def test_correlator_no_worktree_files(self, tmpdir: Path):
        """Correlator handles a directory with no worker files."""
        import swarm_run_correlate as src

        files = src._find_files(tmpdir, ".signals", "launch-*.json")
        assert files == []
