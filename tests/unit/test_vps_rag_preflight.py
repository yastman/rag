from __future__ import annotations

import subprocess
from subprocess import CompletedProcess


def test_preflight_invokes_remote_health_script(monkeypatch):
    from scripts.vps_rag_preflight import run_preflight

    seen: list[str] = []

    def fake_run(cmd, capture_output, text, check):
        joined = " ".join(cmd)
        seen.append(joined)
        if "docker ps --format" in joined:
            return CompletedProcess(
                cmd,
                0,
                "\n".join(
                    [
                        "vps-postgres\tUp 1 minute",
                        "vps-redis\tUp 1 minute",
                        "vps-qdrant\tUp 1 minute",
                        "vps-bge-m3\tUp 1 minute",
                        "vps-litellm\tUp 1 minute",
                        "vps-bot\tUp 1 minute",
                    ]
                )
                + "\n",
                "",
            )
        if "docker compose exec -T bot" in joined:
            return CompletedProcess(cmd, 0, "✓ Qdrant collection exists\n✓ LLM health OK\n", "")
        raise AssertionError(joined)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert run_preflight(host="vps", project_dir="/opt/rag-fresh") == 0
    assert any("docker compose exec -T bot" in call for call in seen)


def test_preflight_returns_non_zero_when_required_service_missing(monkeypatch):
    from scripts.vps_rag_preflight import run_preflight

    def fake_run(cmd, capture_output, text, check):
        joined = " ".join(cmd)
        if "docker ps --format" in joined:
            return CompletedProcess(
                cmd,
                0,
                "\n".join(
                    [
                        "vps-postgres\tUp 1 minute",
                        "vps-redis\tUp 1 minute",
                        "vps-qdrant\tUp 1 minute",
                    ]
                )
                + "\n",
                "",
            )
        raise AssertionError(joined)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert run_preflight(host="vps", project_dir="/opt/rag-fresh") == 1


def test_preflight_returns_non_zero_when_health_output_incomplete(monkeypatch):
    from scripts.vps_rag_preflight import run_preflight

    def fake_run(cmd, capture_output, text, check):
        joined = " ".join(cmd)
        if "docker ps --format" in joined:
            return CompletedProcess(
                cmd,
                0,
                "\n".join(
                    [
                        "vps-postgres\tUp 1 minute",
                        "vps-redis\tUp 1 minute",
                        "vps-qdrant\tUp 1 minute",
                        "vps-bge-m3\tUp 1 minute",
                        "vps-litellm\tUp 1 minute",
                        "vps-bot\tUp 1 minute",
                    ]
                )
                + "\n",
                "",
            )
        if "docker compose exec -T bot" in joined:
            return CompletedProcess(cmd, 0, "✓ Qdrant collection exists\n", "")
        raise AssertionError(joined)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert run_preflight(host="vps", project_dir="/opt/rag-fresh") == 1


def test_preflight_accepts_compose_generated_container_names(monkeypatch):
    from scripts.vps_rag_preflight import run_preflight

    def fake_run(cmd, capture_output, text, check):
        joined = " ".join(cmd)
        if "docker ps --format" in joined:
            return CompletedProcess(
                cmd,
                0,
                "\n".join(
                    [
                        "vps_postgres_1\tUp 1 minute",
                        "vps_redis_1\tUp 1 minute",
                        "vps_qdrant_1\tUp 1 minute",
                        "vps_bge-m3_1\tUp 1 minute",
                        "vps_litellm_1\tUp 1 minute",
                        "vps_bot_1\tUp 1 minute",
                    ]
                )
                + "\n",
                "",
            )
        if "docker compose exec -T bot" in joined:
            return CompletedProcess(cmd, 0, "✓ Qdrant collection exists\n✓ LLM health OK\n", "")
        raise AssertionError(joined)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert run_preflight(host="vps", project_dir="/opt/rag-fresh") == 0


def test_preflight_runs_health_check_via_docker_compose_exec(monkeypatch):
    from scripts.vps_rag_preflight import run_preflight

    seen: list[str] = []

    def fake_run(cmd, capture_output, text, check):
        joined = " ".join(cmd)
        seen.append(joined)
        if "docker ps --format" in joined:
            return CompletedProcess(
                cmd,
                0,
                "\n".join(
                    [
                        "vps_postgres_1\tUp 1 minute",
                        "vps_redis_1\tUp 1 minute",
                        "vps_qdrant_1\tUp 1 minute",
                        "vps_bge-m3_1\tUp 1 minute",
                        "vps_litellm_1\tUp 1 minute",
                        "vps-bot-1\tUp 1 minute",
                    ]
                )
                + "\n",
                "",
            )
        if "docker compose exec -T bot" in joined:
            return CompletedProcess(cmd, 0, "✓ Qdrant collection exists\n✓ LLM health OK\n", "")
        raise AssertionError(joined)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert run_preflight(host="vps", project_dir="/opt/rag-fresh") == 0
    assert any("docker compose exec -T bot" in call for call in seen)
