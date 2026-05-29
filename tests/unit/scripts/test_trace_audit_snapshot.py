"""Unit tests for scripts/audit/trace_audit_snapshot.py (#2221 / Epic L).

The repo already has the right runtime-audit tooling — validate_traces.py,
validate_voice_traces.py, langfuse_triage.py, probe/observability_diagnostic.py
— but no single command that runs them and produces ONE reviewable markdown
snapshot. Epic L adds ``make trace-audit-snapshot`` wrapping them.

The orchestrator runs each underlying script as a best-effort subprocess,
captures stdout + return code, and assembles a dated markdown report under
docs/engineering/. A failing step (Langfuse down, missing dep) becomes a
section with its error — it never aborts the whole snapshot.

These tests pin the pure/orchestration functions; the subprocess runner is
injected so no real scripts run.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest


snap = pytest.importorskip(
    "scripts.audit.trace_audit_snapshot",
    reason="trace audit snapshot orchestrator under test",
)


class TestRunStep:
    def test_captures_output_and_returncode(self) -> None:
        def fake_runner(argv, **kwargs):
            from types import SimpleNamespace

            assert argv[:2] == ["uv", "run"]
            return SimpleNamespace(returncode=0, stdout="OK output", stderr="")

        result = snap.run_step("Validate traces", ["uv", "run", "x"], runner=fake_runner)
        assert result.title == "Validate traces"
        assert result.returncode == 0
        assert "OK output" in result.output

    def test_best_effort_on_runner_exception(self) -> None:
        def boom_runner(argv, **kwargs):
            raise FileNotFoundError("uv not found")

        result = snap.run_step("Triage", ["uv", "run", "x"], runner=boom_runner)
        # Never raises; surfaces the failure in the result.
        assert result.returncode != 0
        assert "uv not found" in result.output or "FileNotFoundError" in result.output

    def test_includes_stderr_when_nonzero(self) -> None:
        def fail_runner(argv, **kwargs):
            from types import SimpleNamespace

            return SimpleNamespace(returncode=2, stdout="partial", stderr="boom err")

        result = snap.run_step("X", ["uv", "run", "x"], runner=fail_runner)
        assert result.returncode == 2
        assert "boom err" in result.output


class TestBuildSnapshotMarkdown:
    def test_assembles_sections_with_status(self) -> None:
        steps = [
            snap.StepResult(title="Validate traces", returncode=0, output="all good"),
            snap.StepResult(title="Voice traces", returncode=1, output="2 missing"),
        ]
        md = snap.build_snapshot_markdown(steps, generated_at=datetime(2026, 5, 29, 12, 0))
        assert "# Langfuse trace-data audit snapshot" in md
        assert "2026-05-29" in md
        # Each step renders as a section with a status marker.
        assert "Validate traces" in md
        assert "Voice traces" in md
        assert "all good" in md
        assert "2 missing" in md
        # Pass/fail markers present
        assert "PASS" in md or "✅" in md
        assert "FAIL" in md or "❌" in md

    def test_summary_counts(self) -> None:
        steps = [
            snap.StepResult(title="a", returncode=0, output="x"),
            snap.StepResult(title="b", returncode=0, output="y"),
            snap.StepResult(title="c", returncode=1, output="z"),
        ]
        md = snap.build_snapshot_markdown(steps, generated_at=datetime(2026, 5, 29))
        # 2 passed, 1 failed reflected in the summary.
        assert "2" in md and "1" in md


class TestSnapshotPath:
    def test_dated_path_under_docs_engineering(self) -> None:
        p = snap.default_snapshot_path(datetime(2026, 5, 29, 8, 30))
        assert isinstance(p, Path)
        assert p.name == "2026-05-29-trace-audit-snapshot.md"
        assert "docs/engineering" in p.as_posix()


class TestAuditStepsDefinition:
    def test_audit_steps_reference_existing_scripts(self) -> None:
        """Every wrapped script in AUDIT_STEPS must exist on disk so the
        snapshot does not silently produce 'module not found' sections."""
        repo_root = Path(snap.__file__).resolve().parents[2]
        missing = []
        for _title, argv in snap.AUDIT_STEPS:
            # argv like ["uv","run","python","scripts/validate_traces.py", ...]
            script = next(
                (a for a in argv if a.endswith(".py") or a.startswith("scripts.")),
                None,
            )
            if script is None:
                continue
            if script.endswith(".py") and not (repo_root / script).exists():
                missing.append(script)
        assert not missing, f"AUDIT_STEPS reference missing scripts: {missing}"

    def test_audit_steps_nonempty(self) -> None:
        assert len(snap.AUDIT_STEPS) >= 3
