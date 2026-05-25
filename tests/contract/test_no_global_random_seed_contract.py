"""Contract test for issue #2071 — bare `random.seed(...)` is forbidden in tests.

Issue #1515 audit S3 flagged `random.seed(...)` calls inside test bodies as
xdist-unsafe: the global `random` module state is shared across the entire
process, so a parallel worker can land on a test mid-`seed`/`getstate` window
and observe non-deterministic state. The accepted remediation in #2071 is
to either:

* use a local `random.Random(seed)` instance (preferred), or
* wrap the global mutation in a save/restore block via `random.getstate()` /
  `random.setstate()` (acceptable when the function under test consumes the
  global module, e.g. `random.choice` / `random.randint`).

This contract test asserts that no test file calls `random.seed(...)`
WITHOUT the save/restore guard. That keeps the door open for legitimate uses
(seeding a global generator that someone else is going to consume) while
catching the unsafe pattern.

The test is text-based and intentionally conservative: it counts the number
of `random.seed(...)` occurrences and the number of `random.getstate()`
occurrences in each file, and fails when `seed > getstate`. Cleaner
encapsulation (a `frozen_random_seed` fixture) is welcome but not required.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _all_test_python_files() -> list[Path]:
    skip = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
    out: list[Path] = []
    for py in (REPO / "tests").rglob("*.py"):
        if any(part in skip for part in py.parts):
            continue
        if py.name == __name__.rsplit(".", 1)[-1] + ".py":
            continue
        out.append(py)
    return out


SEED_RE = re.compile(r"\brandom\.seed\s*\(")
GETSTATE_RE = re.compile(r"\brandom\.getstate\s*\(")


def test_no_unguarded_random_seed_in_test_files() -> None:
    offenders: list[str] = []
    for path in _all_test_python_files():
        text = path.read_text(encoding="utf-8")
        seed_count = len(SEED_RE.findall(text))
        if seed_count == 0:
            continue
        getstate_count = len(GETSTATE_RE.findall(text))
        if seed_count > getstate_count:
            offenders.append(
                f"{path.relative_to(REPO)}: random.seed×{seed_count}, "
                f"random.getstate×{getstate_count}"
            )

    assert offenders == [], (
        "Test files contain unguarded random.seed(...) calls (issue #2071). "
        "Either wrap each seed call with random.getstate()/setstate() to "
        "isolate the global random state, or use a local random.Random(seed) "
        "instance.\n  " + "\n  ".join(offenders)
    )
