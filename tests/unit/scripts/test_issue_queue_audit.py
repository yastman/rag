"""Unit tests for ``scripts/issue_queue_audit.py``."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "issue_queue_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("issue_queue_audit_under_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def iq():
    return _load_module()


NOW = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)


def _issue(
    *,
    number: int = 1,
    title: str = "test issue",
    days_old: int = 1,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
) -> dict:
    created = (NOW - timedelta(days=days_old)).isoformat().replace("+00:00", "Z")
    return {
        "number": number,
        "title": title,
        "url": f"https://example.test/issue/{number}",
        "labels": [{"name": n} for n in (labels or [])],
        "assignees": [{"login": login} for login in (assignees or [])],
        "createdAt": created,
        "updatedAt": created,
    }


# ---------------------------------------------------------------------------
# Per-flag classification
# ---------------------------------------------------------------------------


def test_issue_with_no_labels_no_assignee(iq) -> None:
    out = iq.classify_issue(_issue(), now=NOW)
    assert "no-labels" in out.flags
    assert "no-assignee" in out.flags
    assert "no-lane" not in out.flags  # gated on having any labels
    assert out.is_triaged is False


def test_issue_with_labels_but_no_lane(iq) -> None:
    out = iq.classify_issue(_issue(labels=["bug"], assignees=["alice"]), now=NOW)
    assert "no-lane" in out.flags
    assert "no-labels" not in out.flags
    assert "no-assignee" not in out.flags


def test_fully_triaged_issue(iq) -> None:
    out = iq.classify_issue(
        _issue(labels=["bug", "lane:quick-win"], assignees=["alice"]),
        now=NOW,
    )
    assert out.flags == ["triaged"]
    assert out.is_triaged is True
    assert out.lane == "lane:quick-win"


def test_stale_flag_added_when_old(iq) -> None:
    out = iq.classify_issue(
        _issue(days_old=120, labels=["bug", "lane:plan-needed"], assignees=["bob"]),
        stale_days=60,
        now=NOW,
    )
    assert "stale" in out.flags
    assert out.is_triaged is False  # any flag means not fully triaged


def test_lane_picks_first_lane_label(iq) -> None:
    out = iq.classify_issue(
        _issue(labels=["bug", "lane:quick-win", "lane:plan-needed"], assignees=["alice"]),
        now=NOW,
    )
    assert out.lane == "lane:quick-win"


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def test_summarise_counts_buckets_and_lanes(iq) -> None:
    raw = [
        _issue(number=1),  # no-labels + no-assignee
        _issue(number=2, labels=["bug"]),  # no-lane + no-assignee
        _issue(number=3, labels=["bug", "lane:quick-win"], assignees=["alice"]),
        _issue(
            number=4,
            labels=["bug", "lane:plan-needed"],
            assignees=["bob"],
            days_old=120,
        ),
    ]
    classified = iq.build_report(raw, stale_days=60, now=NOW)
    counts = iq.summarise(classified)

    assert counts["total"] == 4
    assert counts["no-labels"] == 1
    assert counts["no-assignee"] == 2
    assert counts["no-lane"] == 1
    assert counts["stale"] == 1
    assert counts["triaged"] == 1
    assert counts["lane::lane:quick-win"] == 1
    assert counts["lane::lane:plan-needed"] == 1
    assert counts["lane::(none)"] == 2


def test_filter_bucket_returns_only_matches(iq) -> None:
    raw = [
        _issue(number=1),
        _issue(number=2, labels=["bug", "lane:quick-win"], assignees=["a"]),
    ]
    classified = iq.build_report(raw, now=NOW)
    only_no_labels = iq.filter_bucket(classified, "no-labels")
    assert [i.number for i in only_no_labels] == [1]


# ---------------------------------------------------------------------------
# fetch_open_issues uses gh CLI through the runner
# ---------------------------------------------------------------------------


def test_fetch_open_issues_invokes_gh(iq) -> None:
    captured: dict[str, list[str]] = {}

    class _Result:
        returncode = 0
        stdout = "[]"
        stderr = ""

    def fake_runner(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        return _Result()

    iq.fetch_open_issues(limit=10, runner=fake_runner)
    assert captured["cmd"][:3] == ["gh", "issue", "list"]
    assert "--state" in captured["cmd"]
    assert "open" in captured["cmd"]
    assert "10" in captured["cmd"]


def test_fetch_open_issues_raises_on_failure(iq) -> None:
    class _Result:
        returncode = 1
        stdout = ""
        stderr = "auth error"

    def fake_runner(cmd, **kwargs):
        return _Result()

    with pytest.raises(RuntimeError, match="gh issue list failed"):
        iq.fetch_open_issues(runner=fake_runner)


def test_fetch_open_issues_raises_on_non_list_json(iq) -> None:
    class _Result:
        returncode = 0
        stdout = '{"oops": true}'
        stderr = ""

    def fake_runner(cmd, **kwargs):
        return _Result()

    with pytest.raises(RuntimeError, match="non-list JSON"):
        iq.fetch_open_issues(runner=fake_runner)


def test_fetch_open_issues_returns_parsed_list(iq) -> None:
    payload = [_issue(number=99)]

    class _Result:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    def fake_runner(cmd, **kwargs):
        return _Result()

    out = iq.fetch_open_issues(runner=fake_runner)
    assert len(out) == 1
    assert out[0]["number"] == 99
