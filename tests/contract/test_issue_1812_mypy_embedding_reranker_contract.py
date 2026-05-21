"""Contract test for issue ***REMOVED***1812: mypy must not regress on lazy ML singletons.

Two specific mypy errors were observed on a clean ``dev`` checkout (with the
``ml-local`` extra installed so that ``FlagEmbedding`` / ``sentence_transformers``
resolve to real types instead of being silently elided to ``Any``):

* ``src/models/embedding_model.py:98``
  ``error: Returning Any from function declared to return "SentenceTransformer"``
* ``src/retrieval/reranker.py:104``
  ``error: Argument 1 to "predict" of "CrossEncoder" has incompatible type
  "list[tuple[str, Any]]"``

This contract test runs mypy on those two files via subprocess (mirroring the
``make type-check`` invocation of ``uv run mypy ... --ignore-missing-imports``)
and asserts:

1. exit code is 0;
2. the two error substrings (``Returning Any`` and ``CrossEncoder``) are not
   present in stdout/stderr.

The test is skipped only if neither ``uv`` nor a system-level ``mypy`` is
available in the sandbox -- in that case the type check cannot be exercised
and there is nothing meaningful to assert. CI installs the ``dev`` group, so
the test is expected to actually run there.

Refs ***REMOVED***1812.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]

TARGET_FILES = [
    "src/models/embedding_model.py",
    "src/retrieval/reranker.py",
]

FORBIDDEN_SUBSTRINGS = ("Returning Any", "CrossEncoder")


def _resolve_mypy_command() -> list[str] | None:
    """Return an argv prefix that invokes mypy, or ``None`` if unavailable.

    Order of preference:
      1. ``uv run mypy`` -- matches the project's ``make type-check`` target
         and uses the locked dev environment.
      2. ``mypy`` directly from PATH -- fallback for environments where mypy
         is installed globally but ``uv`` is not.
    """
    if shutil.which("uv") is not None:
        return ["uv", "run", "mypy"]
    if shutil.which("mypy") is not None:
        return ["mypy"]
    return None


def test_mypy_clean_on_embedding_model_and_reranker() -> None:
    """mypy must succeed on the two files cited in ***REMOVED***1812."""
    mypy_cmd = _resolve_mypy_command()
    if mypy_cmd is None:
        pytest.skip("Neither `uv` nor `mypy` is available; cannot run ***REMOVED***1812 contract.")

    ***REMOVED*** Mirror Makefile flags so the test reflects what `make type-check` would do.
    argv = [
        *mypy_cmd,
        *TARGET_FILES,
        "--ignore-missing-imports",
        "--no-error-summary",
    ]

    proc = subprocess.run(
        argv,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    combined_output = (proc.stdout or "") + (proc.stderr or "")

    failures: list[str] = []
    if proc.returncode != 0:
        failures.append(f"mypy exit code = {proc.returncode} (expected 0)")

    for needle in FORBIDDEN_SUBSTRINGS:
        if needle in combined_output:
            failures.append(f"mypy output still contains forbidden substring {needle!r}")

    if failures:
        msg_lines = [
            "Issue ***REMOVED***1812 regression: mypy reports errors on the patched files.",
            "Failures:",
            *(f"  - {f}" for f in failures),
            "Full mypy output:",
            combined_output.rstrip() or "<empty>",
        ]
        raise AssertionError("\n".join(msg_lines))
