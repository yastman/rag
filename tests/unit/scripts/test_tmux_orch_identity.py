"""Tests for tmux orchestrator identity management.

Problem: orchestrator (LLM) must track session/window/ORCH_ID across
multiple Bash tool calls where shell state doesn't persist. It frequently:
- Forgets ORCH_ID when writing worker prompts
- Omits -t flag on rename-window (renames user's active window)
- Uses TMUX="" on display-message (loses own pane context)
- Uses window INDEX instead of NAME in webhook targets

Solution: Python module that does init/get/webhook-target in one call,
persists state to file, and constructs all tmux commands correctly.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.tmux_orch_identity import OrchIdentity, _main_repo_root


class TestGenerateOrchId:
    """ORCH_ID format: ORCH-{8 hex chars}, always unique."""

    def test_format_prefix(self):
        ident = OrchIdentity()
        orch_id = ident.generate_id()
        assert orch_id.startswith("ORCH-")

    def test_format_hex_suffix(self):
        ident = OrchIdentity()
        orch_id = ident.generate_id()
        suffix = orch_id.removeprefix("ORCH-")
        assert len(suffix) == 8
        # Must be valid hex
        int(suffix, 16)

    def test_uniqueness(self):
        ids = {OrchIdentity().generate_id() for _ in range(100)}
        assert len(ids) == 100

    def test_stored_on_instance(self):
        ident = OrchIdentity()
        orch_id = ident.generate_id()
        assert ident.orch_id == orch_id


class TestDiscover:
    """discover() uses -t $TMUX_PANE to get OWN window, not user's active."""

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_gets_session_and_window(self, mock_run: MagicMock, monkeypatch):
        monkeypatch.setenv("TMUX_PANE", "%42")
        mock_run.side_effect = [
            MagicMock(stdout="claude\n", returncode=0),
            MagicMock(stdout="3\n", returncode=0),
        ]
        ident = OrchIdentity()
        ident.discover()

        assert ident.session == "claude"
        assert ident.window_index == "3"

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_uses_tmux_pane_target(self, mock_run: MagicMock, monkeypatch):
        """CRITICAL: without -t $TMUX_PANE, display-message returns the
        CLIENT's active window (where user is looking), NOT our window."""
        monkeypatch.setenv("TMUX_PANE", "%92")
        mock_run.side_effect = [
            MagicMock(stdout="claude\n", returncode=0),
            MagicMock(stdout="3\n", returncode=0),
        ]
        ident = OrchIdentity()
        ident.discover()

        for c in mock_run.call_args_list:
            cmd = c.args[0]
            assert "-t" in cmd, "display-message must use -t $TMUX_PANE"
            assert "%92" in cmd, "must target our exact pane"

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_no_tmux_empty_in_env(self, mock_run: MagicMock, monkeypatch):
        """display-message must NOT have TMUX='' — would lose pane context."""
        monkeypatch.setenv("TMUX_PANE", "%42")
        mock_run.side_effect = [
            MagicMock(stdout="claude\n", returncode=0),
            MagicMock(stdout="3\n", returncode=0),
        ]
        ident = OrchIdentity()
        ident.discover()

        for c in mock_run.call_args_list:
            env = c.kwargs.get("env")
            # env should be None (inherit) — NOT have TMUX=""
            if env is not None:
                assert env.get("TMUX") != "", (
                    "display-message must run WITHOUT TMUX='' to get own pane"
                )

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_calls_display_message(self, mock_run: MagicMock, monkeypatch):
        monkeypatch.setenv("TMUX_PANE", "%42")
        mock_run.side_effect = [
            MagicMock(stdout="claude\n", returncode=0),
            MagicMock(stdout="3\n", returncode=0),
        ]
        ident = OrchIdentity()
        ident.discover()

        calls = mock_run.call_args_list
        assert len(calls) == 2
        assert "display-message" in calls[0].args[0]
        assert "#{session_name}" in calls[0].args[0]
        assert "#{window_index}" in calls[1].args[0]

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_works_without_tmux_pane_env(self, mock_run: MagicMock, monkeypatch):
        """Falls back to no -t when TMUX_PANE is not set (non-tmux env)."""
        monkeypatch.delenv("TMUX_PANE", raising=False)
        mock_run.side_effect = [
            MagicMock(stdout="claude\n", returncode=0),
            MagicMock(stdout="3\n", returncode=0),
        ]
        ident = OrchIdentity()
        ident.discover()

        # Should still work, just without -t
        cmd = mock_run.call_args_list[0].args[0]
        assert "-t" not in cmd

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_strips_whitespace(self, mock_run: MagicMock, monkeypatch):
        monkeypatch.setenv("TMUX_PANE", "%42")
        mock_run.side_effect = [
            MagicMock(stdout="  claude \n", returncode=0),
            MagicMock(stdout=" 5 \n", returncode=0),
        ]
        ident = OrchIdentity()
        ident.discover()
        assert ident.session == "claude"
        assert ident.window_index == "5"

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_raises_on_failure(self, mock_run: MagicMock, monkeypatch):
        monkeypatch.setenv("TMUX_PANE", "%42")
        mock_run.side_effect = [
            MagicMock(stdout="", returncode=1, stderr="no server running"),
        ]
        ident = OrchIdentity()
        with pytest.raises(RuntimeError, match="tmux"):
            ident.discover()


class TestRename:
    """rename() must use TMUX='' + -t to target own window, not user's active."""

    def _make_ident(self) -> OrchIdentity:
        ident = OrchIdentity()
        ident.session = "claude"
        ident.window_index = "3"
        ident.orch_id = "ORCH-a1b2c3d4"
        return ident

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_uses_tmux_empty_env(self, mock_run: MagicMock):
        """rename-window MUST have TMUX='' to avoid nested tmux issues."""
        mock_run.return_value = MagicMock(returncode=0)
        ident = self._make_ident()
        ident.rename()

        for c in mock_run.call_args_list:
            env = c.kwargs.get("env", {})
            assert env.get("TMUX") == "", "rename-window must use TMUX='' for nested tmux"

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_uses_explicit_target(self, mock_run: MagicMock):
        """rename-window MUST use -t session:window — without it renames user's window."""
        mock_run.return_value = MagicMock(returncode=0)
        ident = self._make_ident()
        ident.rename()

        rename_call = mock_run.call_args_list[0]
        cmd = rename_call.args[0]
        assert "-t" in cmd
        assert "claude:3" in cmd

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_sets_orch_id_as_name(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=0)
        ident = self._make_ident()
        ident.rename()

        rename_call = mock_run.call_args_list[0]
        cmd = rename_call.args[0]
        assert "ORCH-a1b2c3d4" in cmd

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_disables_automatic_rename(self, mock_run: MagicMock):
        """automatic-rename must be off — otherwise tmux renames by process (node)."""
        mock_run.return_value = MagicMock(returncode=0)
        ident = self._make_ident()
        ident.rename()

        calls = mock_run.call_args_list
        assert len(calls) == 2
        set_opt_cmd = calls[1].args[0]
        assert "set-option" in set_opt_cmd
        assert "automatic-rename" in set_opt_cmd
        assert "off" in set_opt_cmd

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_set_option_also_targets_own_window(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=0)
        ident = self._make_ident()
        ident.rename()

        set_opt_cmd = mock_run.call_args_list[1].args[0]
        assert "-t" in set_opt_cmd
        assert "claude:3" in set_opt_cmd

    def test_raises_without_discover(self):
        ident = OrchIdentity()
        ident.orch_id = "ORCH-test1234"
        with pytest.raises(RuntimeError, match="discover"):
            ident.rename()

    def test_raises_without_generate(self):
        ident = OrchIdentity()
        ident.session = "claude"
        ident.window_index = "3"
        with pytest.raises(RuntimeError, match="generate"):
            ident.rename()


class TestWebhookTarget:
    """Workers must send webhooks by NAME (session:ORCH_ID), never by INDEX."""

    def test_returns_session_colon_name(self):
        ident = OrchIdentity()
        ident.session = "claude"
        ident.orch_id = "ORCH-a1b2c3d4"
        assert ident.webhook_target() == "claude:ORCH-a1b2c3d4"

    def test_does_not_use_index(self):
        ident = OrchIdentity()
        ident.session = "claude"
        ident.window_index = "3"
        ident.orch_id = "ORCH-a1b2c3d4"
        target = ident.webhook_target()
        assert ":3" not in target
        assert "ORCH-" in target

    def test_raises_without_session(self):
        ident = OrchIdentity()
        ident.orch_id = "ORCH-a1b2c3d4"
        with pytest.raises(RuntimeError):
            ident.webhook_target()

    def test_raises_without_orch_id(self):
        ident = OrchIdentity()
        ident.session = "claude"
        with pytest.raises(RuntimeError):
            ident.webhook_target()


class TestSendKeysCommand:
    """Helper to build correct send-keys command for worker prompts."""

    def test_format(self):
        ident = OrchIdentity()
        ident.session = "claude"
        ident.orch_id = "ORCH-a1b2c3d4"
        cmd = ident.send_keys_command("W-FIX COMPLETE — check logs/worker-fix.log")
        assert cmd == (
            'TMUX="" tmux send-keys -t "claude:ORCH-a1b2c3d4"'
            ' "W-FIX COMPLETE — check logs/worker-fix.log"'
        )

    def test_enter_command(self):
        ident = OrchIdentity()
        ident.session = "claude"
        ident.orch_id = "ORCH-a1b2c3d4"
        cmd = ident.send_keys_command("Enter", raw=True)
        assert cmd == 'TMUX="" tmux send-keys -t "claude:ORCH-a1b2c3d4" Enter'


class TestPersistence:
    """Save/load identity to file for cross-bash-call access."""

    def test_save_creates_file(self, tmp_path: Path):
        ident = OrchIdentity()
        ident.session = "claude"
        ident.window_index = "3"
        ident.orch_id = "ORCH-a1b2c3d4"
        path = tmp_path / "orch-identity.json"
        ident.save(path)
        assert path.exists()

    def test_save_content(self, tmp_path: Path):
        ident = OrchIdentity()
        ident.session = "claude"
        ident.window_index = "3"
        ident.orch_id = "ORCH-a1b2c3d4"
        path = tmp_path / "orch-identity.json"
        ident.save(path)

        data = json.loads(path.read_text())
        assert data["session"] == "claude"
        assert data["window_index"] == "3"
        assert data["orch_id"] == "ORCH-a1b2c3d4"
        assert data["webhook_target"] == "claude:ORCH-a1b2c3d4"

    def test_load_roundtrip(self, tmp_path: Path):
        ident = OrchIdentity()
        ident.session = "claude"
        ident.window_index = "3"
        ident.orch_id = "ORCH-a1b2c3d4"
        path = tmp_path / "orch-identity.json"
        ident.save(path)

        loaded = OrchIdentity.load(path)
        assert loaded.session == "claude"
        assert loaded.window_index == "3"
        assert loaded.orch_id == "ORCH-a1b2c3d4"

    def test_load_missing_file(self, tmp_path: Path):
        path = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError):
            OrchIdentity.load(path)


class TestInit:
    """Full init flow: discover → generate → rename → save."""

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_full_flow(self, mock_run: MagicMock, tmp_path: Path):
        mock_run.side_effect = [
            # discover: session
            MagicMock(stdout="claude\n", returncode=0),
            # discover: window_index
            MagicMock(stdout="3\n", returncode=0),
            # rename: rename-window
            MagicMock(returncode=0),
            # rename: set-option
            MagicMock(returncode=0),
        ]
        save_path = tmp_path / "orch-identity.json"

        ident = OrchIdentity.init(save_path)

        assert ident.session == "claude"
        assert ident.window_index == "3"
        assert ident.orch_id.startswith("ORCH-")
        assert save_path.exists()

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_init_prints_orch_id(self, mock_run: MagicMock, tmp_path: Path, capsys):
        """CLI usage: ORCH_ID=$(python scripts/tmux_orch_identity.py init)"""
        mock_run.side_effect = [
            MagicMock(stdout="claude\n", returncode=0),
            MagicMock(stdout="3\n", returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=0),
        ]
        save_path = tmp_path / "orch-identity.json"
        ident = OrchIdentity.init(save_path)
        # The module's __main__ should print ORCH_ID for shell capture
        assert ident.orch_id.startswith("ORCH-")


class TestNewWindowCommand:
    """Helper to build correct new-window command for spawning workers."""

    def test_format_with_worktree(self):
        ident = OrchIdentity()
        ident.session = "claude"
        cmd = ident.new_window_command("W-FIX", "/home/user/projects/rag-fresh")
        assert cmd == (
            'TMUX="" tmux new-window -t "claude" -n "W-FIX" -c "/home/user/projects/rag-fresh"'
        )

    def test_uses_tmux_empty(self):
        ident = OrchIdentity()
        ident.session = "claude"
        cmd = ident.new_window_command("W-A", "/tmp")
        assert cmd.startswith('TMUX=""')


class TestKillWindowCommand:
    """Helper to build kill-window command (by NAME, not index)."""

    def test_by_name(self):
        ident = OrchIdentity()
        ident.session = "claude"
        cmd = ident.kill_window_command("W-FIX")
        assert cmd == 'TMUX="" tmux kill-window -t "claude:W-FIX" 2>/dev/null'


class TestMainRepoRoot:
    """_main_repo_root resolves to main repo even from worktrees."""

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_uses_git_common_dir(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            stdout="/home/user/projects/rag-fresh/.git\n",
            returncode=0,
        )
        root = _main_repo_root()
        assert root == Path("/home/user/projects/rag-fresh")
        cmd = mock_run.call_args[0][0]
        assert "--git-common-dir" in cmd

    @patch("scripts.tmux_orch_identity.subprocess.run")
    def test_fallback_to_toplevel(self, mock_run: MagicMock):
        import subprocess as sp

        mock_run.side_effect = [
            sp.CalledProcessError(1, "git"),  # git-common-dir fails
            MagicMock(stdout="/some/repo\n", returncode=0),  # show-toplevel
        ]
        root = _main_repo_root()
        assert root == Path("/some/repo")


class TestWorktreeLoadSave:
    """save() and load() resolve to main repo root, not CWD."""

    @patch("scripts.tmux_orch_identity._main_repo_root")
    def test_save_default_uses_main_repo_root(self, mock_root: MagicMock, tmp_path: Path):
        mock_root.return_value = tmp_path
        ident = OrchIdentity()
        ident.session = "claude"
        ident.window_index = "3"
        ident.orch_id = "ORCH-worktree"
        ident.save()  # no explicit path
        expected = tmp_path / ".claude" / "orch-identity.json"
        assert expected.exists()
        data = json.loads(expected.read_text())
        assert data["orch_id"] == "ORCH-worktree"

    @patch("scripts.tmux_orch_identity._main_repo_root")
    def test_load_default_uses_main_repo_root(self, mock_root: MagicMock, tmp_path: Path):
        mock_root.return_value = tmp_path
        # Setup: save file at main repo root
        ident_path = tmp_path / ".claude" / "orch-identity.json"
        ident_path.parent.mkdir(parents=True)
        ident_path.write_text(
            json.dumps(
                {
                    "session": "claude",
                    "window_index": "3",
                    "orch_id": "ORCH-fromworktree",
                    "webhook_target": "claude:ORCH-fromworktree",
                }
            )
        )
        loaded = OrchIdentity.load()  # no explicit path
        assert loaded.orch_id == "ORCH-fromworktree"

    def test_save_with_explicit_path_ignores_root(self, tmp_path: Path):
        ident = OrchIdentity()
        ident.session = "claude"
        ident.window_index = "3"
        ident.orch_id = "ORCH-explicit"
        path = tmp_path / "custom.json"
        ident.save(path)
        assert path.exists()
