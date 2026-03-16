from __future__ import annotations

import argparse
import subprocess


LOGICAL_SERVICES = ("postgres", "redis", "qdrant", "bge-m3", "litellm", "bot")


def run_ssh(host: str, remote_cmd: str, *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", host, remote_cmd],
        capture_output=True,
        text=True,
        check=check,
    )


def _parse_docker_ps(raw: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        name, _, status = line.partition("\t")
        rows[name.strip()] = status.strip()
    return rows


def _service_variants(service: str) -> tuple[str, ...]:
    return (
        f"vps-{service}",
        f"vps_{service}_1",
        f"vps-{service}-1",
    )


def _status_for_service(services: dict[str, str], service: str) -> str:
    for candidate in _service_variants(service):
        status = services.get(candidate, "")
        if status:
            return status
    return ""


def _missing_or_unhealthy(services: dict[str, str]) -> list[str]:
    failed: list[str] = []
    for service in LOGICAL_SERVICES:
        status = _status_for_service(services, service)
        if not status or "Up" not in status:
            failed.append(f"vps-{service}")
    return failed


def run_preflight(host: str, project_dir: str) -> int:
    ps_result = run_ssh(host, "docker ps --format '{{.Names}}\t{{.Status}}'")
    if ps_result.returncode != 0:
        print(ps_result.stderr.strip() or "Failed to run docker ps on remote host")
        return 1

    services = _parse_docker_ps(ps_result.stdout)
    failed = _missing_or_unhealthy(services)
    if failed:
        print(f"Missing/unhealthy core services: {', '.join(failed)}")
        return 1

    health_cmd = (
        f"cd {project_dir} && "
        "QDRANT_URL=http://qdrant:6333 "
        "LLM_BASE_URL=http://litellm:4000 "
        "./scripts/test_bot_health.sh"
    )
    health_result = run_ssh(host, health_cmd)
    if health_result.returncode != 0:
        print(health_result.stdout.strip())
        print(health_result.stderr.strip())
        return 1

    output = health_result.stdout
    if "Qdrant" not in output or "LLM" not in output:
        print("Health output missing required checks (Qdrant and LLM)")
        return 1

    print(output.strip())
    print("VPS RAG preflight passed.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run VPS RAG preflight checks")
    parser.add_argument("--host", default="vps", help="SSH host alias (default: vps)")
    parser.add_argument(
        "--project-dir",
        default="/opt/rag-fresh",
        help="Project directory on remote host (default: /opt/rag-fresh)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_preflight(host=args.host, project_dir=args.project_dir)


if __name__ == "__main__":
    raise SystemExit(main())
