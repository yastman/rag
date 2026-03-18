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


def test_ci_deploy_runs_prod_env_preflight_before_build() -> None:
    """CI deploy must validate the production env contract before docker compose build."""
    workflow = CI_WORKFLOW.read_text()
    assert "./scripts/validate_prod_env.sh" in workflow
    assert workflow.index("./scripts/validate_prod_env.sh") < workflow.index("docker compose build")


def test_ci_deploy_force_recreates_services_after_build() -> None:
    """CI deploy must recreate services so rebuilt images actually reach runtime."""
    workflow = CI_WORKFLOW.read_text()
    assert "docker compose --compatibility up -d --force-recreate" in workflow
    assert workflow.index("docker compose build") < workflow.index(
        "docker compose --compatibility up -d --force-recreate"
    )


def test_manual_deploy_uses_strict_mini_app_release_smoke() -> None:
    """Manual VPS deploy must use the same strict release contract as CI."""
    script = DEPLOY_SCRIPT.read_text()
    assert "REQUIRE_MINI_APP_ENDPOINT=true ./scripts/test_release_health_vps.sh" in script


def test_manual_deploy_force_recreates_services_after_build() -> None:
    """Manual deploy must recreate services so rebuilt images replace stale containers."""
    script = DEPLOY_SCRIPT.read_text()
    assert "docker compose --compatibility up -d --force-recreate" in script
    assert script.index("docker compose build") < script.index(
        "docker compose --compatibility up -d --force-recreate"
    )


def test_release_gate_script_contains_handoff_contract() -> None:
    """The production env preflight script must enforce the handoff contract."""
    script = (ROOT / "scripts" / "validate_prod_env.sh").read_text()
    assert "HANDOFF_ENABLED" in script
    assert "MANAGERS_GROUP_ID" in script
    assert "docker compose --env-file .env -f compose.yml -f compose.vps.yml config" in script


def test_release_smoke_checks_handoff_contract_when_enabled() -> None:
    """Release smoke must validate handoff env presence when the feature is enabled."""
    script = RELEASE_SMOKE_SCRIPT.read_text()
    assert "HANDOFF_ENABLED={os.getenv('HANDOFF_ENABLED', 'false')}" in script
    assert "handoff_enabled_runtime" in script
    assert "MANAGERS_GROUP_ID" in script


def test_release_smoke_logs_when_handoff_smoke_is_skipped() -> None:
    """Release smoke must log when the handoff-specific branch is skipped."""
    script = RELEASE_SMOKE_SCRIPT.read_text()
    assert "handoff smoke skipped" in script


def test_release_smoke_reads_handoff_gate_from_bot_runtime_env() -> None:
    """Release smoke must key off container runtime env, not the host shell env."""
    script = RELEASE_SMOKE_SCRIPT.read_text()
    assert "docker compose exec -T bot python - <<'PY'" in script
    assert 'HANDOFF_ENABLED="${HANDOFF_ENABLED:-false}"' not in script
