"""Contract test for issue #2296 — review/candidate gates must be read-only.

`make check` (via `lint` / `type-check`) invokes plain `uv run`, which
auto-syncs the project environment before running. In a shared/reused `.venv`
review worktree this mutates the environment — it re-points the editable
install at the temporary worktree and can switch package versions — so the
"validation" step is not read-only. #2290 added `check-frozen` /
`candidate-check` to avoid this by preflighting with `uv sync --frozen --check`
and then running tools via `$(UV_RUN_NO_SYNC)` (`uv run --no-sync`).

This contract pins that the review-safe gates can never silently regress to a
mutating `uv run`:

* `check-frozen` and `candidate-check` exist;
* `check-frozen` preflights read-only with `uv sync --frozen --check`;
* every tool invocation inside the review-safe gates uses `--no-sync`
  (directly or via `$(UV_RUN_NO_SYNC)`), never a bare auto-syncing `uv run`.

It deliberately does NOT forbid bare `uv run` in developer-friendly `make check`
(auto-sync there is intentional, per the issue).
"""

from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
MAKEFILE = REPO / "Makefile"

# Targets that MUST be read-only with respect to the shared .venv (#2296).
REVIEW_SAFE_TARGETS = ("check-frozen", "candidate-check")


def _makefile_text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def _target_block(text: str, target: str) -> str:
    pattern = rf"^{re.escape(target)}:.*?(?=^[A-Za-z0-9_.-]+:|\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    assert match, f"Makefile must define a {target!r} target (#2296)"
    return match.group(0)


def _uv_run_invocations(block: str) -> list[str]:
    """Return every `uv run ...` command line in a recipe block."""
    return [line.strip() for line in block.splitlines() if re.search(r"\buv run\b", line)]


def test_review_safe_targets_exist() -> None:
    text = _makefile_text()
    for target in REVIEW_SAFE_TARGETS:
        assert re.search(rf"^{re.escape(target)}:", text, re.MULTILINE), (
            f"Makefile must define the read-only review gate {target!r} (#2296)."
        )


def test_check_frozen_preflights_read_only() -> None:
    block = _target_block(_makefile_text(), "check-frozen")
    assert "uv sync --frozen --check" in block, (
        "check-frozen must preflight the environment read-only with "
        "'uv sync --frozen --check' so a stale .venv fails with guidance "
        "instead of being auto-synced (#2296)."
    )


def test_review_safe_gates_never_use_bare_uv_run() -> None:
    """No `uv run` inside a review-safe gate may auto-sync; all must be --no-sync."""
    text = _makefile_text()
    offenders: list[str] = []
    for target in REVIEW_SAFE_TARGETS:
        block = _target_block(text, target)
        for line in _uv_run_invocations(block):
            # Allowed: `uv run --no-sync ...` or the `$(UV_RUN_NO_SYNC)` macro.
            if "$(UV_RUN_NO_SYNC)" in line or "--no-sync" in line:
                continue
            offenders.append(f"{target}: {line}")
    assert not offenders, (
        "Review/candidate gates must run tools without auto-sync "
        "($(UV_RUN_NO_SYNC) / 'uv run --no-sync'); a bare 'uv run' mutates the "
        "shared .venv (#2296). Offenders:\n  " + "\n  ".join(offenders)
    )


def test_check_frozen_runs_both_lint_and_typecheck_no_sync() -> None:
    """The read-only gate must actually cover ruff + mypy via the no-sync runner."""
    block = _target_block(_makefile_text(), "check-frozen")
    no_sync_lines = [
        line
        for line in block.splitlines()
        if ("$(UV_RUN_NO_SYNC)" in line or "--no-sync" in line)
    ]
    joined = "\n".join(no_sync_lines)
    assert "ruff check" in joined, (
        "check-frozen must run 'ruff check' via the no-sync runner (#2296)."
    )
    assert "mypy" in joined, (
        "check-frozen must run 'mypy' via the no-sync runner (#2296)."
    )


def test_uv_run_no_sync_macro_is_no_sync() -> None:
    """The shared $(UV_RUN_NO_SYNC) macro itself must resolve to a no-sync run."""
    text = _makefile_text()
    match = re.search(r"^UV_RUN_NO_SYNC\s*[:?]?=\s*(.+?)$", text, re.MULTILINE)
    assert match, "Makefile must define UV_RUN_NO_SYNC (#2296)."
    value = match.group(1).strip()
    assert "--no-sync" in value, (
        f"UV_RUN_NO_SYNC must use 'uv run --no-sync'; found: {value!r} (#2296)."
    )


class TestDetectorSelfChecks:
    """Guard the helper so the contract cannot rot into vacuity."""

    def test_detects_bare_uv_run(self) -> None:
        block = "check-frozen:\n\tuv run ruff check src/\n"
        bad = [
            ln
            for ln in _uv_run_invocations(block)
            if "--no-sync" not in ln and "$(UV_RUN_NO_SYNC)" not in ln
        ]
        assert bad == ["uv run ruff check src/"]

    def test_accepts_no_sync_and_macro(self) -> None:
        block = (
            "check-frozen:\n"
            "\tuv run --no-sync ruff check src/\n"
            "\t$(UV_RUN_NO_SYNC) mypy src/\n"
        )
        bad = [
            ln
            for ln in _uv_run_invocations(block)
            if "--no-sync" not in ln and "$(UV_RUN_NO_SYNC)" not in ln
        ]
        assert bad == []
