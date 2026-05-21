"""Contract: ``make test-full`` must actually exercise benchmarks (#1618).

``make test-full`` includes ``tests/benchmark/`` in
``PYTEST_FULL_PARALLEL_DIRS``, but ColBERT benchmark tests skip unless
``RUN_BENCHMARK_TESTS=1`` is exported. Without that env var the command
documented as full-suite validation can report success while never
exercising a single benchmark assertion.

This contract pins:

1. The Phase 1 invocation of ``test-full`` exports ``RUN_BENCHMARK_TESTS=1``.
2. A standalone ``test-benchmark`` target exists so users can run
   benchmarks independently — also exporting ``RUN_BENCHMARK_TESTS=1``.
3. The benchmark suite remains in ``PYTEST_FULL_PARALLEL_DIRS`` (so the
   advertised "all tiers" wording stays accurate).
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"


def _target_body(text: str, target: str) -> str:
    """Return the lines that belong to a Make target's recipe."""
    pattern = re.compile(
        rf"^{re.escape(target)}:.*?$",
        re.MULTILINE,
    )
    match = pattern.search(text)
    assert match is not None, f"target '{target}:' not found in Makefile"
    start = match.end()
    body_lines: list[str] = []
    for line in text[start:].splitlines():
        if not line:
            continue
        if not line.startswith("\t"):
            break
        body_lines.append(line)
    return "\n".join(body_lines)


def test_test_full_phase1_exports_run_benchmark_tests() -> None:
    body = _target_body(MAKEFILE.read_text(encoding="utf-8"), "test-full")
    # Phase 1 is the parallel-safe pytest line that includes
    # $(PYTEST_FULL_PARALLEL_DIRS). It must export RUN_BENCHMARK_TESTS=1
    # for the ColBERT benchmark gate to actually run.
    parallel_lines = [
        line
        for line in body.splitlines()
        if "$(PYTEST_FULL_PARALLEL_DIRS)" in line
    ]
    assert parallel_lines, (
        "test-full must invoke pytest against $(PYTEST_FULL_PARALLEL_DIRS) "
        "in its parallel phase"
    )
    for line in parallel_lines:
        assert "RUN_BENCHMARK_TESTS=1" in line, (
            "test-full must export RUN_BENCHMARK_TESTS=1 in the parallel "
            "phase so ColBERT benchmark assertions actually run. Found:\n"
            f"  {line.strip()}"
        )


def test_test_benchmark_standalone_target_exists() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    assert re.search(r"^test-benchmark:", text, re.MULTILINE), (
        "Makefile must define a standalone 'test-benchmark' target so the "
        "benchmark suite can be exercised independently of test-full (#1618)."
    )
    body = _target_body(text, "test-benchmark")
    assert "RUN_BENCHMARK_TESTS=1" in body, (
        "test-benchmark must export RUN_BENCHMARK_TESTS=1 — otherwise the "
        "ColBERT benchmark assertions will skip silently."
    )
    assert "tests/benchmark" in body, (
        "test-benchmark must point pytest at tests/benchmark/."
    )


def test_benchmark_dir_still_listed_in_full_parallel_dirs() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(
        r"^PYTEST_FULL_PARALLEL_DIRS\s*\?=\s*(.+)$",
        text,
        re.MULTILINE,
    )
    assert match is not None, "PYTEST_FULL_PARALLEL_DIRS missing"
    dirs = match.group(1).split()
    assert "tests/benchmark/" in dirs, (
        "tests/benchmark/ must remain in PYTEST_FULL_PARALLEL_DIRS so the "
        "advertised 'all tiers' wording of make test-full stays accurate."
    )
