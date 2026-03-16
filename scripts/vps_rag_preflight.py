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


def _docker_network_health_cmd(project_dir: str) -> str:
    # Run health checks inside the bot container so compose DNS names resolve.
    return (
        f"cd {project_dir} && "
        "docker compose exec -T bot sh -lc "
        '"QDRANT_URL=http://qdrant:6333 '
        "LLM_BASE_URL=http://litellm:4000 "
        "python - <<'PY'\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "import urllib.request\n"
        "\n"
        "qdrant_url = os.environ.get('QDRANT_URL', 'http://qdrant:6333')\n"
        "llm_url = os.environ.get('LLM_BASE_URL', 'http://litellm:4000')\n"
        "collection = os.environ.get('QDRANT_COLLECTION', 'contextual_bulgaria_voyage')\n"
        "mode = os.environ.get('QDRANT_QUANTIZATION_MODE', 'off')\n"
        "base = collection.removesuffix('_binary').removesuffix('_scalar')\n"
        "target = base\n"
        "if mode == 'scalar':\n"
        "    target = f'{base}_scalar'\n"
        "elif mode == 'binary':\n"
        "    target = f'{base}_binary'\n"
        "\n"
        "try:\n"
        "    with urllib.request.urlopen(f'{qdrant_url}/collections', timeout=15) as response:\n"
        "        payload = json.load(response)\n"
        "except Exception:\n"
        "    print(f'FAIL: Qdrant is unreachable at {qdrant_url}')\n"
        "    raise SystemExit(1)\n"
        "\n"
        "collections = payload.get('result', {}).get('collections', [])\n"
        "names = {item.get('name') for item in collections}\n"
        "if target not in names:\n"
        "    print(f\"FAIL: Qdrant collection '{target}' not found (mode={mode})\")\n"
        "    raise SystemExit(1)\n"
        "print(f'✓ Qdrant collection exists: {target} (mode={mode})')\n"
        "\n"
        "try:\n"
        "    urllib.request.urlopen(f'{llm_url}/health/liveliness', timeout=15)\n"
        "    print('✓ LLM health OK')\n"
        "except Exception:\n"
        "    try:\n"
        "        urllib.request.urlopen(f'{llm_url}/v1/models', timeout=15)\n"
        "        print('✓ LLM models OK')\n"
        "    except Exception:\n"
        "        print(f'FAIL: LLM endpoint not responding at {llm_url}')\n"
        "        raise SystemExit(1)\n"
        'PY"'
    )


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

    health_cmd = _docker_network_health_cmd(project_dir)
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
