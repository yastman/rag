#!/usr/bin/env python3
"""Install or check WSL auto-start watcher services for codeindexer and codegraph.

Generates idempotent user systemd units so that codeindexer and codegraph start
automatically when the WSL session starts.

Usage:
    # Preview units without writing files
    python scripts/wsl_agent_watchers.py --dry-run --repo-root /home/user/projects/rag-fresh

    # Check whether systemd is available and report status
    python scripts/wsl_agent_watchers.py --check --repo-root /home/user/projects/rag-fresh

    # Install units
    python scripts/wsl_agent_watchers.py --install --repo-root /home/user/projects/rag-fresh

    # Install with custom directories (useful in tests)
    python scripts/wsl_agent_watchers.py --install --repo-root /repo \\
        --user-systemd-dir /custom/systemd/user \\
        --config-root /custom/config
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path


# Default systemd user directory per the XDG Base Directory Specification.
_DEFAULT_SYSTEMD_USER_DIR = os.path.expanduser("~/.config/systemd/user")


def create_codeindexer_unit(
    repo_root: str,
    port: int = 8978,
    codeindexer_bin: str = "codeindexer",
) -> str:
    """Generate a systemd user unit for codeindexer."""
    return f"""[Unit]
Description=CodeIndexer MCP Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={codeindexer_bin} serve --host 127.0.0.1 --port {port}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


def create_codegraph_unit(repo_root: str, npx_bin: str = "npx") -> str:
    """Generate a systemd user unit that keeps the CodeGraph watcher active."""
    command = " ".join(
        [
            "tail -f /dev/null |",
            shlex.quote(npx_bin),
            "-y",
            "@colbymchenry/codegraph",
            "serve",
            "--mcp",
            "--path",
            shlex.quote(repo_root),
        ],
    )
    return f"""[Unit]
Description=CodeGraph RAG-Fresh Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/env bash -lc {shlex.quote(command)}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


def check_systemd_available() -> bool:
    """Return True if user systemd is available for user services."""
    systemctl = shutil.which("systemctl")
    if systemctl is None:
        return False

    try:
        result = subprocess.run(  # nosec B603
            [systemctl, "--user", "is-system-running"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    state = result.stdout.strip().lower()
    return state in {"running", "degraded"}


def write_unit_file(name: str, content: str, dir_path: str) -> Path:
    """Write a systemd unit file at ``dir_path / name``, creating parent dirs."""
    dest = Path(dir_path) / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage WSL auto-start watcher systemd user units.",
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the unit contents without writing any files.",
    )
    mode_group.add_argument(
        "--check",
        action="store_true",
        help="Check systemd availability and report status (non-destructive).",
    )
    mode_group.add_argument(
        "--install",
        action="store_true",
        help="Write the unit files to the user systemd directory.",
    )

    parser.add_argument(
        "--repo-root",
        required=True,
        help="Absolute path to the repository root (used by codegraph --path).",
    )
    parser.add_argument(
        "--user-systemd-dir",
        default=_DEFAULT_SYSTEMD_USER_DIR,
        help=(f"Directory for user systemd unit files (default: {_DEFAULT_SYSTEMD_USER_DIR})."),
    )
    parser.add_argument(
        "--config-root",
        default=None,
        help=(
            "Optional config root for tools that read a config file. "
            "Not used by the units themselves; accepted for future compatibility."
        ),
    )
    parser.add_argument(
        "--codeindexer-bin",
        default=shutil.which("codeindexer") or "codeindexer",
        help="Path to codeindexer executable used in codeindexer.service.",
    )
    parser.add_argument(
        "--npx-bin",
        default=shutil.which("npx") or "npx",
        help="Path to npx executable used in codegraph-rag-fresh.service.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # Resolve repo_root: just accept it as-is; codegraph unit embeds it literally.
    repo_root = args.repo_root

    codeindexer_content = create_codeindexer_unit(
        repo_root=repo_root,
        codeindexer_bin=args.codeindexer_bin,
    )
    codegraph_content = create_codegraph_unit(
        repo_root=repo_root,
        npx_bin=args.npx_bin,
    )

    if args.dry_run:
        print("=== codeindexer.service ===")
        print(codeindexer_content)
        print("=== codegraph-rag-fresh.service ===")
        print(codegraph_content)
        print("\nDry-run complete — no files were written.")
        sys.exit(0)

    if args.check:
        if not check_systemd_available():
            print(
                "user systemd is not available or is not running.",
                file=sys.stderr,
            )
            print(
                "WSL auto-start watchers require `systemctl --user`.",
                file=sys.stderr,
            )
            sys.exit(1)

        print("systemctl: available")
        print(f"User systemd dir: {args.user_systemd_dir}")
        codeidx_path = Path(args.user_systemd_dir) / "codeindexer.service"
        codegraph_path = Path(args.user_systemd_dir) / "codegraph-rag-fresh.service"

        if codeidx_path.exists():
            print(f"  {codeidx_path} — present")
        else:
            print(f"  {codeidx_path} — not installed")

        if codegraph_path.exists():
            print(f"  {codegraph_path} — present")
        else:
            print(f"  {codegraph_path} — not installed")

        sys.exit(0)

    if args.install:
        unit_dir = args.user_systemd_dir
        write_unit_file("codeindexer.service", codeindexer_content, unit_dir)
        write_unit_file("codegraph-rag-fresh.service", codegraph_content, unit_dir)
        print(f"Installed codeindexer.service to {unit_dir}")
        print(f"Installed codegraph-rag-fresh.service to {unit_dir}")
        print("\nTo enable and start the units:")
        print("  systemctl --user daemon-reload")
        print("  systemctl --user enable codeindexer.service codegraph-rag-fresh.service")
        print("  systemctl --user start codeindexer.service codegraph-rag-fresh.service")
        sys.exit(0)

    # Should not reach here due to mutually exclusive group; defensive.
    print("Error: no mode selected. Use --dry-run, --check, or --install.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
