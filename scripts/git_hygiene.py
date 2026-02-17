#!/usr/bin/env python3
"""Git hygiene report and cleanup tool.

Scans the repository for:
- Branches merged to origin/main
- Branches without upstream tracking
- Detached or /tmp worktrees
- Untracked transient files (coverage.json, test_output*, *.log)

Usage:
    python scripts/git_hygiene.py          # Human-readable report
    python scripts/git_hygiene.py --json   # JSON output
    python scripts/git_hygiene.py --fix    # Auto-cleanup merged branches
    python scripts/git_hygiene.py --fix --dry-run  # Preview cleanup
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field


@dataclass
class HygieneReport:
    """Aggregated hygiene findings."""

    merged_branches: list[str] = field(default_factory=list)
    no_upstream_branches: list[str] = field(default_factory=list)
    stale_worktrees: list[dict[str, str]] = field(default_factory=list)
    transient_files: list[str] = field(default_factory=list)

    @property
    def total_issues(self) -> int:
        return (
            len(self.merged_branches)
            + len(self.no_upstream_branches)
            + len(self.stale_worktrees)
            + len(self.transient_files)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "merged_branches": self.merged_branches,
            "no_upstream_branches": self.no_upstream_branches,
            "stale_worktrees": self.stale_worktrees,
            "transient_files": self.transient_files,
            "total_issues": self.total_issues,
        }


def _run(cmd: list[str], *, check: bool = True) -> str:
    """Run a git command and return stripped stdout."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
    )
    return result.stdout.strip()


def find_merged_branches() -> list[str]:
    """Find local branches already merged into origin/main."""
    # Fetch latest remote state silently
    subprocess.run(
        ["git", "fetch", "--prune"],
        capture_output=True,
        check=False,
    )
    raw = _run(["git", "branch", "--merged", "origin/main", "--format=%(refname:short)"])
    if not raw:
        return []
    protected = {"main", "master", "develop"}
    return [b for b in raw.splitlines() if b.strip() not in protected]


def find_no_upstream_branches() -> list[str]:
    """Find local branches with no upstream tracking branch."""
    raw = _run(
        [
            "git",
            "for-each-ref",
            "--format=%(refname:short) %(upstream)",
            "refs/heads/",
        ]
    )
    if not raw:
        return []
    result: list[str] = []
    for line in raw.splitlines():
        parts = line.split(maxsplit=1)
        branch = parts[0]
        upstream = parts[1] if len(parts) > 1 else ""
        if not upstream:
            result.append(branch)
    return result


def find_stale_worktrees() -> list[dict[str, str]]:
    """Find worktrees that are detached or reside in /tmp."""
    raw = _run(["git", "worktree", "list", "--porcelain"])
    if not raw:
        return []

    stale: list[dict[str, str]] = []
    current: dict[str, str] = {}

    for line in raw.splitlines():
        if line.startswith("worktree "):
            current = {"path": line.split(" ", 1)[1]}
        elif line == "detached":
            current["reason"] = "detached HEAD"
        elif line == "bare":
            current["reason"] = "bare"
        elif line == "":
            if current:
                path = current.get("path", "")
                if current.get("reason") or path.startswith("/tmp"):
                    if path.startswith("/tmp") and "reason" not in current:
                        current["reason"] = "in /tmp"
                    stale.append(current)
            current = {}

    # Handle last entry
    if current:
        path = current.get("path", "")
        if current.get("reason") or path.startswith("/tmp"):
            if path.startswith("/tmp") and "reason" not in current:
                current["reason"] = "in /tmp"
            stale.append(current)

    return stale


def find_transient_files() -> list[str]:
    """Find untracked transient files (coverage, test output, logs).

    Uses ``git ls-files --others --exclude-standard`` so that tracked files
    and files matched by ``.gitignore`` are excluded.  This also avoids
    expensive filesystem walks through ``.venv/`` or ``node_modules/``.
    """
    raw = _run(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "coverage.json",
            "test_output*",
            "*.log",
        ],
        check=False,
    )
    return sorted(raw.splitlines()) if raw else []


def build_report() -> HygieneReport:
    """Build a complete hygiene report."""
    return HygieneReport(
        merged_branches=find_merged_branches(),
        no_upstream_branches=find_no_upstream_branches(),
        stale_worktrees=find_stale_worktrees(),
        transient_files=find_transient_files(),
    )


def print_human_report(report: HygieneReport) -> None:
    """Print a human-readable summary."""
    print("=== Git Hygiene Report ===\n")

    # Merged branches
    print(f"Merged branches ({len(report.merged_branches)}):")
    if report.merged_branches:
        for b in report.merged_branches:
            print(f"  - {b}")
    else:
        print("  (none)")

    # No upstream
    print(f"\nBranches without upstream ({len(report.no_upstream_branches)}):")
    if report.no_upstream_branches:
        for b in report.no_upstream_branches:
            print(f"  - {b}")
    else:
        print("  (none)")

    # Stale worktrees
    print(f"\nStale worktrees ({len(report.stale_worktrees)}):")
    if report.stale_worktrees:
        for wt in report.stale_worktrees:
            print(f"  - {wt['path']} ({wt.get('reason', 'unknown')})")
    else:
        print("  (none)")

    # Transient files
    print(f"\nTransient files ({len(report.transient_files)}):")
    if report.transient_files:
        for f in report.transient_files:
            print(f"  - {f}")
    else:
        print("  (none)")

    print(f"\nTotal issues: {report.total_issues}")


def fix_merged_branches(
    branches: list[str], *, dry_run: bool = False, quiet: bool = False
) -> list[str]:
    """Delete branches merged to origin/main. Returns list of deleted branches."""
    deleted: list[str] = []
    for branch in branches:
        if dry_run:
            if not quiet:
                print(f"  [dry-run] would delete: {branch}")
            deleted.append(branch)
        else:
            result = subprocess.run(
                ["git", "branch", "-d", branch],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                if not quiet:
                    print(f"  deleted: {branch}")
                deleted.append(branch)
            elif not quiet:
                print(f"  FAILED to delete {branch}: {result.stderr.strip()}")
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Git hygiene report and cleanup tool",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-cleanup merged branches (conservative: only merged to origin/main)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview cleanup actions without executing (use with --fix)",
    )
    args = parser.parse_args()

    if args.dry_run and not args.fix:
        parser.error("--dry-run requires --fix")

    report = build_report()

    if args.fix:
        if not args.json:
            print("=== Git Hygiene Cleanup ===\n")
        if report.merged_branches:
            if not args.json:
                label = "dry-run" if args.dry_run else "cleanup"
                print(f"Merged branches ({label}):")
            fix_merged_branches(
                report.merged_branches,
                dry_run=args.dry_run,
                quiet=args.json,
            )
        elif not args.json:
            print("No merged branches to clean up.")
        if not args.json:
            print()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_human_report(report)

    sys.exit(0 if report.total_issues == 0 else 1)


if __name__ == "__main__":
    main()
