"""Tests for dirty-worktree preflight guard."""

from unittest.mock import patch

import pytest


def test_clean_worktree_passes(tmp_path):
    """Clean worktree should not raise."""
    from scripts.validate_traces import check_worktree_clean

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        # Should not raise
        check_worktree_clean(strict=True)


def test_dirty_worktree_strict_fails(tmp_path):
    """Dirty worktree in strict mode should exit."""
    from scripts.validate_traces import check_worktree_clean

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        with pytest.raises(SystemExit):
            check_worktree_clean(strict=True)


def test_dirty_worktree_warn_only(tmp_path, caplog):
    """Dirty worktree in warn mode should log warning but not exit."""
    from scripts.validate_traces import check_worktree_clean

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        check_worktree_clean(strict=False)
        assert "dirty worktree" in caplog.text.lower() or "uncommitted" in caplog.text.lower()


def test_untracked_files_strict_fails(tmp_path):
    """Untracked files should be treated as dirty worktree."""
    from scripts.validate_traces import check_worktree_clean

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "?? notes.txt\n"
        with pytest.raises(SystemExit):
            check_worktree_clean(strict=True)
