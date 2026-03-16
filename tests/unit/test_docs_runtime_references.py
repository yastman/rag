from __future__ import annotations

from pathlib import Path


def test_vps_runbook_uses_current_compose_names():
    runbook = Path("docs/runbooks/vps-rag-ready.md").read_text()
    docker_doc = Path("DOCKER.md").read_text()

    assert "compose.yml:compose.vps.yml" in runbook
    assert "scripts/deploy-vps.sh" in runbook
    assert "make vps-rag-preflight" in runbook
    assert "Telegram" in runbook
    assert "restart/recreate" in runbook.lower()

    assert "docker-compose.vps.yml" not in docker_doc
    assert "docker-compose.dev.yml" not in docker_doc
