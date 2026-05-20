"""Sentinel test: forbid NEW duplicate test function names across the suite (***REMOVED***1539).

pytest-xdist may silently merge or skip identically-named tests living in
different files. We track the current 177 duplicate names in
``tests/data/known_duplicate_test_names.json`` (a ratchet allowlist) and
fail this contract when a developer adds a new duplicate or grows an
existing one. The allowlist must shrink over time; do not regenerate it
to "fix" a CI failure.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_unique_test_names.py"
ALLOWLIST = REPO_ROOT / "tests" / "data" / "known_duplicate_test_names.json"


def test_no_new_duplicate_test_function_names():
    """Run ``scripts/check_unique_test_names.py`` and assert exit code 0.

    The script:
      - walks ``tests/`` and collects every ``test_*`` function name across files;
      - diffs against ``tests/data/known_duplicate_test_names.json`` (the ratchet);
      - exits 0 only when no new duplicate name was introduced AND no allowlisted
        name appeared in MORE files than before.
    """
    assert SCRIPT.exists(), f"missing helper script: {SCRIPT}"
    assert ALLOWLIST.exists(), f"missing ratchet allowlist: {ALLOWLIST}"

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        ***REMOVED*** Surface the script's stderr as the test failure message so the
        ***REMOVED*** developer sees exactly which names need renaming.
        msg = (
            "Duplicate test name ratchet failed (***REMOVED***1539). "
            "Rename your new test to be unique. "
            "DO NOT regenerate the allowlist to silence this:\n\n" + result.stderr
        )
        raise AssertionError(msg)


def test_known_duplicates_allowlist_is_well_formed():
    """The allowlist must be valid JSON of shape {name: [paths]} with len(paths) >= 2."""
    payload = json.loads(ALLOWLIST.read_text())
    assert isinstance(payload, dict), "allowlist must be a JSON object"
    for name, files in payload.items():
        assert isinstance(name, str) and name.startswith("test_"), (
            f"allowlist key {name!r} must start with 'test_'"
        )
        assert isinstance(files, list) and len(files) >= 2, (
            f"allowlist value for {name!r} must be a list of >=2 paths"
        )
        assert all(isinstance(f, str) for f in files), (
            f"allowlist value for {name!r} must contain only string paths"
        )
        assert len(set(files)) == len(files), (
            f"allowlist for {name!r} must not contain duplicate paths"
        )
