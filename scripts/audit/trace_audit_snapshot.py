"""Runtime trace-data audit snapshot (#2221 / Epic L).

The repo already has the right runtime-audit tooling:

* ``scripts/validate_traces.py``        — required trace-family coverage gate
* ``scripts/validate_voice_traces.py``  — voice-session trace validation
* ``scripts/langfuse_triage.py``        — dislike-trace triage (dry-run here)
* ``scripts/probe/observability_diagnostic.py`` — Langfuse/LiteLLM noise probe

…but no single command that runs them and produces ONE reviewable markdown
snapshot. This orchestrator wraps them behind ``make trace-audit-snapshot``.

Each underlying script runs as a **best-effort** subprocess: stdout + return
code are captured into a section. A failing step (Langfuse down, missing dep)
becomes a section flagged FAIL — it never aborts the whole snapshot. The
combined report is written to ``docs/engineering/<date>-trace-audit-snapshot.md``.

Usage::

    make trace-audit-snapshot
    uv run python -m scripts.audit.trace_audit_snapshot
    uv run python -m scripts.audit.trace_audit_snapshot --stdout   # print, don't write
    uv run python -m scripts.audit.trace_audit_snapshot --strict   # exit 1 if any step failed
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

# (section title, argv). Best-effort dry-run flavours so the snapshot is
# side-effect-free (e.g. triage --dry-run does not touch the annotation queue).
AUDIT_STEPS: list[tuple[str, list[str]]] = [
    (
        "Required trace-family coverage (validate_traces.py)",
        ["uv", "run", "python", "scripts/validate_traces.py"],
    ),
    (
        "Voice-session traces (validate_voice_traces.py)",
        ["uv", "run", "python", "scripts/validate_voice_traces.py"],
    ),
    (
        "Dislike-trace triage dry-run (langfuse_triage.py)",
        ["uv", "run", "python", "scripts/langfuse_triage.py", "--dry-run"],
    ),
    (
        "Observability diagnostic (probe/observability_diagnostic.py)",
        ["uv", "run", "python", "scripts/probe/observability_diagnostic.py"],
    ),
]

_STEP_TIMEOUT_SEC = 300


@dataclass
class StepResult:
    title: str
    returncode: int
    output: str


def run_step(title: str, argv: list[str], *, runner=subprocess.run) -> StepResult:
    """Run a single audit script best-effort; capture stdout+stderr+rc.

    A runner exception (missing binary, timeout) is captured into the result
    rather than propagated, so one broken step never aborts the snapshot.
    """
    try:
        completed = runner(
            argv,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=_STEP_TIMEOUT_SEC,
        )
        rc = int(getattr(completed, "returncode", 1) or 0)
        stdout = getattr(completed, "stdout", "") or ""
        stderr = getattr(completed, "stderr", "") or ""
        output = stdout if rc == 0 else (stdout + "\n" + stderr).strip()
        return StepResult(title=title, returncode=rc, output=output or "(no output)")
    except Exception as exc:  # best-effort: never abort the whole snapshot
        return StepResult(title=title, returncode=1, output=f"{type(exc).__name__}: {exc}")


def build_snapshot_markdown(steps: list[StepResult], *, generated_at: datetime) -> str:
    """Assemble all step results into one reviewable markdown report."""
    passed = sum(1 for s in steps if s.returncode == 0)
    failed = len(steps) - passed
    lines = [
        "# Langfuse trace-data audit snapshot",
        "",
        f"- generated_at: {generated_at.isoformat()}",
        f"- steps: {len(steps)}  |  passed: {passed}  |  failed: {failed}",
        "",
        "## Summary",
        "",
        "| step | status |",
        "| --- | --- |",
    ]
    for s in steps:
        marker = "✅ PASS" if s.returncode == 0 else "❌ FAIL"
        lines.append(f"| {s.title} | {marker} |")
    lines.append("")
    for s in steps:
        marker = "✅ PASS" if s.returncode == 0 else f"❌ FAIL (rc={s.returncode})"
        lines.append(f"## {s.title} — {marker}")
        lines.append("")
        lines.append("```")
        lines.append(s.output.strip())
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def default_snapshot_path(generated_at: datetime) -> Path:
    date = generated_at.strftime("%Y-%m-%d")
    return REPO_ROOT / "docs" / "engineering" / f"{date}-trace-audit-snapshot.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Runtime trace-data audit snapshot")
    parser.add_argument("--stdout", action="store_true", help="print report, do not write file")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any audit step failed")
    args = parser.parse_args(argv)

    generated_at = datetime.now(UTC)
    steps = [run_step(title, cmd) for title, cmd in AUDIT_STEPS]
    report = build_snapshot_markdown(steps, generated_at=generated_at)

    if args.stdout:
        print(report)
    else:
        path = default_snapshot_path(generated_at)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
        print(f"Wrote trace-audit snapshot: {path.relative_to(REPO_ROOT)}")

    if args.strict and any(s.returncode != 0 for s in steps):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
