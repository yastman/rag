#!/usr/bin/env python3
"""Ratchet check for duplicate test function names across TRACKED tests (#1539, #3243).

pytest-xdist routes tests across workers and may silently merge or skip
identically-named tests living in different files. This script enumerates the
authoritative test suite from Git (``git ls-files``), collects every ``test_*``
function defined in tracked ``tests/**/test_*.py`` modules, and refuses to
introduce **new** duplicate names while a known-allowlist of pre-existing
duplicates shrinks incrementally.

The ratchet is anchored to git-tracked paths only (#3243):

  - untracked scratch files can never create, grow, or mask a duplicate;
  - every allowlist entry must point at real, tracked occurrences. An entry
    whose path is not tracked (deleted or never committed) or whose file no
    longer defines the symbol is a **stale allowance** and fails loudly
    instead of silently widening the ratchet.

Usage:
    python scripts/check_unique_test_names.py               # check
    python scripts/check_unique_test_names.py --regenerate  # regenerate allowlist

The check is wired into the test suite via
``tests/contract/test_no_new_duplicate_test_names.py``.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast


REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_REL = "tests/data/known_duplicate_test_names.json"


@dataclass(frozen=True)
class Violation:
    """One concrete reason the ratchet failed, naming exact files/symbols."""

    kind: str  # "new" | "expanded" | "untracked_path" | "missing_symbol" | "not_duplicate"
    name: str
    detail: str


def tracked_test_files(repo_root: Path) -> list[str]:
    """Return repo-relative posix paths of git-tracked ``tests/**/test_*.py`` modules.

    Git is the source of truth (#3243): files that are untracked, deleted from
    the index, or merely present in the worktree are excluded.
    """
    result = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "--", "tests"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git ls-files failed in {repo_root} (exit {result.returncode}): {result.stderr.strip()}"
        )
    files: list[str] = []
    for line in result.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        posix = PurePosixPath(rel)
        if posix.name.startswith("test_") and posix.suffix == ".py":
            files.append(rel)
    return sorted(files)


def collect_occurrences(repo_root: Path, tracked_files: list[str]) -> dict[str, list[str]]:
    """Return ``{function_name: [repo-relative files]}`` for tracked test functions.

    Functions whose names start with ``test_`` are collected regardless of
    enclosing class. Tracked files that fail to parse are skipped (we only
    care about real, collectable tests).
    """
    buckets: dict[str, list[str]] = defaultdict(list)
    for rel in tracked_files:
        try:
            tree = ast.parse((repo_root / rel).read_text(errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test_"
            ):
                buckets[node.name].append(rel)
    return {name: sorted(set(files)) for name, files in buckets.items()}


def duplicate_names(occurrences: dict[str, list[str]]) -> dict[str, list[str]]:
    """Filter occurrences down to names defined in more than one tracked file."""
    return {name: files for name, files in occurrences.items() if len(files) > 1}


def check_ratchet(
    occurrences: dict[str, list[str]],
    duplicates: dict[str, list[str]],
    allowlist: dict[str, list[str]],
    tracked_files: list[str],
) -> list[Violation]:
    """Diff the tracked duplicates against the allowlist and return violations.

    Fails on:
      - ``new``: a name duplicated across tracked files but absent from the allowlist;
      - ``expanded``: an allowlisted name that now also occurs in more files;
      - ``untracked_path``: an allowlist path that is not a git-tracked test file;
      - ``missing_symbol``: an allowlisted file that no longer defines the symbol;
      - ``not_duplicate``: an allowlist name with fewer than two valid occurrences.
    """
    violations: list[Violation] = []
    tracked = set(tracked_files)

    for name, files in sorted(duplicates.items()):
        if name not in allowlist:
            violations.append(Violation("new", name, f"duplicated across: {', '.join(files)}"))
            continue
        added = sorted(set(files) - set(allowlist[name]))
        if added:
            violations.append(Violation("expanded", name, f"new occurrences: {', '.join(added)}"))

    for name, allowed_paths in sorted(allowlist.items()):
        defined_in = set(occurrences.get(name, ()))
        valid = 0
        for rel in allowed_paths:
            if rel not in tracked:
                violations.append(
                    Violation(
                        "untracked_path",
                        name,
                        f"{rel} is not a git-tracked test file",
                    )
                )
            elif rel not in defined_in:
                violations.append(
                    Violation(
                        "missing_symbol",
                        name,
                        f"{rel} no longer defines {name}()",
                    )
                )
            else:
                valid += 1
        if valid < 2:
            violations.append(
                Violation(
                    "not_duplicate",
                    name,
                    f"only {valid} valid tracked occurrence(s) "
                    f"({', '.join(sorted(set(allowed_paths) & defined_in)) or 'none'}); "
                    "the name is no longer a tracked duplicate",
                )
            )
    return violations


def render_violations(violations: list[Violation]) -> str:
    """Render violations as a grouped, actionable failure report."""
    headers = {
        "new": "New duplicate names (must be renamed):",
        "expanded": (
            "Allowlisted duplicate names that now appear in MORE files "
            "(rename the new occurrence rather than copying the duplicate):"
        ),
        "untracked_path": (
            "Stale allowlist entries pointing at untracked/deleted paths "
            "(remove the path or the whole entry from the allowlist):"
        ),
        "missing_symbol": (
            "Stale allowlist entries whose file no longer defines the symbol "
            "(remove the path or the whole entry from the allowlist):"
        ),
        "not_duplicate": (
            "Allowlist names that are no longer tracked duplicates "
            "(remove the whole entry from the allowlist):"
        ),
    }
    order = ["new", "expanded", "untracked_path", "missing_symbol", "not_duplicate"]
    lines: list[str] = []
    for kind in order:
        group = [v for v in violations if v.kind == kind]
        if not group:
            continue
        lines.append("")
        lines.append(headers[kind])
        for v in sorted(group, key=lambda v: (v.name, v.detail)):
            if kind in ("new", "expanded"):
                lines.append(f"  {v.name}: {v.detail}")
            else:
                lines.append(f"  {v.name} -> {v.detail}")
    lines.append("")
    lines.append(
        "Fix options:\n"
        "  - Rename your new test to be unique (preferred), e.g. "
        "test_<feature>_<scenario_specific>.\n"
        "  - Prune stale allowances narrowly: edit "
        f"{ALLOWLIST_REL} and delete only the offending entry/path.\n"
        "  - To rebuild the baseline from tracked tests after manual cleanup: "
        "python scripts/check_unique_test_names.py --regenerate"
    )
    return "\n".join(lines)


def allowlist_path(repo_root: Path) -> Path:
    return repo_root / ALLOWLIST_REL


def load_allowlist(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    return cast("dict[str, list[str]]", json.loads(path.read_text()))


def write_allowlist(path: Path, payload: dict[str, list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository to check (defaults to the checkout containing this script).",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Overwrite the allowlist with the current set of tracked duplicates "
        "(use after manual cleanup).",
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    allowlist_file = allowlist_path(repo_root)

    tracked = tracked_test_files(repo_root)
    occurrences = collect_occurrences(repo_root, tracked)
    current = duplicate_names(occurrences)

    if args.regenerate:
        write_allowlist(allowlist_file, current)
        print(
            f"Wrote allowlist with {len(current)} duplicate names to {ALLOWLIST_REL}",
        )
        return 0

    allowlist = load_allowlist(allowlist_file)
    violations = check_ratchet(occurrences, current, allowlist, tracked)

    if not violations:
        print(
            f"OK: {len(current)} known duplicate test names across "
            f"{len(tracked)} tracked test modules; no new duplicates and no "
            f"stale allowances. Existing duplicates are tracked in "
            f"{ALLOWLIST_REL} and should be renamed incrementally (see #1539)."
        )
        return 0

    print(
        "FAIL: duplicate test name ratchet violated (#1539 ratchet, #3243 tracked paths).",
        file=sys.stderr,
    )
    print(render_violations(violations), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
