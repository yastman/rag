from __future__ import annotations

import argparse
import json
import subprocess
from typing import Any


def run_ssh(host: str, remote_cmd: str) -> str:
    completed = subprocess.run(
        ["ssh", host, remote_cmd],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _parse_compose_file(line: str) -> str:
    if "=" not in line:
        return ""
    return line.split("=", 1)[1].strip()


def _split_non_empty_lines(raw: str) -> list[str]:
    return [line for line in raw.splitlines() if line.strip()]


def build_inventory(host: str, project_dir: str) -> dict[str, Any]:
    compose_line = run_ssh(host, f"grep '^COMPOSE_FILE=' {project_dir}/.env")
    containers = run_ssh(host, "docker ps --format '{{.Names}}\t{{.Status}}'")
    networks = run_ssh(host, "docker network ls --format '{{.Name}}'")
    volumes = run_ssh(host, "docker volume ls --format '{{.Name}}'")

    return {
        "host": host,
        "project_dir": project_dir,
        "compose_file": _parse_compose_file(compose_line),
        "containers": _split_non_empty_lines(containers),
        "networks": _split_non_empty_lines(networks),
        "volumes": _split_non_empty_lines(volumes),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect VPS Docker runtime inventory")
    parser.add_argument("--host", default="vps", help="SSH host alias (default: vps)")
    parser.add_argument(
        "--project-dir",
        default="/opt/rag-fresh",
        help="Project directory on remote host (default: /opt/rag-fresh)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_inventory(host=args.host, project_dir=args.project_dir)
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
