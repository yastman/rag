"""tmux orchestrator identity management.

Solves the problem of orchestrator not tracking its own window name
across multiple Bash tool calls where shell state doesn't persist.

Usage (orchestrator):
    # Init: discover window, generate ID, rename, save state
    ORCH_ID=$(python scripts/tmux_orch_identity.py init)

    # Get saved ORCH_ID later
    ORCH_ID=$(python scripts/tmux_orch_identity.py get)

    # Get webhook target for worker prompts
    TARGET=$(python scripts/tmux_orch_identity.py webhook-target)
    # → claude:ORCH-a1b2c3d4

Usage (worker webhook — 3 separate calls as required by skill):
    python scripts/tmux_orch_identity.py worker-notify W-FIX "check logs/worker-fix.log"
    sleep 1
    python scripts/tmux_orch_identity.py worker-enter

Or generate commands for prompt injection:
    python scripts/tmux_orch_identity.py webhook-commands W-FIX
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


DEFAULT_IDENTITY_PATH = Path(".claude/orch-identity.json")


class OrchIdentity:
    """Manages tmux orchestrator window identity."""

    def __init__(self) -> None:
        self.session: str | None = None
        self.window_index: str | None = None
        self.orch_id: str | None = None

    def generate_id(self) -> str:
        """Generate unique ORCH-{8 hex chars} id."""
        self.orch_id = f"ORCH-{os.urandom(4).hex()}"
        return self.orch_id

    def discover(self) -> None:
        """Get own window info via $TMUX_PANE.

        CRITICAL: display-message without -t returns the CLIENT's active window
        (where the user is looking), NOT the window where this process runs.
        Must use -t $TMUX_PANE to target our exact pane.
        """
        pane = os.environ.get("TMUX_PANE", "")
        target_args = ["-t", pane] if pane else []

        session_result = subprocess.run(
            ["tmux", "display-message", *target_args, "-p", "#{session_name}"],
            capture_output=True,
            text=True,
        )
        if session_result.returncode != 0:
            msg = f"tmux display-message failed: {session_result.stderr}"
            raise RuntimeError(msg)

        self.session = session_result.stdout.strip()

        window_result = subprocess.run(
            ["tmux", "display-message", *target_args, "-p", "#{window_index}"],
            capture_output=True,
            text=True,
        )
        if window_result.returncode != 0:
            msg = f"tmux display-message failed: {window_result.stderr}"
            raise RuntimeError(msg)

        self.window_index = window_result.stdout.strip()

    def rename(self) -> None:
        """Rename own window. Uses TMUX='' + -t to target own window, not user's."""
        if not self.session or not self.window_index:
            msg = "Must call discover() first"
            raise RuntimeError(msg)
        if not self.orch_id:
            msg = "Must call generate_id() first"
            raise RuntimeError(msg)

        env = {**os.environ, "TMUX": ""}
        target = f"{self.session}:{self.window_index}"

        subprocess.run(
            ["tmux", "rename-window", "-t", target, self.orch_id],
            env=env,
            check=True,
        )
        subprocess.run(
            ["tmux", "set-option", "-t", target, "-w", "automatic-rename", "off"],
            env=env,
            check=True,
        )

    def webhook_target(self) -> str:
        """Return target for worker webhooks: session:ORCH_ID (NAME, not INDEX)."""
        if not self.session:
            msg = "session not set — call discover() or load()"
            raise RuntimeError(msg)
        if not self.orch_id:
            msg = "orch_id not set — call generate_id() or load()"
            raise RuntimeError(msg)
        return f"{self.session}:{self.orch_id}"

    def send_keys_command(self, text: str, *, raw: bool = False) -> str:
        """Build tmux send-keys command for worker prompt injection."""
        target = self.webhook_target()
        if raw:
            return f'TMUX="" tmux send-keys -t "{target}" {text}'
        return f'TMUX="" tmux send-keys -t "{target}" "{text}"'

    def new_window_command(self, name: str, working_dir: str) -> str:
        """Build tmux new-window command for spawning workers."""
        if not self.session:
            msg = "session not set"
            raise RuntimeError(msg)
        return f'TMUX="" tmux new-window -t "{self.session}" -n "{name}" -c "{working_dir}"'

    def kill_window_command(self, name: str) -> str:
        """Build tmux kill-window command (by NAME, not index)."""
        if not self.session:
            msg = "session not set"
            raise RuntimeError(msg)
        return f'TMUX="" tmux kill-window -t "{self.session}:{name}" 2>/dev/null'

    def save(self, path: Path | str = DEFAULT_IDENTITY_PATH) -> None:
        """Persist identity to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "session": self.session,
            "window_index": self.window_index,
            "orch_id": self.orch_id,
            "webhook_target": f"{self.session}:{self.orch_id}",
        }
        path.write_text(json.dumps(data, indent=2) + "\n")

    @classmethod
    def load(cls, path: Path | str = DEFAULT_IDENTITY_PATH) -> OrchIdentity:
        """Load identity from JSON file."""
        path = Path(path)
        if not path.exists():
            # Worktree fallback: resolve via git common-dir to main repo
            common = subprocess.run(
                ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if common:
                fallback = Path(common).parent / path
                if fallback.exists():
                    path = fallback
        if not path.exists():
            raise FileNotFoundError(path)
        data = json.loads(path.read_text())
        ident = cls()
        ident.session = data["session"]
        ident.window_index = data["window_index"]
        ident.orch_id = data["orch_id"]
        return ident

    @classmethod
    def init(cls, save_path: Path | str = DEFAULT_IDENTITY_PATH) -> OrchIdentity:
        """Full flow: discover → generate → rename → save."""
        ident = cls()
        ident.discover()
        ident.generate_id()
        ident.rename()
        ident.save(save_path)
        return ident


def _cli() -> None:
    """CLI entrypoint for orchestrator and worker usage."""
    if len(sys.argv) < 2:
        print("Usage: tmux_orch_identity.py <init|get|webhook-target|webhook-commands>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "init":
        ident = OrchIdentity.init()
        print(ident.orch_id)

    elif cmd == "get":
        ident = OrchIdentity.load()
        print(ident.orch_id)

    elif cmd == "webhook-target":
        ident = OrchIdentity.load()
        print(ident.webhook_target())

    elif cmd == "webhook-commands":
        # Generate webhook bash snippet for worker prompt injection
        if len(sys.argv) < 3:
            print("Usage: tmux_orch_identity.py webhook-commands W-NAME [message]")
            sys.exit(1)
        worker_name = sys.argv[2]
        message = sys.argv[3] if len(sys.argv) > 3 else f"{worker_name} COMPLETE"
        ident = OrchIdentity.load()
        # Print 3-call webhook snippet
        print(f"Вызов 1: {ident.send_keys_command(message)}")
        print("Вызов 2: sleep 1")
        print(f"Вызов 3: {ident.send_keys_command('Enter', raw=True)}")

    elif cmd == "worker-notify":
        # Worker sends text to orchestrator (call 1 of 3)
        if len(sys.argv) < 3:
            print("Usage: tmux_orch_identity.py worker-notify W-NAME [message]")
            sys.exit(1)
        worker_name = sys.argv[2]
        message = sys.argv[3] if len(sys.argv) > 3 else f"{worker_name} COMPLETE"
        try:
            ident = OrchIdentity.load()
        except FileNotFoundError:
            print("No orchestrator session active (missing .claude/orch-identity.json)")
            sys.exit(2)
        target = ident.webhook_target()
        env = {**os.environ, "TMUX": ""}
        subprocess.run(
            ["tmux", "send-keys", "-t", target, message],
            env=env,
            check=True,
        )

    elif cmd == "worker-enter":
        # Worker sends Enter to orchestrator (call 3 of 3)
        try:
            ident = OrchIdentity.load()
        except FileNotFoundError:
            print("No orchestrator session active (missing .claude/orch-identity.json)")
            sys.exit(2)
        target = ident.webhook_target()
        env = {**os.environ, "TMUX": ""}
        subprocess.run(
            ["tmux", "send-keys", "-t", target, "Enter"],
            env=env,
            check=True,
        )

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
