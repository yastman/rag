from __future__ import annotations

import json
import subprocess
from subprocess import CompletedProcess


def test_inventory_builds_expected_json(monkeypatch):
    from scripts.vps_runtime_inventory import build_inventory

    calls: list[list[str]] = []

    def fake_run(cmd, capture_output, text, check):
        calls.append(cmd)
        joined = " ".join(cmd)
        if "grep '^COMPOSE_FILE='" in joined:
            return CompletedProcess(cmd, 0, "COMPOSE_FILE=compose.yml:compose.vps.yml\n", "")
        if "docker ps --format" in joined:
            return CompletedProcess(cmd, 0, "vps-bot\tUp 10 minutes\n", "")
        if "docker network ls --format" in joined:
            return CompletedProcess(cmd, 0, "vps_default\n", "")
        if "docker volume ls --format" in joined:
            return CompletedProcess(cmd, 0, "vps_postgres_data\n", "")
        raise AssertionError(joined)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = build_inventory(host="vps", project_dir="/opt/rag-fresh")

    assert result["compose_file"] == "compose.yml:compose.vps.yml"
    assert result["host"] == "vps"
    assert result["project_dir"] == "/opt/rag-fresh"
    assert "vps-bot\tUp 10 minutes" in result["containers"]
    assert "vps_default" in result["networks"]
    assert "vps_postgres_data" in result["volumes"]
    assert len(calls) == 4


def test_main_prints_json(monkeypatch, capsys):
    from scripts import vps_runtime_inventory

    monkeypatch.setattr(
        vps_runtime_inventory,
        "build_inventory",
        lambda host, project_dir: {
            "host": host,
            "project_dir": project_dir,
            "compose_file": "compose.yml:compose.vps.yml",
            "containers": ["vps-bot\tUp"],
            "networks": ["vps_default"],
            "volumes": ["vps_postgres_data"],
        },
    )

    exit_code = vps_runtime_inventory.main(["--host", "vps", "--project-dir", "/opt/rag-fresh"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["host"] == "vps"
    assert payload["compose_file"] == "compose.yml:compose.vps.yml"
