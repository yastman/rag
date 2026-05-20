***REMOVED***!/usr/bin/env python3
"""Ratchet check for duplicate test function names across the test suite (***REMOVED***1539).

pytest-xdist routes tests across workers and may silently merge or skip
identically-named tests living in different files. This script walks
``tests/`` and refuses to introduce **new** duplicate names while a
known-allowlist of pre-existing duplicates is gradually shrunk by hand.

Usage:
    python scripts/check_unique_test_names.py            ***REMOVED*** check
    python scripts/check_unique_test_names.py --regenerate  ***REMOVED*** regenerate allowlist

The check is wired into the test suite via
``tests/contract/test_no_new_duplicate_test_names.py``.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO_ROOT / "tests"
ALLOWLIST_PATH = TESTS_DIR / "data" / "known_duplicate_test_names.json"


def collect_test_function_names() -> dict[str, list[str]]:
    """Return ``{function_name: [relative_file_paths]}`` for every duplicate.

    Functions whose names start with ``test_`` are collected regardless of
    enclosing class. Files that fail to parse are skipped (we only care
    about real, collected tests).
    """
    buckets: dict[str, list[str]] = defaultdict(list)
    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(errors="ignore"))
        except SyntaxError:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test_"
            ):
                buckets[node.name].append(rel)
    return {name: sorted(set(files)) for name, files in buckets.items() if len(set(files)) > 1}


def load_allowlist() -> dict[str, list[str]]:
    if not ALLOWLIST_PATH.exists():
        return {}
    return json.loads(ALLOWLIST_PATH.read_text())


def write_allowlist(payload: dict[str, list[str]]) -> None:
    ALLOWLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALLOWLIST_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )


def diff_against_allowlist(
    current: dict[str, list[str]], allowlist: dict[str, list[str]]
) -> tuple[dict[str, list[str]], dict[str, tuple[list[str], list[str]]]]:
    """Return ``(new_duplicates, expanded_duplicates)``.

    - ``new_duplicates``: names that became duplicate but weren't in the allowlist.
    - ``expanded_duplicates``: known names whose file list grew (more dupes added).
    """
    new_dupes: dict[str, list[str]] = {}
    expanded: dict[str, tuple[list[str], list[str]]] = {}
    for name, files in current.items():
        if name not in allowlist:
            new_dupes[name] = files
            continue
        previous = set(allowlist[name])
        added = [f for f in files if f not in previous]
        if added:
            expanded[name] = (sorted(previous), sorted(set(files)))
    return new_dupes, expanded


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Overwrite the allowlist with the current set of duplicates (use after manual cleanup).",
    )
    args = parser.parse_args()

    current = collect_test_function_names()

    if args.regenerate:
        write_allowlist(current)
        print(
            f"Wrote allowlist with {len(current)} duplicate names to "
            f"{ALLOWLIST_PATH.relative_to(REPO_ROOT)}",
        )
        return 0

    allowlist = load_allowlist()
    new_dupes, expanded = diff_against_allowlist(current, allowlist)

    if not new_dupes and not expanded:
        print(
            f"OK: {len(current)} known duplicate test names; no new duplicates introduced. "
            f"Existing duplicates are tracked in {ALLOWLIST_PATH.relative_to(REPO_ROOT)} "
            "and should be renamed incrementally (see ***REMOVED***1539).",
        )
        return 0

    print("FAIL: new duplicate test function names detected (***REMOVED***1539 ratchet).", file=sys.stderr)
    if new_dupes:
        print("\nNew duplicate names (must be renamed):", file=sys.stderr)
        for name, files in sorted(new_dupes.items()):
            print(f"  {name}", file=sys.stderr)
            for f in files:
                print(f"    - {f}", file=sys.stderr)
    if expanded:
        print(
            "\nExisting duplicate names that now appear in MORE files "
            "(rename the new occurrence rather than copying the duplicate):",
            file=sys.stderr,
        )
        for name, (prev, now) in sorted(expanded.items()):
            added = sorted(set(now) - set(prev))
            print(f"  {name} (added: {', '.join(added)})", file=sys.stderr)

    print(
        "\nFix options:\n"
        "  - Rename your new test to be unique (preferred), e.g. "
        "test_<feature>_<scenario_specific>.\n"
        "  - If the duplicate is intentional and unavoidable, regenerate the allowlist "
        "with: python scripts/check_unique_test_names.py --regenerate",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
