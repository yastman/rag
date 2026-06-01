# tests/contract/test_makefile_python_version_contract.py
"""Contract: Makefile pytest targets must route through a pinned Python runtime.

Closes #1792.

Problem reproduced: running ``uv run pytest`` without ``--python`` could select
CPython 3.14 on WSL/Linux hosts where multiple interpreters are available.
``voyageai`` (and other C-extension packages) fail with pydantic.v1 under
3.14, breaking collection before any test runs.

This contract pins three things:
1. A ``PYTHON_VERSION`` override variable exists in the Makefile with a
   default of ``3.12``.
2. Every fast pytest target routes through ``uv run --python $(PYTHON_VERSION)``
   (or equivalent variable) rather than bare ``uv run pytest``.
3. The ``PYTHON_VERSION`` default is exactly ``3.12``.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
PYTHON_VERSION_FILE = REPO_ROOT / ".python-version"

# Fast targets that must use the pinned runtime.
FAST_TARGETS = [
    "test-unit",
    "test-unit-loadscope",
    "test",
    "test-fast",
    "test-all-fast",
    "test-profile",
    "test-store-durations",
]


def _read_makefile() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def test_python_version_variable_defined() -> None:
    """``PYTHON_VERSION ?= 3.12`` must be present in the Makefile."""
    src = _read_makefile()
    # Accept either bare assignment or the default-override form.
    assert re.search(r"PYTHON_VERSION\s*\?=\s*3\.12", src), (
        "Makefile must define PYTHON_VERSION ?= 3.12 so local pytest targets "
        "can be overridden without editing the file."
    )


def test_python_version_default_is_312() -> None:
    """The default value of PYTHON_VERSION must be exactly '3.12'."""
    src = _read_makefile()
    m = re.search(r"PYTHON_VERSION\s*\?=\s*(\S+)", src)
    assert m is not None, "PYTHON_VERSION variable not found"
    assert m.group(1) == "3.12", f"PYTHON_VERSION default must be 3.12, got {m.group(1)!r}"


def test_repo_python_version_file_pins_uv_default_to_312() -> None:
    """Bare ``uv sync`` must not select a newer installed interpreter.

    Without a repo-level ``.python-version``, uv can pick CPython 3.14 on
    machines that have it installed. That forces packages such as ``grpcio``
    down the source-build path when the pinned version has no cp314 wheel.
    """
    assert PYTHON_VERSION_FILE.exists(), (
        "Repository must include .python-version so bare `uv sync` uses the "
        "same Python as Makefile fast gates instead of selecting newer local "
        "interpreters."
    )
    assert PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip() == "3.12"


def test_uv_run_no_sync_variable_is_uv_run() -> None:
    """``UV_RUN_NO_SYNC`` must remain an uv-run wrapper for fast local gates."""
    src = _read_makefile()
    assert re.search(r"UV_RUN_NO_SYNC\s*\?=\s*uv run --no-sync", src), (
        "Makefile must define UV_RUN_NO_SYNC ?= uv run --no-sync so local "
        "fast pytest targets avoid mutating the shared venv during xdist runs."
    )


def _target_body(src: str, target: str) -> str:
    """Extract the recipe lines for *target* from the Makefile source.

    Returns the block from the target header up to (but not including) the
    next non-indented line.
    """
    # Find the target header line.
    pattern = re.compile(r"^" + re.escape(target) + r"\s*:", re.MULTILINE)
    m = pattern.search(src)
    if m is None:
        return ""
    start = m.start()
    # Recipe lines are indented with a tab; collect until a non-tab line.
    body_lines = []
    for line in src[start:].splitlines()[1:]:
        if line.startswith("\t") or line.strip() == "":
            body_lines.append(line)
        else:
            break
    return "\n".join(body_lines)


def test_fast_targets_use_pinned_python() -> None:
    """Every fast pytest target must invoke pytest via the pinned Python.

    Accepts both ``uv run --python $(PYTHON_VERSION) pytest`` and
    ``uv run --python $(PYTHON_VERSION) python -m pytest`` patterns.
    """
    src = _read_makefile()
    # Pattern: uv run --python <something> ... pytest, or an equivalent
    # variable wrapper such as $(UV_RUN_NO_SYNC) --python <something>.
    pinned_pattern = re.compile(
        r"(?:uv run|\$\(UV_RUN_NO_SYNC\))\s+--python\s+\$\(PYTHON_VERSION\)"
    )
    # Bare uv run pytest (NOT pinned) — to detect violations.
    bare_pattern = re.compile(r"\buv run pytest\b")

    failures = []
    for target in FAST_TARGETS:
        body = _target_body(src, target)
        if not body:
            failures.append(f"{target}: target not found in Makefile")
            continue
        has_pinned = bool(pinned_pattern.search(body))
        has_bare = bool(bare_pattern.search(body))
        if not has_pinned:
            failures.append(
                f"{target}: recipe does not use 'uv run --python $(PYTHON_VERSION) pytest'"
            )
        if has_bare:
            failures.append(
                f"{target}: recipe still contains bare 'uv run pytest' "
                f"(not pinned to PYTHON_VERSION)"
            )

    assert not failures, (
        "The following Makefile targets violate the Python-version pin:\n"
        + "\n".join(f"  - {f}" for f in failures)
    )
