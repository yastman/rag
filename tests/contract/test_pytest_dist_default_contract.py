"""Contract: global pytest ``--dist`` default must align with the local fast gate (#1796).

`pyproject.toml` previously hard-coded ``--dist=loadscope`` in the global
``[tool.pytest.ini_options].addopts`` block. The canonical local fast-gate
scheduler (Makefile, AGENTS overrides, docs) is ``worksteal``. Any pytest
target using ``-n auto`` without an explicit ``--dist`` then silently
inherited ``loadscope`` from the global default, including
``test-profile`` and ``test-store-durations``. Scheduler comparisons
became invalid because targets were not running the same distribution
strategy.

This contract pins the global default to ``worksteal`` (or to no global
``--dist`` at all, in which case every xdist target must remain
explicit). It also guards the explicit ``test-unit-loadscope`` Makefile
target so the loadscope experiment path is not accidentally removed.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
MAKEFILE = REPO_ROOT / "Makefile"


def _read_global_addopts() -> str:
    """Return the full text of ``[tool.pytest.ini_options].addopts``.

    We parse manually because the value is a triple-quoted multi-line string
    in pyproject.toml, and we want to preserve every flag verbatim.
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    # Match `addopts = """..."""` inside [tool.pytest.ini_options].
    section = re.search(
        r"\[tool\.pytest\.ini_options\](?P<body>.*?)(?:\n\[|\Z)",
        text,
        re.DOTALL,
    )
    assert section is not None, "Missing [tool.pytest.ini_options] in pyproject.toml"
    body = section.group("body")
    addopts = re.search(
        r'addopts\s*=\s*"""(?P<value>.*?)"""',
        body,
        re.DOTALL,
    )
    assert addopts is not None, (
        "Missing addopts triple-quoted string in [tool.pytest.ini_options]"
    )
    return addopts.group("value")


def _extract_dist_flags(addopts_text: str) -> list[str]:
    """Return every ``--dist=<scheduler>`` value found in addopts."""
    tokens = shlex.split(addopts_text)
    values: list[str] = []
    for tok in tokens:
        if tok.startswith("--dist="):
            values.append(tok.split("=", 1)[1])
        elif tok == "--dist":  # space-separated form
            # Defer to next token; xdist supports both shapes
            values.append("__SPACE_SEPARATED__")
    return values


def test_global_pytest_dist_is_worksteal_or_unset() -> None:
    """Global ``--dist`` must be ``worksteal`` (or absent) — never ``loadscope`` (#1796)."""
    addopts = _read_global_addopts()
    dist_values = _extract_dist_flags(addopts)
    if not dist_values:
        # Acceptable: no global default; every xdist target is explicit.
        return
    assert dist_values == ["worksteal"], (
        "Global pytest addopts in pyproject.toml must use --dist=worksteal "
        "to match the canonical Makefile/docs default. Found: "
        f"{dist_values!r}. The explicit loadscope experiment lives in the "
        "'test-unit-loadscope' Makefile target."
    )


def test_makefile_default_parallel_args_is_worksteal() -> None:
    """``PYTEST_PARALLEL_ARGS`` default must remain ``-n auto --dist=worksteal``."""
    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(
        r"^PYTEST_PARALLEL_ARGS\s*\?=\s*(.+)$",
        text,
        re.MULTILINE,
    )
    assert match is not None, "PYTEST_PARALLEL_ARGS default missing in Makefile"
    value = match.group(1).strip()
    assert value == "-n auto --dist=worksteal", (
        f"Makefile PYTEST_PARALLEL_ARGS default drifted: {value!r}. "
        "Expected '-n auto --dist=worksteal'."
    )


def test_loadscope_experiment_target_still_exists() -> None:
    """The opt-in ``test-unit-loadscope`` target must remain available (#1796)."""
    text = MAKEFILE.read_text(encoding="utf-8")
    assert re.search(r"^test-unit-loadscope:", text, re.MULTILINE), (
        "Removing 'test-unit-loadscope' would erase the explicit loadscope "
        "experiment lane. Keep it as the documented opt-in path."
    )
    assert "--dist=loadscope" in text, (
        "test-unit-loadscope must still pass --dist=loadscope explicitly."
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("--dist=worksteal", ["worksteal"]),
        ("-ra --dist=loadscope", ["loadscope"]),
        ("--dist worksteal", ["__SPACE_SEPARATED__"]),
        ("-ra --strict-markers", []),
    ],
)
def test_extract_dist_flags_helper(raw: str, expected: list[str]) -> None:
    assert _extract_dist_flags(raw) == expected
