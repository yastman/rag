#!/usr/bin/env python3
"""Open issue queue hygiene report.

Reads open issues via ``gh issue list --json ...`` and classifies each into
hygiene buckets so an operator can decide what to label, assign, split, or
close. Designed for the weekly governance runbook (issue #1720).

Lane labels respected
---------------------
- ``lane:quick-win``           : narrow, low-risk; pick up first
- ``lane:plan-needed``         : multi-file or runtime-impacting
- ``lane:architecture-heavy``  : ambiguous structure, needs spec
- (none)                        : missing-lane warning surfaced separately

Hygiene buckets
---------------
- ``no-labels``         : Issue has no labels at all.
- ``no-assignee``       : Issue is not assigned to anyone.
- ``no-lane``           : Has labels but no ``lane:*`` label.
- ``stale``             : Open longer than ``--stale-days`` (default 60).
- ``triaged``           : Has at least one label, an assignee, and a lane.

A single issue may show up in multiple buckets; the JSON output exposes the
full set of flags per issue.

CLI
---

    python scripts/issue_queue_audit.py
    python scripts/issue_queue_audit.py --json
    python scripts/issue_queue_audit.py --bucket no-lane
    python scripts/issue_queue_audit.py --stale-days 30

Exit code is 0 only when there are no issues missing labels, assignees, or a
lane, and no stale issues; otherwise 1.

Requirements: ``gh`` CLI authenticated to the target repository.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


IssueBucket = Literal["no-labels", "no-assignee", "no-lane", "stale", "triaged"]
LANE_PREFIX = "lane:"


@dataclass
class IssueStatus:
    """Hygiene-classification record for a single open issue."""

    number: int
    title: str
    url: str
    age_days: int
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    lane: str = ""  # "" when no lane:* label
    flags: list[IssueBucket] = field(default_factory=list)

    @property
    def is_triaged(self) -> bool:
        return self.flags == ["triaged"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "url": self.url,
            "age_days": self.age_days,
            "labels": list(self.labels),
            "assignees": list(self.assignees),
            "lane": self.lane,
            "flags": list(self.flags),
            "is_triaged": self.is_triaged,
        }


GH_FIELDS: tuple[str, ...] = (
    "number",
    "title",
    "url",
    "labels",
    "assignees",
    "createdAt",
    "updatedAt",
)


def fetch_open_issues(
    *,
    limit: int = 500,
    runner=subprocess.run,
) -> list[dict[str, Any]]:
    """Invoke ``gh issue list`` and return parsed JSON."""
    cmd = [
        "gh",
        "issue",
        "list",
        "--state",
        "open",
        "--limit",
        str(limit),
        "--json",
        ",".join(GH_FIELDS),
    ]
    result = runner(cmd, capture_output=True, text=True, check=False)
    if getattr(result, "returncode", 1) != 0:
        raise RuntimeError(
            f"gh issue list failed (exit {result.returncode}): {getattr(result, 'stderr', '')!r}"
        )
    raw = (result.stdout or "").strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise RuntimeError("gh returned non-list JSON; cannot triage")
    return parsed


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


def classify_issue(
    raw: dict[str, Any],
    *,
    stale_days: int = 60,
    now: datetime | None = None,
) -> IssueStatus:
    """Classify a single ``gh issue list`` entry."""
    number = int(raw.get("number", 0))
    title = str(raw.get("title", "") or "")
    url = str(raw.get("url", "") or "")

    label_names: list[str] = []
    for label in raw.get("labels") or []:
        if isinstance(label, dict) and label.get("name"):
            label_names.append(str(label["name"]))

    assignee_logins: list[str] = []
    for assignee in raw.get("assignees") or []:
        if isinstance(assignee, dict) and assignee.get("login"):
            assignee_logins.append(str(assignee["login"]))

    lane = next((lbl for lbl in label_names if lbl.startswith(LANE_PREFIX)), "")
    age_days = _parse_age_days(raw.get("createdAt", ""), now=now)

    flags: list[IssueBucket] = []
    if not label_names:
        flags.append("no-labels")
    if not assignee_logins:
        flags.append("no-assignee")
    if label_names and not lane:
        flags.append("no-lane")
    if age_days >= stale_days:
        flags.append("stale")
    if not flags:
        flags.append("triaged")

    return IssueStatus(
        number=number,
        title=title,
        url=url,
        age_days=age_days,
        labels=label_names,
        assignees=assignee_logins,
        lane=lane,
        flags=flags,
    )


def summarise(issues: list[IssueStatus]) -> dict[str, int]:
    """Return per-bucket counts plus a per-lane breakdown."""
    counts = dict.fromkeys(("no-labels", "no-assignee", "no-lane", "stale", "triaged"), 0)
    counts["total"] = len(issues)
    lanes: dict[str, int] = {}
    for issue in issues:
        for flag in issue.flags:
            counts[flag] = counts.get(flag, 0) + 1
        lanes[issue.lane or "(none)"] = lanes.get(issue.lane or "(none)", 0) + 1
    counts.update({f"lane::{k}": v for k, v in lanes.items()})
    return counts


def filter_bucket(issues: list[IssueStatus], bucket: IssueBucket | None) -> list[IssueStatus]:
    if bucket is None:
        return issues
    return [i for i in issues if bucket in i.flags]


def print_human_report(issues: list[IssueStatus], counts: dict[str, int]) -> None:
    print("=== Issue Queue Hygiene ===")
    print(f"Total open issues: {counts.get('total', 0)}")
    print(
        f"  no-labels:   {counts.get('no-labels', 0)}\n"
        f"  no-assignee: {counts.get('no-assignee', 0)}\n"
        f"  no-lane:     {counts.get('no-lane', 0)}\n"
        f"  stale:       {counts.get('stale', 0)}\n"
        f"  triaged:     {counts.get('triaged', 0)}\n"
    )

    print("Lane breakdown:")
    lane_keys = sorted([k for k in counts if k.startswith("lane::")])
    if not lane_keys:
        print("  (none)")
    else:
        for key in lane_keys:
            lane_name = key.removeprefix("lane::")
            print(f"  {lane_name:30}  {counts[key]}")
    print()

    if not issues:
        print("(no issues to display)")
        return

    print("Issues requiring action:")
    actionable = [
        i
        for i in issues
        if any(f in {"no-labels", "no-assignee", "no-lane", "stale"} for f in i.flags)
    ]
    actionable.sort(key=lambda i: i.age_days, reverse=True)
    if not actionable:
        print("  (none)")
    else:
        for issue in actionable:
            flags_str = ",".join(issue.flags)
            print(f"  #{issue.number:>5} ({issue.age_days}d) [{flags_str}]  {issue.title}")
            assignees = ", ".join(f"@{a}" for a in issue.assignees) or "—"
            lane = issue.lane or "—"
            print(f"         lane={lane}  assignees={assignees}")
            print(f"         {issue.url}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_report(
    raw_issues: list[dict[str, Any]],
    *,
    stale_days: int = 60,
    now: datetime | None = None,
) -> list[IssueStatus]:
    return [classify_issue(item, stale_days=stale_days, now=now) for item in raw_issues]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open issue queue hygiene report")
    parser.add_argument(
        "--stale-days",
        type=int,
        default=60,
        help="Age threshold in days that flags an issue as stale (default: 60).",
    )
    parser.add_argument(
        "--bucket",
        choices=("no-labels", "no-assignee", "no-lane", "stale", "triaged"),
        default=None,
        help="Show only issues with the given hygiene flag.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Max issues requested from gh (default: 500).",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    raw = fetch_open_issues(limit=args.limit)
    classified = build_report(raw, stale_days=args.stale_days)
    classified = filter_bucket(classified, args.bucket)
    counts = summarise(classified)

    if args.json:
        payload = {
            "summary": counts,
            "stale_days": args.stale_days,
            "bucket_filter": args.bucket,
            "items": [i.to_dict() for i in classified],
        }
        print(json.dumps(payload, indent=2))
    else:
        print_human_report(classified, counts)

    actionable = (
        counts.get("no-labels", 0)
        + counts.get("no-assignee", 0)
        + counts.get("no-lane", 0)
        + counts.get("stale", 0)
    )
    return 0 if actionable == 0 else 1


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    sys.exit(main())
