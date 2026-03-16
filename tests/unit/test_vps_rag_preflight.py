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
        if "./scripts/test_bot_health.sh" in joined:
            return CompletedProcess(cmd, 0, "✓ Qdrant collection exists\n✓ LLM health OK\n", "")
        raise AssertionError(joined)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert run_preflight(host="vps", project_dir="/opt/rag-fresh") == 0
    assert any("./scripts/test_bot_health.sh" in call for call in seen)
    assert any("QDRANT_URL=http://qdrant:6333" in call for call in seen)
    assert any("LLM_BASE_URL=http://litellm:4000" in call for call in seen)


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
        if "./scripts/test_bot_health.sh" in joined:
            return CompletedProcess(cmd, 0, "✓ Qdrant collection exists\n", "")
        raise AssertionError(joined)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert run_preflight(host="vps", project_dir="/opt/rag-fresh") == 1
