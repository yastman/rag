"""Contract: pre-existing exact-duplicate test files removed (#1996).

Three integration test files were byte-identical copies of unit-test files.
They were removed in PR #1996 to stop pytest-xdist from silently merging or
skipping identically-named tests living under different paths and to shrink
the ratchet allowlist in ``tests/data/known_duplicate_test_names.json``.

The duplicate integration paths must remain absent. Of their original
unit-tier counterparts, only ``tests/unit/test_redis_url.py`` remains:
the Voyage integration test was removed with the dead Voyage dependency,
and the contextual integration test was removed with the dead contextual
loader. Those later removals do not weaken the #1996 deduplication invariant.

If new tests genuinely need to live under ``tests/integration/``, give them
unique filenames; do not re-introduce the same module name.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

DELETED_DUPLICATES = (
    "tests/integration/test_voyage_integration.py",
    "tests/integration/test_contextual_integration.py",
    "tests/integration/test_redis_url.py",
)

CANONICAL_KEPT = ("tests/unit/test_redis_url.py",)


def test_duplicate_integration_test_files_are_absent() -> None:
    for rel in DELETED_DUPLICATES:
        assert not (REPO_ROOT / rel).exists(), (
            f"#1996: {rel} was a byte-identical duplicate of a unit test and "
            "must stay removed. Rename your new test if you need an "
            "integration-tier copy."
        )


def test_canonical_unit_test_files_are_present() -> None:
    for rel in CANONICAL_KEPT:
        assert (REPO_ROOT / rel).exists(), (
            f"#1996: canonical kept test path {rel} is missing. The "
            "deduplication PR must keep the unit-tier file as the single "
            "source of truth."
        )
