"""Process healthcheck for the LiveKit voice-agent container."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path


def _cmdline_matches_voice_agent(cmdline: Sequence[str]) -> bool:
    """Return True for the expected `python -m src.voice.agent start` process."""
    return any(
        arg == "-m"
        and index + 2 < len(cmdline)
        and cmdline[index + 1] == "src.voice.agent"
        and cmdline[index + 2] == "start"
        for index, arg in enumerate(cmdline)
    )


def is_voice_agent_running(
    proc_root: Path = Path("/proc"),
    *,
    current_pid: int | None = None,
) -> bool:
    current_pid = os.getpid() if current_pid is None else current_pid
    for entry in proc_root.iterdir():
        if not entry.name.isdigit() or int(entry.name) == current_pid:
            continue
        try:
            raw_cmdline = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if not raw_cmdline:
            continue
        cmdline = [part.decode(errors="ignore") for part in raw_cmdline.split(b"\0") if part]
        if _cmdline_matches_voice_agent(cmdline):
            return True
    return False


def main() -> int:
    return 0 if is_voice_agent_running() else 1


if __name__ == "__main__":
    raise SystemExit(main())
