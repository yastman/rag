"""Unit tests for ``scripts/git_hygiene.py``.

Two test surfaces:

1. **Static guards** — assertions over the source text so the file always
   keeps the conventions encoded by the wider repo (``dev`` as base branch,
   protected long-lived names).
2. **Behavioural** — exercise the classification and reporting logic by
   constructing ``BranchInfo`` / ``WorktreeInfo`` records directly (no live
   git invocation), so ***REMOVED***1718 safety guarantees are pinned by tests.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "git_hygiene.py"


def _load_module():
    """Import ``scripts/git_hygiene.py`` as a standalone module."""
    spec = importlib.util.spec_from_file_location("git_hygiene_under_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gh():
    return _load_module()


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Static guards (kept for backward compatibility with ***REMOVED***1718 audit checklist)
***REMOVED*** ---------------------------------------------------------------------------


def test_git_hygiene_uses_dev_default_branch() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert 'DEFAULT_BASE_BRANCH = "dev"' in text


def test_git_hygiene_protects_long_lived_branches() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    ***REMOVED*** Set membership; new code uses ``PROTECTED_NAMES`` frozenset.
    assert '"main"' in text
    assert '"master"' in text
    assert '"develop"' in text


def test_repo_cleanup_uses_dev_default_branch() -> None:
    text = (REPO_ROOT / "scripts" / "repo_cleanup.sh").read_text(encoding="utf-8")
    assert 'MAIN_BRANCH="${MAIN_BRANCH:-dev}"' in text


def test_repo_cleanup_filters_base_branch_by_exact_match() -> None:
    text = (REPO_ROOT / "scripts" / "repo_cleanup.sh").read_text(encoding="utf-8")
    assert 'grep -v "$MAIN_BRANCH"' not in text
    assert '[ "$branch" = "$MAIN_BRANCH" ] && continue' in text


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Branch classification
***REMOVED*** ---------------------------------------------------------------------------


def _branch(gh, name: str, **overrides):
    info = gh.BranchInfo(name=name)
    for key, value in overrides.items():
        setattr(info, key, value)
    return info


def test_classify_current_branch_is_protected(gh) -> None:
    info = _branch(gh, "feature/x", is_current=True, merged_into_base=True)
    out = gh.classify_branch(info, base="dev")
    assert out.category == "protected"
    assert "current branch" in out.reasons


def test_classify_base_branch_is_protected(gh) -> None:
    info = _branch(gh, "dev", merged_into_base=True)
    out = gh.classify_branch(info, base="dev")
    assert out.category == "protected"
    assert any("base branch" in r for r in out.reasons)


@pytest.mark.parametrize("name", ["main", "master", "develop"])
def test_classify_long_lived_branch_is_protected(gh, name: str) -> None:
    out = gh.classify_branch(_branch(gh, name), base="dev")
    assert out.category == "protected"


def test_classify_merged_with_upstream_is_safe_to_delete(gh) -> None:
    info = _branch(
        gh,
        "feature/done",
        upstream="origin/feature/done",
        merged_into_base=True,
    )
    out = gh.classify_branch(info, base="dev")
    assert out.category == "safe-to-delete"
    assert any("merged into dev" in r for r in out.reasons)


def test_classify_no_upstream_is_requires_human(gh) -> None:
    info = _branch(
        gh,
        "feature/local-only",
        upstream=None,
        merged_into_base=True,
    )
    out = gh.classify_branch(info, base="dev")
    assert out.category == "requires-human"
    assert "no upstream" in out.reasons


def test_classify_upstream_gone_is_requires_human(gh) -> None:
    info = _branch(
        gh,
        "feature/orphan",
        upstream="origin/feature/orphan",
        upstream_gone=True,
        merged_into_base=True,
    )
    out = gh.classify_branch(info, base="dev")
    assert out.category == "requires-human"
    assert "upstream gone" in out.reasons


def test_classify_ahead_of_upstream_is_requires_human(gh) -> None:
    info = _branch(
        gh,
        "feature/wip",
        upstream="origin/feature/wip",
        ahead=3,
        merged_into_base=True,
    )
    out = gh.classify_branch(info, base="dev")
    assert out.category == "requires-human"
    assert any("3 commit(s) ahead" in r for r in out.reasons)


def test_classify_unmerged_is_requires_human(gh) -> None:
    info = _branch(
        gh,
        "feature/wip",
        upstream="origin/feature/wip",
        merged_into_base=False,
    )
    out = gh.classify_branch(info, base="dev")
    assert out.category == "requires-human"
    assert any("not merged into dev" in r for r in out.reasons)


def test_classify_dirty_worktree_blocks_safe_deletion(gh) -> None:
    """Even merged + upstream-tracked branch is requires-human if its worktree is dirty."""
    info = _branch(
        gh,
        "feature/done-but-dirty",
        upstream="origin/feature/done-but-dirty",
        merged_into_base=True,
        worktree_path="/tmp/wt",
        worktree_dirty=True,
    )
    out = gh.classify_branch(info, base="dev")
    assert out.category == "requires-human"
    assert any("uncommitted changes in worktree" in r for r in out.reasons)


def test_classify_clean_worktree_attached_branch_is_requires_human(gh) -> None:
    """Branch is checked out in a worktree -> ``git branch -d`` would fail; surface it."""
    info = _branch(
        gh,
        "feature/checked-out",
        upstream="origin/feature/checked-out",
        merged_into_base=True,
        worktree_path="/projects/sandbox/wt",
        worktree_dirty=False,
    )
    out = gh.classify_branch(info, base="dev")
    assert out.category == "requires-human"
    assert any("checked out at" in r for r in out.reasons)


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Worktree classification
***REMOVED*** ---------------------------------------------------------------------------


def test_worktree_clean_repo_is_safe(gh) -> None:
    wt = gh.WorktreeInfo(path="/projects/sandbox/rag", branch="dev")
    assert wt.category == "safe"
    assert wt.reasons == []


def test_worktree_in_tmp_is_requires_human(gh) -> None:
    wt = gh.WorktreeInfo(path="/tmp/scratch", branch="feature/x", in_tmp=True)
    assert wt.category == "requires-human"
    assert "in /tmp" in wt.reasons


def test_worktree_detached_is_requires_human(gh) -> None:
    wt = gh.WorktreeInfo(path="/srv/wt", detached=True)
    assert wt.category == "requires-human"
    assert "detached HEAD" in wt.reasons


def test_worktree_dirty_is_requires_human(gh) -> None:
    wt = gh.WorktreeInfo(path="/srv/wt", branch="feature/x", dirty=True)
    assert wt.category == "requires-human"
    assert "uncommitted changes" in wt.reasons


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Report contracts
***REMOVED*** ---------------------------------------------------------------------------


def test_report_total_issues_excludes_protected(gh) -> None:
    branches = [
        gh.BranchInfo(name="dev", category="protected", reasons=["base branch (dev)"]),
        gh.BranchInfo(name="feature/done", category="safe-to-delete"),
        gh.BranchInfo(name="feature/wip", category="requires-human", reasons=["x"]),
    ]
    worktrees = [
        gh.WorktreeInfo(path="/srv/clean"),
        gh.WorktreeInfo(path="/tmp/scratch", in_tmp=True),
    ]
    report = gh.HygieneReport(branches=branches, worktrees=worktrees, transient_files=["a.log"])

    assert report.total_issues == 4  ***REMOVED*** 1 safe + 1 requires-human + 1 stale wt + 1 transient


def test_report_backward_compat_keys(gh) -> None:
    branches = [
        gh.BranchInfo(name="feature/done", category="safe-to-delete"),
        gh.BranchInfo(
            name="feature/local",
            category="requires-human",
            reasons=["no upstream"],
        ),
    ]
    worktrees = [gh.WorktreeInfo(path="/tmp/old", in_tmp=True)]
    report = gh.HygieneReport(branches=branches, worktrees=worktrees)

    assert report.merged_branches == ["feature/done"]
    assert report.no_upstream_branches == ["feature/local"]
    assert report.stale_worktrees == [{"path": "/tmp/old", "reason": "in /tmp"}]


def test_report_to_dict_contains_classification_view(gh) -> None:
    report = gh.HygieneReport(
        branches=[gh.BranchInfo(name="feature/done", category="safe-to-delete")],
    )
    payload = report.to_dict()
    ***REMOVED*** Round-trip JSON to make sure it is serialisable.
    encoded = json.loads(json.dumps(payload))
    assert "classification" in encoded
    assert encoded["classification"]["safe_to_delete"][0]["name"] == "feature/done"
    ***REMOVED*** Backward-compat top-level keys remain in place.
    assert "merged_branches" in encoded
    assert "no_upstream_branches" in encoded


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Cleanup safety
***REMOVED*** ---------------------------------------------------------------------------


def test_fix_safe_branches_dry_run_does_not_invoke_git(monkeypatch, gh) -> None:
    calls: list[list[str]] = []

    def fake_run(*args, **kwargs):  ***REMOVED*** pragma: no cover - guard
        calls.append(list(args[0]))
        raise AssertionError("subprocess.run must not be invoked in dry-run")

    monkeypatch.setattr(gh.subprocess, "run", fake_run)

    deleted = gh.fix_safe_branches(
        [gh.BranchInfo(name="feature/x", category="safe-to-delete")],
        dry_run=True,
        quiet=True,
    )
    assert deleted == ["feature/x"]
    assert calls == []


def test_fix_safe_branches_invokes_git_branch_d(monkeypatch, gh) -> None:
    seen: list[list[str]] = []

    class _Result:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen.append(list(cmd))
        return _Result()

    monkeypatch.setattr(gh.subprocess, "run", fake_run)

    deleted = gh.fix_safe_branches(
        [gh.BranchInfo(name="feature/done", category="safe-to-delete")],
        dry_run=False,
        quiet=True,
    )
    assert deleted == ["feature/done"]
    assert seen == [["git", "branch", "-d", "feature/done"]]


def test_fix_merged_branches_backward_compat_shim(monkeypatch, gh) -> None:
    """Existing callers passing list[str] still work."""
    seen: list[list[str]] = []

    class _Result:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen.append(list(cmd))
        return _Result()

    monkeypatch.setattr(gh.subprocess, "run", fake_run)
    deleted = gh.fix_merged_branches(["feature/done"], dry_run=False, quiet=True)
    assert deleted == ["feature/done"]
    assert seen == [["git", "branch", "-d", "feature/done"]]


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** CLI argparse safety
***REMOVED*** ---------------------------------------------------------------------------


def test_cli_dry_run_requires_fix(gh, capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        old_argv = sys.argv
        sys.argv = ["git_hygiene.py", "--dry-run"]
        try:
            gh.main()
        finally:
            sys.argv = old_argv
    assert exc_info.value.code != 0
    err = capsys.readouterr().err
    assert "--dry-run requires --fix" in err


def test_cli_include_requires_human_requires_fix(gh, capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        old_argv = sys.argv
        sys.argv = ["git_hygiene.py", "--include-requires-human"]
        try:
            gh.main()
        finally:
            sys.argv = old_argv
    assert exc_info.value.code != 0
    err = capsys.readouterr().err
    assert "--include-requires-human requires --fix" in err
