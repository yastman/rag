"""Contract: fast pytest Makefile targets must honour $(PYTEST_PARALLEL_ARGS).

Background (issue #1794)
------------------------
On memory-constrained WSL2/Docker Desktop hosts (~8 GiB) the local fast
gate killed pytest-xdist workers with `Error 137` because the Makefile
hard-coded ``-n auto --dist=worksteal`` for the most common fast targets.
``PYTEST_PARALLEL_ARGS`` was already defined as a ``?=`` override point,
but only ``test-full`` consumed it. This contract pins the override
surface so future fast-lane targets stay overridable too::

    PYTEST_PARALLEL_ARGS="-n 2 --dist=worksteal" make test-unit

Targets covered:
- ``test``               (PR/local fast gate)
- ``test-unit``          (canonical core unit lane)
- ``test-unit-loadscope`` (loadscope is intentionally explicit; see note)
- ``test-fast``
- ``test-all-fast``
- ``test-profile``
- ``test-store-durations``

The default value of ``PYTEST_PARALLEL_ARGS`` must remain
``-n auto --dist=worksteal`` so existing local/CI behaviour is preserved
out of the box. ``test-unit-loadscope`` is the documented loadscope
experiment lane — it must keep ``--dist=loadscope`` explicit and is
therefore exempt from the ``$(PYTEST_PARALLEL_ARGS)`` rule but is still
required to use ``-n auto`` (or an override).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"

PARALLEL_VAR = "$(PYTEST_PARALLEL_ARGS)"

# Targets that must consume $(PYTEST_PARALLEL_ARGS) so a local override
# (`-n 2 --dist=worksteal`) flows through.
OVERRIDABLE_TARGETS = (
    "test",
    "test-unit",
    "test-fast",
    "test-all-fast",
    "test-profile",
    "test-store-durations",
)


def _read_makefile_text() -> str:
    assert MAKEFILE.exists(), f"Makefile missing at {MAKEFILE}"
    return MAKEFILE.read_text(encoding="utf-8")


def _extract_recipe(makefile_text: str, target: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(target)}:[^\n]*\n((?:\t.*\n|\n)*?)(?=^[A-Za-z0-9_./%-]+:|^\Z)",
        re.MULTILINE,
    )
    match = pattern.search(makefile_text)
    assert match, f"Target `{target}` not found in Makefile"
    return match.group(1)


def _pytest_invocation(recipe: str) -> str:
    lines = []
    in_pytest = False
    for raw in recipe.splitlines():
        line = raw.lstrip("\t")
        if "uv run pytest" in line or "pytest tests/" in line:
            in_pytest = True
            lines.append(line)
            if not line.rstrip().endswith("\\"):
                break
            continue
        if in_pytest:
            lines.append(line)
            if not line.rstrip().endswith("\\"):
                break
    assert lines, f"No pytest invocation found in recipe:\n{recipe}"
    return " ".join(s.rstrip(" \\").strip() for s in lines)


@pytest.mark.parametrize("target", OVERRIDABLE_TARGETS)
def test_target_uses_parallel_args_variable(target: str) -> None:
    """Each fast-lane target must consume $(PYTEST_PARALLEL_ARGS).

    This is what lets a memory-constrained host opt into bounded workers
    (e.g. ``PYTEST_PARALLEL_ARGS='-n 2 --dist=worksteal'``).
    """
    text = _read_makefile_text()
    recipe = _extract_recipe(text, target)
    invocation = _pytest_invocation(recipe)
    assert PARALLEL_VAR in invocation, (
        f"Target `{target}` must include `{PARALLEL_VAR}` so callers can "
        f"override worker count on memory-constrained hosts. Found:\n"
        f"  {invocation}"
    )


@pytest.mark.parametrize("target", OVERRIDABLE_TARGETS)
def test_target_does_not_hardcode_worker_flags(target: str) -> None:
    """Once $(PYTEST_PARALLEL_ARGS) is in use, raw -n/--dist must be removed.

    Otherwise the override silently loses to the hard-coded flag.
    """
    text = _read_makefile_text()
    recipe = _extract_recipe(text, target)
    invocation = _pytest_invocation(recipe)
    # Strip the variable itself before scanning for raw flags.
    scrubbed = invocation.replace(PARALLEL_VAR, "")
    assert " -n " not in f" {scrubbed} ", (
        f"Target `{target}` still hard-codes `-n` outside of "
        f"`{PARALLEL_VAR}`. The override is silently shadowed.\n"
        f"  {invocation}"
    )
    assert "--dist=" not in scrubbed, (
        f"Target `{target}` still hard-codes `--dist=` outside of "
        f"`{PARALLEL_VAR}`. The override is silently shadowed.\n"
        f"  {invocation}"
    )


def test_parallel_args_default_remains_worksteal() -> None:
    """The default must stay `-n auto --dist=worksteal` for backwards-compat.

    Existing local/CI runs that rely on the implicit default must keep
    behaving the same when no override is exported.
    """
    text = _read_makefile_text()
    match = re.search(
        r"^PYTEST_PARALLEL_ARGS\s*\?=\s*(.+?)$", text, re.MULTILINE
    )
    assert match, "PYTEST_PARALLEL_ARGS must be defined with `?=` so callers can override it"
    default = match.group(1).strip()
    assert default == "-n auto --dist=worksteal", (
        f"Default PYTEST_PARALLEL_ARGS changed unexpectedly. The contract "
        f"requires the historical default so unconfigured hosts behave as "
        f"before.\n  expected: '-n auto --dist=worksteal'\n  got:      '{default}'"
    )


def test_loadscope_target_remains_explicit() -> None:
    """test-unit-loadscope must keep `--dist=loadscope` explicit.

    Per repo convention this is the opt-in loadscope experiment lane and
    must NOT be folded into $(PYTEST_PARALLEL_ARGS).
    """
    text = _read_makefile_text()
    recipe = _extract_recipe(text, "test-unit-loadscope")
    invocation = _pytest_invocation(recipe)
    assert "--dist=loadscope" in invocation, (
        "test-unit-loadscope is the documented loadscope experiment lane "
        "and must keep `--dist=loadscope` explicit even after #1794."
    )
