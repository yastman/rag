"""Unit tests for ``scripts/pr_queue_audit.py``.

Exercise the classification logic through ``classify_pr`` with synthetic
``gh pr list --json`` payloads. ``fetch_open_prs`` is exercised through a
fake subprocess runner so we do not require a real ``gh`` installation.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "pr_queue_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("pr_queue_audit_under_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pq():
    return _load_module()


***REMOVED*** Reference "now" used across age computations so tests are deterministic.
NOW = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)


def _pr(
    *,
    number: int = 1,
    title: str = "test pr",
    base: str = "dev",
    head: str = "feature/x",
    is_draft: bool = False,
    mergeable: str = "MERGEABLE",
    merge_state: str = "CLEAN",
    rollup_state: str = "SUCCESS",
    review_decision: str = "APPROVED",
    days_old: int = 1,
    author: str = "alice",
    labels: list[str] | None = None,
) -> dict:
    created = (NOW - timedelta(days=days_old)).isoformat().replace("+00:00", "Z")
    return {
        "number": number,
        "title": title,
        "url": f"https://example.test/pr/{number}",
        "isDraft": is_draft,
        "mergeable": mergeable,
        "mergeStateStatus": merge_state,
        "baseRefName": base,
        "headRefName": head,
        "createdAt": created,
        "updatedAt": created,
        "author": {"login": author},
        "labels": [{"name": n} for n in (labels or [])],
        "reviewDecision": review_decision,
        "statusCheckRollup": [{"conclusion": rollup_state}],
    }


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Bucket classification
***REMOVED*** ---------------------------------------------------------------------------


def test_ready_pr(pq) -> None:
    out = pq.classify_pr(_pr(), now=NOW)
    assert out.bucket == "ready"
    assert out.blocked_reason == ""


def test_draft_pr_takes_precedence_over_other_signals(pq) -> None:
    out = pq.classify_pr(
        _pr(is_draft=True, mergeable="CONFLICTING", rollup_state="FAILURE"),
        now=NOW,
    )
    assert out.bucket == "draft"
    assert out.is_draft is True


def test_conflict_pr(pq) -> None:
    out = pq.classify_pr(_pr(mergeable="CONFLICTING"), now=NOW)
    assert out.bucket == "conflicts"
    assert "merge conflicts" in out.blocked_reason


def test_dirty_merge_state_is_conflict(pq) -> None:
    out = pq.classify_pr(_pr(mergeable="UNKNOWN", merge_state="DIRTY"), now=NOW)
    assert out.bucket == "conflicts"


def test_ci_failing_pr(pq) -> None:
    out = pq.classify_pr(_pr(rollup_state="FAILURE"), now=NOW)
    assert out.bucket == "ci-failing"
    assert "CI failure" in out.blocked_reason


def test_ci_pending_pr(pq) -> None:
    out = pq.classify_pr(_pr(rollup_state="IN_PROGRESS"), now=NOW)
    assert out.bucket == "ci-pending"


def test_changes_requested_pr(pq) -> None:
    out = pq.classify_pr(_pr(review_decision="CHANGES_REQUESTED"), now=NOW)
    assert out.bucket == "changes-requested"


def test_review_required_pr(pq) -> None:
    out = pq.classify_pr(_pr(review_decision="REVIEW_REQUIRED"), now=NOW)
    assert out.bucket == "review-needed"


def test_no_review_policy_pr_with_green_ci(pq) -> None:
    out = pq.classify_pr(_pr(review_decision=""), now=NOW)
    assert out.bucket == "ready"


def test_no_review_policy_with_no_ci_data(pq) -> None:
    raw = _pr(review_decision="")
    raw["statusCheckRollup"] = []
    out = pq.classify_pr(raw, now=NOW)
    assert out.bucket == "ready"


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Stale flag
***REMOVED*** ---------------------------------------------------------------------------


def test_stale_flag_set_for_old_prs(pq) -> None:
    out = pq.classify_pr(_pr(days_old=20), stale_days=14, now=NOW)
    assert out.is_stale is True
    assert out.age_days == 20


def test_stale_flag_off_for_fresh_prs(pq) -> None:
    out = pq.classify_pr(_pr(days_old=2), stale_days=14, now=NOW)
    assert out.is_stale is False


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Severity reduction over rollup
***REMOVED*** ---------------------------------------------------------------------------


def test_ci_state_picks_worst_check_first(pq) -> None:
    raw = _pr()
    raw["statusCheckRollup"] = [
        {"conclusion": "SUCCESS"},
        {"state": "FAILURE"},
        {"conclusion": "PENDING"},
    ]
    out = pq.classify_pr(raw, now=NOW)
    assert out.ci_state == "FAILURE"
    assert out.bucket == "ci-failing"


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Aggregate: summarise + filter
***REMOVED*** ---------------------------------------------------------------------------


def test_summarise_counts_per_bucket(pq) -> None:
    raw = [
        _pr(number=1, mergeable="CONFLICTING"),
        _pr(number=2, rollup_state="FAILURE"),
        _pr(number=3, review_decision="APPROVED"),
        _pr(number=4, days_old=30),  ***REMOVED*** stale + ready
    ]
    classified = pq.build_report(raw, stale_days=14, now=NOW)
    counts = pq.summarise(classified)

    assert counts["conflicts"] == 1
    assert counts["ci-failing"] == 1
    assert counts["ready"] == 2
    assert counts["stale_flagged"] == 1


def test_filter_bucket_returns_only_match(pq) -> None:
    raw = [
        _pr(number=1, mergeable="CONFLICTING"),
        _pr(number=2),
    ]
    classified = pq.build_report(raw, now=NOW)
    only_conflicts = pq.filter_bucket(classified, "conflicts")
    assert [p.number for p in only_conflicts] == [1]


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** fetch_open_prs uses gh CLI through the runner
***REMOVED*** ---------------------------------------------------------------------------


def test_fetch_open_prs_invokes_gh_with_correct_args(pq) -> None:
    captured: dict[str, list[str]] = {}

    class _Result:
        returncode = 0
        stdout = "[]"
        stderr = ""

    def fake_runner(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        return _Result()

    pq.fetch_open_prs(base="dev", limit=50, runner=fake_runner)
    assert captured["cmd"][:3] == ["gh", "pr", "list"]
    assert "--state" in captured["cmd"]
    assert "--base" in captured["cmd"]
    assert "dev" in captured["cmd"]


def test_fetch_open_prs_raises_on_gh_failure(pq) -> None:
    class _Result:
        returncode = 1
        stdout = ""
        stderr = "auth error"

    def fake_runner(cmd, **kwargs):
        return _Result()

    with pytest.raises(RuntimeError, match="gh pr list failed"):
        pq.fetch_open_prs(runner=fake_runner)


def test_fetch_open_prs_raises_on_non_list_json(pq) -> None:
    class _Result:
        returncode = 0
        stdout = '{"oops": true}'
        stderr = ""

    def fake_runner(cmd, **kwargs):
        return _Result()

    with pytest.raises(RuntimeError, match="non-list JSON"):
        pq.fetch_open_prs(runner=fake_runner)


def test_fetch_open_prs_returns_parsed_list(pq) -> None:
    payload = [_pr(number=42)]

    class _Result:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    def fake_runner(cmd, **kwargs):
        return _Result()

    out = pq.fetch_open_prs(runner=fake_runner)
    assert len(out) == 1
    assert out[0]["number"] == 42
