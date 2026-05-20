#!/usr/bin/env python3
"""Git hygiene report and safe cleanup tool.

Classifies every local branch and worktree into one of three lanes:

- ``safe-to-delete``   : merged into the configured base branch, has upstream,
                         is not the current branch, and is not attached to a
                         dirty or ``/tmp`` worktree.
- ``protected``        : current branch, configured base branch, or one of the
                         well-known long-lived branches (``main``, ``master``,
                         ``develop``).
- ``requires-human``   : everything else — unmerged, upstream-gone, ahead of
                         upstream, no upstream tracking, or attached to a
                         dirty/transient worktree. These are surfaced in the
                         report but are NOT deleted by ``--fix`` unless the
                         operator explicitly opts in via
                         ``--include-requires-human``.

Worktrees are also classified:

- ``safe``         : on disk under the repository, attached to a known branch,
                     and clean.
- ``requires-human``: detached HEAD, located under ``/tmp``, or contains
                      uncommitted changes.

Usage:
    python scripts/git_hygiene.py                    # Human-readable report
    python scripts/git_hygiene.py --json             # Machine-readable
    python scripts/git_hygiene.py --fix --dry-run    # Preview safe deletions
    python scripts/git_hygiene.py --fix              # Apply safe deletions

Exit code is non-zero whenever the report contains anything actionable
(safe-to-delete, requires-human, dirty worktrees, transient files), so it can
be wired into CI or weekly hygiene checks.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Literal


DEFAULT_BASE_BRANCH = "dev"
PROTECTED_NAMES: frozenset[str] = frozenset({"main", "master", "develop"})

base_branch = os.environ.get("REPO_BASE_BRANCH", DEFAULT_BASE_BRANCH)

BranchCategory = Literal["safe-to-delete", "protected", "requires-human"]
WorktreeCategory = Literal["safe", "requires-human"]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BranchInfo:
    """Per-branch hygiene metadata and classification."""

    name: str
    category: BranchCategory = "requires-human"
    reasons: list[str] = field(default_factory=list)
    upstream: str | None = None
    upstream_gone: bool = False
    ahead: int = 0
    behind: int = 0
    merged_into_base: bool = False
    worktree_path: str | None = None
    worktree_dirty: bool = False
    is_current: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "category": self.category,
            "reasons": list(self.reasons),
            "upstream": self.upstream,
            "upstream_gone": self.upstream_gone,
            "ahead": self.ahead,
            "behind": self.behind,
            "merged_into_base": self.merged_into_base,
            "worktree_path": self.worktree_path,
            "worktree_dirty": self.worktree_dirty,
            "is_current": self.is_current,
        }


@dataclass
class WorktreeInfo:
    """Per-worktree hygiene metadata and classification."""

    path: str
    branch: str | None = None
    detached: bool = False
    bare: bool = False
    in_tmp: bool = False
    dirty: bool = False
    is_main: bool = False

    @property
    def reasons(self) -> list[str]:
        out: list[str] = []
        if self.bare:
            out.append("bare")
        if self.detached:
            out.append("detached HEAD")
        if self.in_tmp:
            out.append("in /tmp")
        if self.dirty:
            out.append("uncommitted changes")
        return out

    @property
    def category(self) -> WorktreeCategory:
        return "safe" if not self.reasons else "requires-human"

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "branch": self.branch,
            "category": self.category,
            "reasons": self.reasons,
            "detached": self.detached,
            "bare": self.bare,
            "in_tmp": self.in_tmp,
            "dirty": self.dirty,
            "is_main": self.is_main,
        }


@dataclass
class HygieneReport:
    """Aggregated hygiene findings."""

    branches: list[BranchInfo] = field(default_factory=list)
    worktrees: list[WorktreeInfo] = field(default_factory=list)
    transient_files: list[str] = field(default_factory=list)

    # ----- New, lane-aware accessors -----

    def branches_in_category(self, category: BranchCategory) -> list[BranchInfo]:
        return [b for b in self.branches if b.category == category]

    @property
    def safe_to_delete(self) -> list[BranchInfo]:
        return self.branches_in_category("safe-to-delete")

    @property
    def protected(self) -> list[BranchInfo]:
        return self.branches_in_category("protected")

    @property
    def requires_human(self) -> list[BranchInfo]:
        return self.branches_in_category("requires-human")

    @property
    def stale_worktrees_info(self) -> list[WorktreeInfo]:
        return [w for w in self.worktrees if w.category != "safe"]

    # ----- Backward-compatible accessors (kept for existing JSON consumers) -----

    @property
    def merged_branches(self) -> list[str]:
        """Branches eligible for safe automatic deletion."""
        return [b.name for b in self.safe_to_delete]

    @property
    def no_upstream_branches(self) -> list[str]:
        """Branches surfaced under ``requires-human`` for missing upstream."""
        return [b.name for b in self.requires_human if "no upstream" in b.reasons]

    @property
    def stale_worktrees(self) -> list[dict[str, str]]:
        """Backward-compat shape: list of ``{path, reason}`` dicts."""
        out: list[dict[str, str]] = []
        for w in self.stale_worktrees_info:
            out.append({"path": w.path, "reason": ", ".join(w.reasons) or "unknown"})
        return out

    # ----- Aggregate counters -----

    @property
    def total_issues(self) -> int:
        # Protected branches are always present and not actionable, so they
        # don't contribute to the count.
        return (
            len(self.safe_to_delete)
            + len(self.requires_human)
            + len(self.stale_worktrees_info)
            + len(self.transient_files)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            # Backward-compat top-level keys
            "merged_branches": self.merged_branches,
            "no_upstream_branches": self.no_upstream_branches,
            "stale_worktrees": self.stale_worktrees,
            "transient_files": self.transient_files,
            "total_issues": self.total_issues,
            # New lane-aware view
            "classification": {
                "safe_to_delete": [b.to_dict() for b in self.safe_to_delete],
                "protected": [b.to_dict() for b in self.protected],
                "requires_human": [b.to_dict() for b in self.requires_human],
                "worktrees": [w.to_dict() for w in self.worktrees],
            },
        }


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], *, check: bool = True, cwd: str | None = None) -> str:
    """Run a git command and return stripped stdout."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
        cwd=cwd,
    )
    return result.stdout.strip()


def _current_branch() -> str | None:
    name = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], check=False)
    if not name or name == "HEAD":
        return None
    return name


def _is_merged_into_base(branch: str, base: str) -> bool:
    """Return True if ``branch`` tip is reachable from ``origin/base``.

    Falls back to local ``base`` if the remote ref does not exist.
    """
    for ref in (f"origin/{base}", base):
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", branch, ref],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return True
        # returncode 1 == not an ancestor; >1 means ref doesn't exist, try fallback
        if result.returncode == 1:
            return False
    return False


def _worktree_is_dirty(path: str) -> bool:
    """Return True if the worktree at ``path`` has uncommitted changes.

    Uses ``git status --porcelain`` against the given worktree path. Any
    non-empty output (modified, staged, untracked) counts as dirty.
    """
    result = subprocess.run(
        ["git", "-C", path, "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Treat unreachable worktree as suspicious -> dirty for safety.
        return True
    return bool(result.stdout.strip())


def fetch_remote_state() -> None:
    """Best-effort fetch with prune so upstream-gone is detectable."""
    subprocess.run(
        ["git", "fetch", "--prune"],
        capture_output=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# Worktree discovery
# ---------------------------------------------------------------------------


def collect_worktrees() -> list[WorktreeInfo]:
    """Parse ``git worktree list --porcelain`` and check dirty state for each."""
    raw = _run(["git", "worktree", "list", "--porcelain"], check=False)
    worktrees: list[WorktreeInfo] = []
    if not raw:
        return worktrees

    current: dict[str, object] = {}

    def finalize(entry: dict[str, object]) -> None:
        if not entry:
            return
        path = str(entry.get("path", ""))
        if not path:
            return
        wt = WorktreeInfo(
            path=path,
            branch=entry.get("branch"),  # type: ignore[arg-type]
            detached=bool(entry.get("detached", False)),
            bare=bool(entry.get("bare", False)),
            in_tmp=path.startswith("/tmp"),
            is_main=bool(entry.get("is_main", False)),
        )
        # Bare worktrees are not real working trees; skip dirty probe.
        if not wt.bare:
            wt.dirty = _worktree_is_dirty(path)
        worktrees.append(wt)

    is_first = True
    for line in raw.splitlines():
        if line.startswith("worktree "):
            finalize(current)
            current = {"path": line.split(" ", 1)[1], "is_main": is_first}
            is_first = False
        elif line.startswith("branch "):
            ref = line.split(" ", 1)[1]
            current["branch"] = ref.removeprefix("refs/heads/")
        elif line == "detached":
            current["detached"] = True
        elif line == "bare":
            current["bare"] = True
        elif line == "":
            finalize(current)
            current = {}
    finalize(current)
    return worktrees


# ---------------------------------------------------------------------------
# Branch discovery & classification
# ---------------------------------------------------------------------------


def collect_branches(
    *,
    base: str,
    current: str | None,
    worktrees: list[WorktreeInfo],
) -> list[BranchInfo]:
    """Collect per-branch metadata required for classification."""
    fmt = "%(refname:short)\t%(upstream:short)\t%(upstream:track)"
    raw = _run(
        ["git", "for-each-ref", f"--format={fmt}", "refs/heads/"],
        check=False,
    )
    if not raw:
        return []

    wt_by_branch: dict[str, WorktreeInfo] = {}
    for wt in worktrees:
        if wt.branch:
            wt_by_branch[wt.branch] = wt

    branches: list[BranchInfo] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        name = parts[0]
        upstream = parts[1] if len(parts) > 1 and parts[1] else None
        track = parts[2] if len(parts) > 2 else ""

        info = BranchInfo(
            name=name,
            upstream=upstream,
            is_current=(name == current),
        )

        # Parse upstream tracking ([gone], [ahead 1], [ahead 1, behind 2])
        if track == "[gone]":
            info.upstream_gone = True
        elif track:
            inside = track.strip("[]")
            for token in (t.strip() for t in inside.split(",")):
                if token.startswith("ahead "):
                    with contextlib.suppress(ValueError, IndexError):
                        info.ahead = int(token.split()[1])
                elif token.startswith("behind "):
                    with contextlib.suppress(ValueError, IndexError):
                        info.behind = int(token.split()[1])

        info.merged_into_base = _is_merged_into_base(name, base)

        wt = wt_by_branch.get(name)
        if wt is not None:
            info.worktree_path = wt.path
            info.worktree_dirty = wt.dirty

        branches.append(info)

    return branches


def classify_branch(info: BranchInfo, *, base: str) -> BranchInfo:
    """Set ``info.category`` and ``info.reasons`` based on collected metadata."""
    reasons: list[str] = []

    # Protected branches are not deletable regardless of state.
    if info.is_current or info.name == base or info.name in PROTECTED_NAMES:
        info.category = "protected"
        if info.is_current:
            reasons.append("current branch")
        elif info.name == base:
            reasons.append(f"base branch ({base})")
        else:
            reasons.append("long-lived branch")
        info.reasons = reasons
        return info

    # Anything below this point is deletable in principle, so collect risk
    # signals and decide between safe-to-delete and requires-human.
    if info.upstream is None:
        reasons.append("no upstream")
    if info.upstream_gone:
        reasons.append("upstream gone")
    if info.ahead > 0:
        reasons.append(f"{info.ahead} commit(s) ahead of upstream")
    if not info.merged_into_base:
        reasons.append(f"not merged into {base}")
    if info.worktree_path:
        reasons.append(f"checked out at {info.worktree_path}")
        if info.worktree_dirty:
            reasons.append("uncommitted changes in worktree")

    if not reasons:
        info.category = "safe-to-delete"
        info.reasons = [f"merged into {base}", "upstream tracking present", "no live worktree"]
    else:
        info.category = "requires-human"
        info.reasons = reasons

    return info


def classify_branches(branches: list[BranchInfo], *, base: str) -> list[BranchInfo]:
    return [classify_branch(b, base=base) for b in branches]


# ---------------------------------------------------------------------------
# Transient files (unchanged)
# ---------------------------------------------------------------------------


def find_transient_files() -> list[str]:
    """Find untracked transient files (coverage, test output, logs)."""
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


# ---------------------------------------------------------------------------
# Backward-compat helpers (kept so external callers/tests stay green)
# ---------------------------------------------------------------------------


def find_merged_branches() -> list[str]:
    """Backward-compat: list of branch names eligible for safe deletion."""
    fetch_remote_state()
    current = _current_branch()
    worktrees = collect_worktrees()
    branches = classify_branches(
        collect_branches(base=base_branch, current=current, worktrees=worktrees),
        base=base_branch,
    )
    return [b.name for b in branches if b.category == "safe-to-delete"]


def find_no_upstream_branches() -> list[str]:
    """Backward-compat: branches without upstream tracking."""
    raw = _run(
        [
            "git",
            "for-each-ref",
            "--format=%(refname:short) %(upstream)",
            "refs/heads/",
        ],
        check=False,
    )
    if not raw:
        return []
    out: list[str] = []
    for line in raw.splitlines():
        parts = line.split(maxsplit=1)
        branch = parts[0]
        upstream = parts[1] if len(parts) > 1 else ""
        if not upstream:
            out.append(branch)
    return out


def find_stale_worktrees() -> list[dict[str, str]]:
    """Backward-compat: dicts of ``{path, reason}`` for any non-safe worktree."""
    worktrees = collect_worktrees()
    out: list[dict[str, str]] = []
    for wt in worktrees:
        if wt.category != "safe":
            out.append({"path": wt.path, "reason": ", ".join(wt.reasons) or "unknown"})
    return out


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def build_report() -> HygieneReport:
    """Assemble a complete hygiene report."""
    fetch_remote_state()
    current = _current_branch()
    worktrees = collect_worktrees()
    branches = classify_branches(
        collect_branches(base=base_branch, current=current, worktrees=worktrees),
        base=base_branch,
    )
    return HygieneReport(
        branches=branches,
        worktrees=worktrees,
        transient_files=find_transient_files(),
    )


def print_human_report(report: HygieneReport) -> None:
    """Print a human-readable summary."""
    print("=== Git Hygiene Report ===\n")
    print(f"Base branch: {base_branch}\n")

    safe = report.safe_to_delete
    print(f"Safe to delete ({len(safe)}):")
    if safe:
        for b in safe:
            print(f"  - {b.name}")
    else:
        print("  (none)")

    rh = report.requires_human
    print(f"\nRequires human review ({len(rh)}):")
    if rh:
        for b in rh:
            wt = f" [worktree: {b.worktree_path}]" if b.worktree_path else ""
            print(f"  - {b.name}{wt}")
            for reason in b.reasons:
                print(f"      • {reason}")
    else:
        print("  (none)")

    stale = report.stale_worktrees_info
    print(f"\nStale / dirty worktrees ({len(stale)}):")
    if stale:
        for wt in stale:
            print(f"  - {wt.path}  ({', '.join(wt.reasons)})")
    else:
        print("  (none)")

    print(f"\nTransient files ({len(report.transient_files)}):")
    if report.transient_files:
        for f in report.transient_files:
            print(f"  - {f}")
    else:
        print("  (none)")

    print(f"\nProtected branches: {len(report.protected)}")
    for b in report.protected:
        print(f"  - {b.name}  ({', '.join(b.reasons)})")

    print(f"\nTotal actionable issues: {report.total_issues}")


# ---------------------------------------------------------------------------
# Cleanup actions
# ---------------------------------------------------------------------------


def fix_safe_branches(
    branches: list[BranchInfo], *, dry_run: bool = False, quiet: bool = False
) -> list[str]:
    """Delete branches that are safely mergeable into base."""
    deleted: list[str] = []
    for branch in branches:
        if dry_run:
            if not quiet:
                print(f"  [dry-run] would delete: {branch.name}")
            deleted.append(branch.name)
            continue
        result = subprocess.run(
            ["git", "branch", "-d", branch.name],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            if not quiet:
                print(f"  deleted: {branch.name}")
            deleted.append(branch.name)
        elif not quiet:
            print(f"  FAILED to delete {branch.name}: {result.stderr.strip()}")
    return deleted


# Backward-compat shim: existing tests/code may call ``fix_merged_branches``.
def fix_merged_branches(
    branches: list[str], *, dry_run: bool = False, quiet: bool = False
) -> list[str]:
    """Backward-compatible shim accepting plain branch names."""
    return fix_safe_branches(
        [BranchInfo(name=b, category="safe-to-delete") for b in branches],
        dry_run=dry_run,
        quiet=quiet,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Git hygiene report and safe cleanup tool",
    )
    parser.add_argument("--json", action="store_true", help="Output report as JSON")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-cleanup safe-to-delete branches (merged + clean worktree + has upstream).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview cleanup actions without executing (use with --fix).",
    )
    parser.add_argument(
        "--include-requires-human",
        action="store_true",
        help=(
            "Also delete branches in the 'requires-human' lane. "
            "Refuses to delete a branch attached to a dirty worktree even with this flag."
        ),
    )
    args = parser.parse_args()

    if args.dry_run and not args.fix:
        parser.error("--dry-run requires --fix")
    if args.include_requires_human and not args.fix:
        parser.error("--include-requires-human requires --fix")

    report = build_report()

    if args.fix:
        if not args.json:
            print("=== Git Hygiene Cleanup ===\n")

        if report.safe_to_delete:
            if not args.json:
                label = "dry-run" if args.dry_run else "cleanup"
                print(f"Safe-to-delete branches ({label}):")
            fix_safe_branches(
                report.safe_to_delete,
                dry_run=args.dry_run,
                quiet=args.json,
            )
        elif not args.json:
            print("No safe-to-delete branches.")

        if args.include_requires_human:
            elig = [b for b in report.requires_human if not b.worktree_dirty and not b.is_current]
            if elig:
                if not args.json:
                    label = "dry-run" if args.dry_run else "cleanup"
                    print(f"\nRequires-human branches ({label}, opt-in):")
                fix_safe_branches(elig, dry_run=args.dry_run, quiet=args.json)
            elif not args.json:
                print("\nNo eligible requires-human branches (all blocked by safety guard).")

        if not args.json:
            print()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_human_report(report)

    sys.exit(0 if report.total_issues == 0 else 1)


if __name__ == "__main__":
    main()
