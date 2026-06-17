"""Contract: live E2E cache test must FAIL on missing transitions, not skip (#1630).

``test_core_flows_live.py`` was removed in #2696 (stale RAG API surface cleanup).
The current live E2E path is ``tests/e2e/test_core_live_ingest_answer.py``.

This contract file is retained as a tombstone so git history stays readable and
so that any future re-introduction of a cache-transition test in the active e2e
suite can be validated here.

Original contract rules (preserved for reference):

1. Inside ``test_cache_miss_then_hit_on_repeated_query``, a ``pytest.skip(...)``
   call may only appear BEFORE the live-stack preflight returns successfully
   (or as the preflight itself via ``_require_live_stack``). After the
   queries have run, the missing transition must be expressed as an
   ``assert``.

2. The test must contain an ``assert`` that requires both
   ``hits >= 1`` (or ``> 0``) and ``misses >= 1`` (or ``> 0``).
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STALE_TARGET = REPO_ROOT / "tests" / "e2e" / "test_core_flows_live.py"


def test_stale_api_e2e_file_removed() -> None:
    """test_core_flows_live.py must not exist after #2696 cleanup."""
    assert not STALE_TARGET.exists(), (
        f"{STALE_TARGET.relative_to(REPO_ROOT)} was re-introduced. "
        "This file targets the archived RAG API surface and must not be "
        "part of the active test suite. Archive or rewrite it to target "
        "the current core live entrypoint (test_core_live_ingest_answer.py)."
    )
