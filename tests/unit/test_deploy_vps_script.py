from __future__ import annotations

from pathlib import Path


def test_deploy_script_has_verify_and_core_only_flags():
    content = Path("scripts/deploy-vps.sh").read_text()

    assert "--core-only" in content
    assert "--verify" in content
    assert "docker compose config" in content
    assert "compose.yml:compose.vps.yml" in content
    assert "vps_rag_preflight.py" in content
