"""Strict deterministic six-service promotion gate; never reads operator secrets."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICES = {"postgres", "redis", "qdrant", "bge-m3", "bot", "ingestion"}
SUITES = (
    "tests/e2e_core/test_live_stack_required_live.py",
    "tests/e2e_core/test_qdrant_operational_live.py",
    "tests/e2e/test_redis_modes_live.py",
    "tests/e2e/test_core_live_ingest_answer.py",
    "tests/e2e/test_binary_quantization_live.py",
    "tests/e2e/test_postgres_capability.py",
    "tests/e2e/test_markdown_ingestion_capability.py",
    "tests/e2e/test_telegram_dispatch_capability.py",
    "tests/e2e/test_catalog_capability.py",
    "tests/e2e/test_funnel_lead_capability.py",
    "tests/e2e/test_handoff_capability.py",
    "tests/e2e/test_voice_capability.py",
    "tests/e2e/test_feedback_observability_capability.py",
)


def project_name(run_id: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{12}", run_id):
        raise ValueError("run id must be exactly 12 lowercase hexadecimal characters")
    return f"rag-e2e-{run_id}"


def strict_result(path: Path) -> int:
    """Even an otherwise successful pytest invocation cannot hide skips/empty selection."""
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    if not cases or any(list(root.iter(tag)) for tag in ("skipped", "failure", "error")):
        raise ValueError(f"required suite empty, skipped, blocked or failed: {path.name}")
    return len(cases)


def clean_environment() -> dict[str, str]:
    """Preserve OS/tool lookup only; no inherited service URLs, tokens or pytest options."""
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "TEMP",
        "TMP",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
    }
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def command(args: list[str], env: dict[str, str], *, timeout: int = 120) -> str:
    result = subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        # Tool output may contain environment values. Preserve it only for the
        # deterministic pytest invocation, whose environment is generated below.
        raise RuntimeError(
            f"{args[0]} command failed with exit {result.returncode}: "
            + (result.stderr or result.stdout)[-4000:]
        )
    return result.stdout.strip()


def service_snapshot(
    compose: list[str], project: str, env: dict[str, str], *, allow_qdrant_restart: bool = False
) -> list[dict]:
    ids = command([*compose, "ps", "-aq"], env).split()
    if not ids:
        raise ValueError("required containers are missing")
    # Select only names/ownership/state; do not collect container environment or logs.
    template = (
        '{"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
        '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
        '"status":{{json .State.Status}},"restarts":{{.RestartCount}},'
        '"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}}}'
    )
    rows = [
        json.loads(row)
        for row in command(["docker", "inspect", "--format", template, *ids], env).splitlines()
    ]
    if len(rows) != len(SERVICES) or {row["service"] for row in rows} != SERVICES:
        raise ValueError(f"expected exactly the six required services: {rows}")
    if any(
        row["project"] != project
        or row["status"] != "running"
        or row["health"] != "healthy"
        or row["restarts"] > (1 if allow_qdrant_restart and row["service"] == "qdrant" else 0)
        for row in rows
    ):
        raise ValueError(
            f"required service not owned, healthy, running or within restart budget: {rows}"
        )
    return rows


def resources(project: str, env: dict[str, str]) -> dict[str, str]:
    """Docker's exact Compose ownership label is the cleanup boundary."""
    label = f"label=com.docker.compose.project={project}"
    owned = {
        kind: command(["docker", *args, "--filter", label], env)
        for kind, args in {
            "containers": ["ps", "-aq"],
            "volumes": ["volume", "ls", "-q"],
            "networks": ["network", "ls", "-q"],
        }.items()
    }
    owned["images"] = command(
        ["docker", "image", "ls", "-q", "--filter", f"reference={project}_*"], env
    )
    owned["auxiliary_containers"] = command(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            f"label=rag.e2e.run={project.removeprefix('rag-e2e-')}",
        ],
        env,
    )
    return owned


def cleanup(compose: list[str], run_dir: Path, env: dict[str, str]) -> None:
    project = project_name(run_dir.name)
    if run_dir.parent != ROOT / "logs" / "e2e-full" or compose[2:4] != ["-p", project]:
        raise ValueError("refusing cleanup outside the exact run-owned project")
    for container in resources(project, env).get("auxiliary_containers", "").split():
        owner = command(
            ["docker", "inspect", "--format", '{{index .Config.Labels "rag.e2e.run"}}', container],
            env,
        )
        if owner != run_dir.name:
            raise ValueError("refusing cleanup of a foreign fixture container")
        command(["docker", "rm", "-f", container], env)
    command(
        [*compose, "--profile", "full", "down", "--volumes", "--remove-orphans"], env, timeout=180
    )
    for service in ("bot", "ingestion", "bge-m3"):
        name = f"{project}_{service}"
        if command(["docker", "image", "ls", "-q", "--filter", f"reference={name}:latest"], env):
            command(["docker", "image", "rm", name], env)
    if any(resources(project, env).values()):
        raise RuntimeError("run-owned resources remain after teardown")


def write_inputs(run_dir: Path, model_dir: Path, password: str) -> Path:
    (run_dir / "ingestion").mkdir()
    values = {
        "COMPOSE_PROJECT_NAME": project_name(run_dir.name),
        "POSTGRES_PASSWORD": password,
        "REDIS_PASSWORD": password,
        "TELEGRAM_BOT_TOKEN": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        "CEREBRAS_API_KEY": "deterministic-unused-key",
        "BGE_M3_MEMORY_LIMIT": "6G",
        "BGE_M3_ONNX_MODEL_HOST_DIR": model_dir.as_posix(),
        "GDRIVE_SYNC_DIR": (run_dir / "ingestion").as_posix(),
        "QDRANT_COLLECTION": f"e2e_{run_dir.name}_documents",
    }
    env_file = run_dir / "compose.env"
    env_file.write_text(
        "".join(f'{key}="{value}"\n' for key, value in values.items()), encoding="utf-8"
    )
    # !override replaces fixed development ports rather than merging them.
    override = "services:\n"
    for service, port in (("postgres", 5432), ("redis", 6379), ("qdrant", 6333), ("bge-m3", 8000)):
        override += f'  {service}:\n    ports: !override\n      - "127.0.0.1::{port}"\n'
    adapter = json.dumps((ROOT / "tests/e2e_core/bot_runtime.py").as_posix())
    health = (
        "import os,time,httpx,redis; from pathlib import Path; p=Path('/tmp/e2e-polling'); "
        "alive=p.exists() and time.time()-p.stat().st_mtime<15; "
        "c=httpx.Client(timeout=5); q=c.get('http://qdrant:6333/readyz'); "
        "b=c.get('http://bge-m3:8000/health'); c.close(); "
        "r=redis.Redis.from_url(os.environ['REDIS_URL'],socket_timeout=5); ready=r.ping(); r.close(); "
        "exit(0 if alive and ready and q.status_code==200 and b.status_code==200 "
        "and b.json().get('model_loaded') is True else 1)"
    )
    override += f"""  bot:
    command: ["python", "/app/harness_bot.py"]
    volumes:
      - type: bind
        source: {adapter}
        target: /app/harness_bot.py
        read_only: true
    environment:
      PYTHON_DOTENV_DISABLED: "1"
      OTEL_SDK_DISABLED: "true"
    healthcheck:
      test: {json.dumps(["CMD", "python", "-c", health])}
      interval: 5s
      timeout: 20s
      retries: 3
      start_period: 60s
networks:
  default:
    internal: true
"""
    (run_dir / "compose.override.yml").write_text(override, encoding="utf-8")
    return env_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)
    env = clean_environment()
    run_id = args.run_id or uuid.uuid4().hex[:12]
    project = project_name(run_id)
    run_dir = ROOT / "logs" / "e2e-full" / run_id
    if not run_dir.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("run artifacts must stay inside this checkout")
    if run_dir.exists() or any(resources(project, env).values()):
        raise ValueError("run id already exists; choose a fresh run id")
    if command(["git", "status", "--porcelain", "--untracked-files=normal"], env):
        raise ValueError("promotion requires a clean frozen Git candidate")
    sha = command(["git", "rev-parse", "HEAD"], env)
    model_dir = args.model_dir.resolve(strict=True)
    command(
        [
            sys.executable,
            "services/bge-m3-api/verify_artifact.py",
            "--dir",
            str(model_dir),
            "--expected-manifest",
            "services/bge-m3-api/artifact_manifest.json",
        ],
        env,
        timeout=600,
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    password = secrets.token_hex(16)
    env_file = write_inputs(run_dir, model_dir, password)
    compose = [
        "docker",
        "compose",
        "-p",
        project,
        "--project-directory",
        str(ROOT),
        "--env-file",
        str(env_file),
        "-f",
        str(ROOT / "compose.yml"),
        "-f",
        str(ROOT / "compose.dev.yml"),
        "-f",
        str(run_dir / "compose.override.yml"),
    ]
    evidence: dict = {
        "sha": sha,
        "started_at": datetime.now(UTC).isoformat(),
        "command": [
            "python",
            "-m",
            "scripts.e2e.full_stack_gate",
            "--model-dir",
            str(model_dir),
            "--run-id",
            run_id,
        ],
        "run_id": run_id,
        "suites": [],
        "passed": False,
        "cleaned": False,
    }
    try:
        rendered = command([*compose, "--profile", "full", "config", "--services"], env)
        if set(rendered.splitlines()) != SERVICES:
            raise ValueError("rendered topology is not the required six services")
        print(f"Building and starting six services for {project}", flush=True)
        command(
            [
                *compose,
                "--profile",
                "full",
                "up",
                "-d",
                "--build",
                "--wait",
                "--wait-timeout",
                "900",
            ],
            env,
            timeout=2400,
        )
        evidence["before"] = service_snapshot(compose, project, env)
        endpoints = {}
        for service, port in (
            ("postgres", 5432),
            ("redis", 6379),
            ("qdrant", 6333),
            ("bge-m3", 8000),
        ):
            address = command([*compose, "port", service, str(port)], env)
            if not re.fullmatch(r"127\.0\.0\.1:\d+", address):
                raise ValueError(f"expected one loopback ephemeral endpoint for {service}")
            endpoints[service] = address
        test_env = {
            **env,
            "PYTHON_DOTENV_DISABLED": "1",
            "E2E_RUN_ID": run_id,
            "E2E_HARNESS_REQUIRED": "1",
            "E2E_FULL_GATE": "1",
            "E2E_REDIS_STRICT": "1",
            "QDRANT_E2E_STRICT": "1",
            "QDRANT_E2E_RESTART_PROJECT": project,
            "RUN_INTEGRATION_TESTS": "1",
            "QDRANT_URL": f"http://{endpoints['qdrant']}",
            "BGE_M3_URL": f"http://{endpoints['bge-m3']}",
            "REDIS_URL": f"redis://:{password}@{endpoints['redis']}/0",
            "POSTGRES_DSN": f"postgresql://postgres:{password}@{endpoints['postgres']}/realestate",
        }
        for suite in SUITES:
            print(f"Required suite: {suite}", flush=True)
            report = run_dir / (Path(suite).stem + ".xml")
            log = report.with_suffix(".log")
            with log.open("w", encoding="utf-8") as output:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        suite,
                        "-q",
                        "--no-cov",
                        "-m",
                        "e2e and requires_services",
                        f"--junitxml={report}",
                    ],
                    cwd=ROOT,
                    env=test_env,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    timeout=1800,
                    check=False,
                )
            if result.returncode:
                raise RuntimeError(f"required suite failed: {suite} (exit {result.returncode})")
            evidence["suites"].append({"path": suite, "passed": strict_result(report)})
        evidence["after"] = service_snapshot(compose, project, env, allow_qdrant_restart=True)
        evidence["passed"] = True
    except Exception as exc:
        evidence["error"] = str(exc)
    finally:
        try:
            cleanup(compose, run_dir, env)
            evidence["cleaned"] = True
        except Exception as exc:
            evidence["cleanup_error"] = str(exc)
            evidence["passed"] = False
        evidence["finished_at"] = datetime.now(UTC).isoformat()
        # Only generated local credentials exist in this process; nevertheless
        # keep retained failure reports free of passwords and authenticated URLs.
        for report in (*run_dir.glob("*.xml"), *run_dir.glob("*.log")):
            content = report.read_text(encoding="utf-8", errors="replace").replace(
                password, "[redacted]"
            )
            content = re.sub(r"(redis|postgresql)://[^@\s]+@", r"\1://[redacted]@", content)
            report.write_text(content, encoding="utf-8")
        if evidence["cleaned"]:
            env_file.unlink(missing_ok=True)
        serialized = json.dumps(evidence, indent=2).replace(password, "[redacted]")
        serialized = re.sub(r"(redis|postgresql)://[^@\s]+@", r"\1://[redacted]@", serialized)
        (run_dir / "result.json").write_text(serialized, encoding="utf-8")
    print(f"Six-service gate {'PASS' if evidence['passed'] else 'FAIL'}: {run_dir / 'result.json'}")
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
