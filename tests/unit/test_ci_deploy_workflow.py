from pathlib import Path

import yaml


def test_deploy_timeout_increased() -> None:
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    deploy = next(j for j in data["jobs"].values() if j.get("name") == "Deploy to VPS")
    assert deploy.get("timeout-minutes", 10) > 10


def test_deploy_no_fixed_sleep() -> None:
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "sleep 20" not in text
    # Disallow blind fixed sleeps anywhere in the deploy job script
    assert "sleep " not in text


def test_deploy_uses_compose_wait_or_health_driven() -> None:
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "--wait" in text or "health" in text.lower()


def test_deploy_exports_buildkit() -> None:
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "DOCKER_BUILDKIT=1" in text


def test_deploy_dirty_tree_guard_before_reset() -> None:
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    # Must guard against dirty tree before destructive reset
    assert "git status --porcelain" in text
    reset_idx = text.find("git reset --hard")
    guard_idx = text.find("git status --porcelain")
    assert guard_idx < reset_idx, "dirty-tree guard must appear before git reset --hard"
