#!/usr/bin/env python3
"""Preflight guard for trace validation runtime safety."""

from __future__ import annotations

import argparse
import os
import subprocess  # nosec
import sys
from pathlib import Path


CI_ENV_FILE = Path("tests/fixtures/compose.ci.env")
POSTGRES_VOLUME_SUFFIX = "postgres_data"
LOCAL_DEFAULT_POSTGRES_VALUE = "postgres"


def _parse_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def _volume_exists(volume_name: str) -> bool:
    try:
        # nosec: fixed local docker subcommand with no shell expansion.
        result = subprocess.run(  # nosec
            ["docker", "volume", "inspect", volume_name],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


def _resolve_env_path(repo_root: Path, env_file: str) -> Path:
    path = Path(env_file)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def _resolve_project_name(
    compose_project_name: str | None,
    env_file_values: dict[str, str],
) -> str:
    if compose_project_name:
        return compose_project_name
    from_env = os.getenv("COMPOSE_PROJECT_NAME")
    if from_env:
        return from_env
    return env_file_values.get("COMPOSE_PROJECT_NAME", "dev")


def _uses_ci_env_fallback(repo_root: Path, env_path: Path) -> bool:
    return env_path == (repo_root / CI_ENV_FILE).resolve()


def run_guard(
    *,
    repo_root: Path,
    env_file: str,
    compose_project_name: str | None = None,
) -> tuple[bool, str]:
    root = repo_root.resolve()
    env_path = _resolve_env_path(root, env_file)
    dotenv_path = root / ".env"

    if dotenv_path.exists():
        return True, ".env detected; skipping fallback Postgres volume guard."

    if not env_path.exists():
        return False, f"env file not found: {env_path}"

    env_values = _parse_env_file(env_path)
    project_name = _resolve_project_name(compose_project_name, env_values)
    volume_name = f"{project_name}_{POSTGRES_VOLUME_SUFFIX}"

    if not _uses_ci_env_fallback(root, env_path):
        return True, "non-fallback env file; guard not required."

    if "POSTGRES_PASSWORD" in os.environ:
        return True, "POSTGRES_PASSWORD override detected; skipping fallback mismatch guard."

    if not _volume_exists(volume_name):
        return True, f"volume {volume_name} not found; no auth-mismatch risk from reused volume."

    fallback_password = env_values.get("POSTGRES_PASSWORD", "")
    if fallback_password == LOCAL_DEFAULT_POSTGRES_VALUE:
        return (
            True,
            "fallback env uses local default POSTGRES_PASSWORD=postgres; existing dev volume is compatible.",
        )

    remediation = (
        "Postgres auth mismatch risk: validate-traces-fast is using "
        f"{CI_ENV_FILE}, but Docker volume '{volume_name}' already exists.\n"
        "This commonly means the volume was initialized with a different password "
        f"than fallback POSTGRES_PASSWORD='{fallback_password or '<missing>'}', and Langfuse will fail with Prisma P1000.\n"
        "Remediation:\n"
        "1) Create/update .env with POSTGRES_PASSWORD matching the existing dev volume.\n"
        "2) Or remove the old dev Postgres volume before re-running:\n"
        f"   docker volume rm {volume_name}\n"
        "3) Then run make validate-traces-fast again."
    )
    return False, remediation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Guard validate-traces-fast against silent Postgres auth mismatch loops."
    )
    parser.add_argument(
        "--env-file",
        required=True,
        help="Env file passed to docker compose (usually .env or tests/fixtures/compose.ci.env).",
    )
    parser.add_argument(
        "--compose-project-name",
        default=None,
        help="Optional explicit Compose project name override.",
    )
    args = parser.parse_args(argv)

    ok, message = run_guard(
        repo_root=Path.cwd(),
        env_file=args.env_file,
        compose_project_name=args.compose_project_name,
    )
    stream = sys.stdout if ok else sys.stderr
    print(message, file=stream)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
