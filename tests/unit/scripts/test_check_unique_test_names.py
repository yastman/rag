"""Self-tests for the duplicate-test-name ratchet (#1539, #3243).

The ratchet must be anchored to git-tracked paths only:

  - untracked scratch files can never create or grow a duplicate;
  - an allowlist entry pointing at an untracked/deleted path, at a file that
    no longer defines the symbol, or at a name that is no longer a tracked
    duplicate is a stale allowance and must fail loudly.

Library-level tests drive ``scripts/check_unique_test_names.py`` functions
against synthetic repos; CLI-level tests run the script as a subprocess with
``--repo-root`` pointed at those repos.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import check_unique_test_names as ratchet


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "check_unique_test_names.py"

FILE_A = """\
def test_dup():
    assert True

def test_unique_a():
    assert True
"""

FILE_B = """\
def test_dup():
    assert True

def test_unique_b():
    assert True
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _commit(repo: Path, *paths: str) -> None:
    _git(repo, "add", "--", *paths)
    _git(repo, "commit", "-q", "-m", "snapshot")


def _write(repo: Path, rel: str, body: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A minimal git repo with a tests/ tree ready for ratchet scenarios."""
    repo = tmp_path / "repo"
    (repo / "tests" / "data").mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "ratchet@example.com")
    _git(repo, "config", "user.name", "Ratchet Self-Test")
    return repo


def _run_cli(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        timeout=60,
    )


# --------------------------------------------------------------------------
# Tracked-path enumeration (the #3243 core fix)
# --------------------------------------------------------------------------


def test_tracked_test_files_enumerates_only_git_tracked_modules(git_repo: Path) -> None:
    _write(git_repo, "tests/test_a.py", FILE_A)
    _commit(git_repo, "tests/test_a.py")
    _write(git_repo, "tests/test_untracked.py", FILE_B)  # never committed
    _write(git_repo, "tests/helpers.py", "x = 1\n")  # not a test module

    assert ratchet.tracked_test_files(git_repo) == ["tests/test_a.py"]


def test_untracked_file_cannot_create_duplicate(git_repo: Path) -> None:
    """A duplicate that exists only via an untracked file must not trip the ratchet."""
    _write(git_repo, "tests/test_a.py", FILE_A)
    _commit(git_repo, "tests/test_a.py")
    _write(git_repo, "tests/test_untracked.py", FILE_B)  # same test_dup, untracked

    tracked = ratchet.tracked_test_files(git_repo)
    occurrences = ratchet.collect_occurrences(git_repo, tracked)
    violations = ratchet.check_ratchet(
        occurrences, ratchet.duplicate_names(occurrences), {}, tracked
    )
    assert violations == []


def test_untracked_file_cannot_mask_stale_allowance(git_repo: Path) -> None:
    """An untracked file must not resurrect a name so a stale entry passes."""
    _write(git_repo, "tests/test_a.py", FILE_A)
    _commit(git_repo, "tests/test_a.py")
    _write(git_repo, "tests/test_untracked.py", FILE_B)

    tracked = ratchet.tracked_test_files(git_repo)
    occurrences = ratchet.collect_occurrences(git_repo, tracked)
    allowlist = {"test_dup": ["tests/test_a.py", "tests/test_untracked.py"]}
    violations = ratchet.check_ratchet(
        occurrences, ratchet.duplicate_names(occurrences), allowlist, tracked
    )
    kinds = {v.kind for v in violations}
    assert "untracked_path" in kinds
    assert "not_duplicate" in kinds


# --------------------------------------------------------------------------
# Ratchet decisions
# --------------------------------------------------------------------------


def _scenario(git_repo: Path, *, commit_b: bool) -> tuple[dict, dict, list[str]]:
    _write(git_repo, "tests/test_a.py", FILE_A)
    if commit_b:
        _write(git_repo, "tests/test_b.py", FILE_B)
        _commit(git_repo, "tests/test_a.py", "tests/test_b.py")
    else:
        _commit(git_repo, "tests/test_a.py")
    tracked = ratchet.tracked_test_files(git_repo)
    occurrences = ratchet.collect_occurrences(git_repo, tracked)
    return occurrences, ratchet.duplicate_names(occurrences), tracked


def test_check_passes_on_matching_baseline(git_repo: Path) -> None:
    occurrences, duplicates, tracked = _scenario(git_repo, commit_b=True)
    allowlist = {"test_dup": ["tests/test_a.py", "tests/test_b.py"]}
    assert ratchet.check_ratchet(occurrences, duplicates, allowlist, tracked) == []


def test_check_flags_synthetic_duplicate(git_repo: Path) -> None:
    occurrences, duplicates, tracked = _scenario(git_repo, commit_b=True)
    violations = ratchet.check_ratchet(occurrences, duplicates, {}, tracked)
    assert [(v.kind, v.name) for v in violations] == [("new", "test_dup")]
    rendered = ratchet.render_violations(violations)
    assert "test_dup" in rendered
    assert "tests/test_a.py" in rendered and "tests/test_b.py" in rendered


def test_check_flags_expanded_duplicate(git_repo: Path) -> None:
    occurrences, duplicates, tracked = _scenario(git_repo, commit_b=True)
    allowlist = {"test_dup": ["tests/test_a.py"]}  # missing the second file
    violations = ratchet.check_ratchet(occurrences, duplicates, allowlist, tracked)
    kinds = {(v.kind, v.name) for v in violations}
    assert ("expanded", "test_dup") in kinds
    rendered = ratchet.render_violations(violations)
    assert "tests/test_b.py" in rendered


def test_check_flags_untracked_allowance(git_repo: Path) -> None:
    occurrences, duplicates, tracked = _scenario(git_repo, commit_b=True)
    allowlist = {
        "test_dup": ["tests/test_a.py", "tests/test_b.py", "tests/test_ghost.py"],
    }
    violations = ratchet.check_ratchet(occurrences, duplicates, allowlist, tracked)
    stale = [v for v in violations if v.kind == "untracked_path"]
    assert len(stale) == 1
    assert stale[0].name == "test_dup"
    assert "tests/test_ghost.py" in stale[0].detail
    # One valid occurrence remains, so the entry is not (yet) a non-duplicate.
    assert all(v.kind == "untracked_path" for v in violations)


def test_check_flags_missing_symbol(git_repo: Path) -> None:
    occurrences, duplicates, tracked = _scenario(git_repo, commit_b=True)
    _write(git_repo, "tests/test_b.py", "def test_renamed():\n    assert True\n")
    occurrences = ratchet.collect_occurrences(git_repo, tracked)
    duplicates = ratchet.duplicate_names(occurrences)
    allowlist = {"test_dup": ["tests/test_a.py", "tests/test_b.py"]}

    violations = ratchet.check_ratchet(occurrences, duplicates, allowlist, tracked)
    kinds = {(v.kind, v.name) for v in violations}
    assert ("missing_symbol", "test_dup") in kinds
    assert ("not_duplicate", "test_dup") in kinds
    rendered = ratchet.render_violations(violations)
    assert "tests/test_b.py no longer defines test_dup()" in rendered


def test_check_flags_no_longer_duplicate(git_repo: Path) -> None:
    """A fully renamed duplicate leaves a stale entry that must fail loudly."""
    occurrences, duplicates, tracked = _scenario(git_repo, commit_b=True)
    allowlist = {
        "test_dup": ["tests/test_a.py", "tests/test_b.py"],
        "test_gone": ["tests/test_a.py", "tests/test_b.py"],
    }
    violations = ratchet.check_ratchet(occurrences, duplicates, allowlist, tracked)
    kinds = {v.kind for v in violations}
    assert {"missing_symbol", "not_duplicate"} <= kinds
    assert {v.name for v in violations} == {"test_gone"}


# --------------------------------------------------------------------------
# CLI end-to-end (exit codes and loud, exact output)
# --------------------------------------------------------------------------


def test_cli_passes_on_tracked_suite(git_repo: Path) -> None:
    _write(git_repo, "tests/test_a.py", FILE_A)
    _write(git_repo, "tests/test_b.py", FILE_B)
    _commit(git_repo, "tests/test_a.py", "tests/test_b.py")
    _write(
        git_repo,
        "tests/data/known_duplicate_test_names.json",
        '{\n  "test_dup": ["tests/test_a.py", "tests/test_b.py"]\n}\n',
    )
    _commit(git_repo, "tests/data/known_duplicate_test_names.json")

    result = _run_cli(git_repo)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_cli_synthetic_duplicate_fails_with_exact_names(git_repo: Path) -> None:
    _write(git_repo, "tests/test_a.py", FILE_A)
    _write(git_repo, "tests/test_b.py", FILE_B)
    _commit(git_repo, "tests/test_a.py", "tests/test_b.py")
    _write(git_repo, "tests/data/known_duplicate_test_names.json", "{}\n")
    _commit(git_repo, "tests/data/known_duplicate_test_names.json")

    result = _run_cli(git_repo)
    assert result.returncode == 1
    assert "test_dup" in result.stderr
    assert "tests/test_a.py" in result.stderr
    assert "tests/test_b.py" in result.stderr


def test_cli_untracked_allowance_fails_loudly(git_repo: Path) -> None:
    _write(git_repo, "tests/test_a.py", FILE_A)
    _commit(git_repo, "tests/test_a.py")
    _write(
        git_repo,
        "tests/data/known_duplicate_test_names.json",
        '{\n  "test_dup": ["tests/test_a.py", "tests/test_ghost.py"]\n}\n',
    )
    _commit(git_repo, "tests/data/known_duplicate_test_names.json")

    result = _run_cli(git_repo)
    assert result.returncode == 1
    assert "test_dup" in result.stderr
    assert "tests/test_ghost.py" in result.stderr
