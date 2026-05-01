from pathlib import Path


def test_deploy_vps_no_hardcoded_connection_defaults() -> None:
    text = Path("scripts/deploy-vps.sh").read_text(encoding="utf-8")
    assert 'VPS_HOST="REDACTED_VPS_IP"' not in text
    assert 'VPS_PORT="1654"' not in text
    assert 'VPS_USER="admin"' not in text
    assert 'VPS_KEY="$HOME/.ssh/vps_access_key"' not in text


def test_deploy_vps_env_defaults_with_clear_failure() -> None:
    text = Path("scripts/deploy-vps.sh").read_text(encoding="utf-8")
    # Connection params should come from environment with clear failure if missing
    assert "VPS_HOST" in text
    assert "VPS_PORT" in text
    assert "VPS_USER" in text
    assert "VPS_KEY" in text
    assert ":-" in text or "error" in text.lower()


def test_deploy_vps_no_strict_host_key_checking_no() -> None:
    text = Path("scripts/deploy-vps.sh").read_text(encoding="utf-8")
    assert "StrictHostKeyChecking=no" not in text


def test_deploy_vps_strict_host_key_checking_configurable() -> None:
    text = Path("scripts/deploy-vps.sh").read_text(encoding="utf-8")
    assert "StrictHostKeyChecking" in text


def test_deploy_vps_fails_when_required_env_missing() -> None:
    text = Path("scripts/deploy-vps.sh").read_text(encoding="utf-8")
    # Should validate required env vars early and fail clearly
    assert "VPS_HOST" in text
    assert "error" in text.lower() or "exit" in text.lower()
