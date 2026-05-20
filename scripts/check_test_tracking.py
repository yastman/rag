#!/usr/bin/env python3
"""Fail if test files are present in working tree but not tracked by Git."""

from __future__ import annotations

import re
import subprocess  # nosec B404
from pathlib import Path


TEST_FILENAME_RE = re.compile(
    r"(^test_.*\.(py|sh)$)|(\.(test|spec)\.[cm]?[jt]sx?$)",
    re.IGNORECASE,
)


def _repo_root() -> Path:
    result = subprocess.run(  # nosec B603 B607 - fixed local git command, no shell.
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def _git_untracked(repo_root: Path) -> list[Path]:
    result = subprocess.run(  # nosec B603 B607 - fixed local git command, no shell.
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo_root,
    )
    return [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]


def _is_test_path(path: Path) -> bool:
    parts = set(path.parts)
    if "tests" in parts or "__tests__" in parts:
        return True
    return TEST_FILENAME_RE.search(path.name) is not None


def _is_inside_nested_repo(path: Path, repo_root: Path) -> bool:
    current = repo_root / path
    for parent in current.parents:
        if parent == repo_root:
            break
        if (parent / ".git").exists():
            return True
    return False


def find_untracked_tests(repo_root: Path) -> list[Path]:
    offenders: list[Path] = []
    for path in _git_untracked(repo_root):
        if not _is_test_path(path):
            continue
        if _is_inside_nested_repo(path, repo_root):
            continue
        offenders.append(path)
    return sorted(offenders)


def main() -> int:
    root = _repo_root()
    offenders = find_untracked_tests(root)
    if not offenders:
        print("OK: no untracked test files found")
        return 0

    print("Found untracked test files. Add or ignore them explicitly:")
    for path in offenders:
        print(f" - {path.as_posix()}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
