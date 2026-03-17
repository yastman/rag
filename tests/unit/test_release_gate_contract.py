"""Regression tests for the VPS release gate contract."""

from pathlib import Path


ROOT = Path(__file__).parents[2]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy-vps.sh"
RELEASE_SMOKE_SCRIPT = ROOT / "scripts" / "test_release_health_vps.sh"


def test_release_smoke_script_does_not_allow_profile_mode() -> None:
    """Release smoke must not keep the profile-aware downgrade path."""
    script = RELEASE_SMOKE_SCRIPT.read_text()
    assert "auto|true|false" in script
    assert "profile" not in script, (
        "scripts/test_release_health_vps.sh still supports 'profile', "
        "which lets release-critical callers skip strict mini-app parity."
    )


def test_ci_deploy_uses_strict_mini_app_release_smoke() -> None:
    """CI deploy must fail when mini-app parity is broken."""
    workflow = CI_WORKFLOW.read_text()
    assert "REQUIRE_MINI_APP_ENDPOINT=true ./scripts/test_release_health_vps.sh" in workflow


def test_manual_deploy_uses_strict_mini_app_release_smoke() -> None:
    """Manual VPS deploy must use the same strict release contract as CI."""
    script = DEPLOY_SCRIPT.read_text()
    assert "REQUIRE_MINI_APP_ENDPOINT=true ./scripts/test_release_health_vps.sh" in script
