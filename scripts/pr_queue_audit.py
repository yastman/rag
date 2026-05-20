#!/usr/bin/env python3
"""Open PR queue triage report.

Reads open pull requests via ``gh pr list --json ...`` and classifies each
into actionable buckets so an operator can decide what to merge / nudge /
close. Designed for the weekly governance runbook (issue #1719).

Buckets
-------

- ``ready``               : Mergeable, static CI green, has at least one
                            approval (or repo policy waives review). Confirm
                            local test evidence before merge.
- ``ci-failing``           : Static CI status is FAILURE / ERROR / CANCELLED.
- ``ci-pending``           : Static CI not yet completed.
- ``conflicts``            : ``mergeable`` reports CONFLICTING.
- ``review-needed``        : Static CI green, no approvals yet.
- ``changes-requested``    : Reviewer asked for changes; awaits author.
- ``draft``                : Marked as draft.
- ``stale``                : Open longer than ``--stale-days`` (default 14).
- ``unknown``              : Could not determine state (gh field missing).

A PR can land in only one bucket. Order of precedence:

    draft > conflicts > ci-failing > ci-pending > changes-requested
        > review-needed > ready > unknown

``stale`` is reported as a separate flag in addition to the primary bucket so
that long-lived but otherwise-ready PRs still surface.

CLI
---

    python scripts/pr_queue_audit.py                     # human report
    python scripts/pr_queue_audit.py --json              # machine-readable
    python scripts/pr_queue_audit.py --base dev          # filter by base
    python scripts/pr_queue_audit.py --stale-days 7
    python scripts/pr_queue_audit.py --bucket conflicts  # one bucket only

Exit code is 0 on a clean queue, 1 otherwise.

Requirements: ``gh`` CLI authenticated to the target repository.
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


PRBucket = Literal[
    "ready",
    "ci-failing",
    "ci-pending",
    "conflicts",
    "review-needed",
    "changes-requested",
    "draft",
    "stale",
    "unknown",
]

# Order: most actionable first; used for sorted reports and for triage SLA.
PRIORITY_ORDER: tuple[PRBucket, ...] = (
    "conflicts",
    "ci-failing",
    "ci-pending",
    "changes-requested",
    "review-needed",
    "ready",
    "draft",
    "stale",
    "unknown",
)


GH_FIELDS: tuple[str, ...] = (
    "number",
    "title",
    "url",
    "isDraft",
    "mergeable",
    "mergeStateStatus",
    "baseRefName",
    "headRefName",
    "createdAt",
    "updatedAt",
    "author",
    "labels",
    "reviewDecision",
    "statusCheckRollup",
)


@dataclass
class PRStatus:
    """Triage classification of a single open pull request."""

    number: int
    title: str
    url: str
    base: str
    head: str
    bucket: PRBucket
    age_days: int
    is_stale: bool = False
    blocked_reason: str = ""
    author: str = ""
    labels: list[str] = field(default_factory=list)
    review_decision: str = ""
    ci_state: str = ""
    is_draft: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "url": self.url,
            "base": self.base,
            "head": self.head,
            "bucket": self.bucket,
            "age_days": self.age_days,
            "is_stale": self.is_stale,
            "blocked_reason": self.blocked_reason,
            "author": self.author,
            "labels": list(self.labels),
            "review_decision": self.review_decision,
            "ci_state": self.ci_state,
            "is_draft": self.is_draft,
        }


# ---------------------------------------------------------------------------
# gh CLI invocation
# ---------------------------------------------------------------------------


def fetch_open_prs(
    *,
    base: str | None = None,
    limit: int = 200,
    runner=subprocess.run,
) -> list[dict[str, Any]]:
    """Invoke ``gh pr list`` and return the parsed JSON list."""
    cmd: list[str] = [
        "gh",
        "pr",
        "list",
        "--state",
        "open",
        "--limit",
        str(limit),
        "--json",
        ",".join(GH_FIELDS),
    ]
    if base:
        cmd.extend(["--base", base])

    result = runner(cmd, capture_output=True, text=True, check=False)
    if getattr(result, "returncode", 1) != 0:
        raise RuntimeError(
            f"gh pr list failed (exit {result.returncode}): {getattr(result, 'stderr', '')!r}"
        )
    raw = (result.stdout or "").strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise RuntimeError("gh returned non-list JSON; cannot triage")
    return parsed


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _ci_state(rollup: Iterable[Any] | None) -> str:
    """Reduce ``statusCheckRollup`` to a single state string.

    GitHub returns a list of check runs; we surface the worst-case state.
    """
    if not rollup:
        return ""
    severity = {
        "FAILURE": 5,
        "ERROR": 5,
        "CANCELLED": 4,
        "TIMED_OUT": 4,
        "ACTION_REQUIRED": 4,
        "PENDING": 3,
        "IN_PROGRESS": 3,
        "QUEUED": 3,
        "SUCCESS": 2,
        "NEUTRAL": 1,
        "SKIPPED": 1,
    }
    worst_state = ""
    worst_score = -1
    for check in rollup:
        if not isinstance(check, dict):
            continue
        # Both ``conclusion`` (CheckRun) and ``state`` (StatusContext) appear.
        state = check.get("conclusion") or check.get("state") or ""
        if not state:
            continue
        score = severity.get(state, 0)
        if score > worst_score:
            worst_score = score
            worst_state = state
    return worst_state


def _parse_age_days(created_at: str, *, now: datetime | None = None) -> int:
    if not created_at:
        return 0
    try:
        # Python 3.11+ ``fromisoformat`` parses the trailing ``Z`` natively.
        dt = datetime.fromisoformat(created_at)
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    reference = now or datetime.now(UTC)
    return max(0, (reference - dt).days)


def classify_pr(
    raw: dict[str, Any],
    *,
    stale_days: int = 14,
    now: datetime | None = None,
) -> PRStatus:
    """Convert a single ``gh pr list`` entry into a ``PRStatus``."""
    number = int(raw.get("number", 0))
    title = str(raw.get("title", "") or "")
    url = str(raw.get("url", "") or "")
    base = str(raw.get("baseRefName", "") or "")
    head = str(raw.get("headRefName", "") or "")
    is_draft = bool(raw.get("isDraft", False))

    author_block = raw.get("author") or {}
    author = author_block.get("login", "") if isinstance(author_block, dict) else ""

    label_names: list[str] = []
    for label in raw.get("labels") or []:
        if isinstance(label, dict) and label.get("name"):
            label_names.append(str(label["name"]))

    review_decision = str(raw.get("reviewDecision") or "")
    mergeable = str(raw.get("mergeable") or "").upper()
    merge_state = str(raw.get("mergeStateStatus") or "").upper()
    ci_state = _ci_state(raw.get("statusCheckRollup"))

    age_days = _parse_age_days(raw.get("createdAt", ""), now=now)
    is_stale = age_days >= stale_days

    bucket: PRBucket = "unknown"
    blocked_reason = ""

    if is_draft:
        bucket = "draft"
        blocked_reason = "marked as draft"
    elif mergeable == "CONFLICTING" or merge_state == "DIRTY":
        bucket = "conflicts"
        blocked_reason = "merge conflicts"
    elif ci_state in {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"}:
        bucket = "ci-failing"
        blocked_reason = f"CI {ci_state.lower()}"
    elif ci_state in {"PENDING", "IN_PROGRESS", "QUEUED"}:
        bucket = "ci-pending"
        blocked_reason = "CI in progress"
    elif review_decision == "CHANGES_REQUESTED":
        bucket = "changes-requested"
        blocked_reason = "reviewer requested changes"
    elif review_decision == "APPROVED":
        bucket = "ready"
        blocked_reason = ""
    elif review_decision == "REVIEW_REQUIRED":
        bucket = "review-needed"
        blocked_reason = "no approval yet"
    elif review_decision == "":
        # No review policy -> ready if everything else is fine
        bucket = "ready" if ci_state in {"SUCCESS", ""} else "review-needed"
    else:
        bucket = "unknown"
        blocked_reason = f"unrecognised reviewDecision={review_decision!r}"

    return PRStatus(
        number=number,
        title=title,
        url=url,
        base=base,
        head=head,
        bucket=bucket,
        age_days=age_days,
        is_stale=is_stale,
        blocked_reason=blocked_reason,
        author=author,
        labels=label_names,
        review_decision=review_decision,
        ci_state=ci_state,
        is_draft=is_draft,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def summarise(prs: list[PRStatus]) -> dict[str, int]:
    """Return per-bucket counts plus the stale-flag count."""
    counts: dict[str, int] = dict.fromkeys(PRIORITY_ORDER, 0)
    counts["stale_flagged"] = 0
    for pr in prs:
        counts[pr.bucket] = counts.get(pr.bucket, 0) + 1
        if pr.is_stale:
            counts["stale_flagged"] += 1
    return counts


def print_human_report(prs: list[PRStatus], counts: dict[str, int]) -> None:
    """Print a grouped human-readable report."""
    total = sum(counts[b] for b in PRIORITY_ORDER)
    print("=== PR Queue Triage ===")
    print(f"Total open PRs: {total}")
    print(f"Stale (flagged): {counts['stale_flagged']}\n")

    by_bucket: dict[str, list[PRStatus]] = {b: [] for b in PRIORITY_ORDER}
    for pr in prs:
        by_bucket[pr.bucket].append(pr)

    for bucket in PRIORITY_ORDER:
        items = by_bucket[bucket]
        if not items:
            continue
        items.sort(key=lambda p: p.age_days, reverse=True)
        print(f"[{bucket}] ({len(items)}):")
        for pr in items:
            stale_flag = " [STALE]" if pr.is_stale else ""
            reason = f"  -- {pr.blocked_reason}" if pr.blocked_reason else ""
            print(f"  #{pr.number:>5} ({pr.age_days}d){stale_flag}  {pr.title}")
            print(f"         base={pr.base} head={pr.head} author=@{pr.author}{reason}")
            print(f"         {pr.url}")
        print()


def filter_bucket(prs: list[PRStatus], bucket: PRBucket | None) -> list[PRStatus]:
    if bucket is None:
        return prs
    return [pr for pr in prs if pr.bucket == bucket]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_report(
    raw_prs: list[dict[str, Any]],
    *,
    stale_days: int = 14,
    now: datetime | None = None,
) -> list[PRStatus]:
    return [classify_pr(item, stale_days=stale_days, now=now) for item in raw_prs]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open PR queue triage report")
    parser.add_argument(
        "--base",
        default=None,
        help="Filter PRs by base branch (e.g. dev, main).",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=14,
        help="Age threshold in days that flags a PR as stale (default: 14).",
    )
    parser.add_argument(
        "--bucket",
        choices=list(PRIORITY_ORDER),
        default=None,
        help="Show only PRs in the given bucket.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Max PRs requested from gh (default: 200).",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    raw_prs = fetch_open_prs(base=args.base, limit=args.limit)
    classified = build_report(raw_prs, stale_days=args.stale_days)
    classified = filter_bucket(classified, args.bucket)
    counts = summarise(classified)

    if args.json:
        payload = {
            "summary": counts,
            "stale_days": args.stale_days,
            "base_filter": args.base,
            "bucket_filter": args.bucket,
            "items": [pr.to_dict() for pr in classified],
        }
        print(json.dumps(payload, indent=2))
    else:
        print_human_report(classified, counts)

    actionable_buckets = {"conflicts", "ci-failing", "changes-requested", "review-needed", "ready"}
    actionable = sum(counts[b] for b in actionable_buckets) + counts["stale_flagged"]
    return 0 if actionable == 0 else 1


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    sys.exit(main())
