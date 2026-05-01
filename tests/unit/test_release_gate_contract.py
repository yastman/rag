"""Regression tests for the VPS release gate contract."""

import re
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
    assert "docker compose --compatibility up -d --wait --force-recreate" in workflow
    assert workflow.index("docker compose build") < workflow.index(
        "docker compose --compatibility up -d --wait --force-recreate"
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


def test_manual_deploy_runs_prod_env_preflight_before_build() -> None:
    """Manual deploy must validate the production env contract before docker compose build."""
    script = DEPLOY_SCRIPT.read_text()
    assert "./scripts/validate_prod_env.sh" in script
    assert script.index("./scripts/validate_prod_env.sh") < script.index("docker compose build")


def test_release_gate_script_contains_handoff_contract() -> None:
    """The production env preflight script must enforce the handoff contract."""
    script = (ROOT / "scripts" / "validate_prod_env.sh").read_text()
    assert "HANDOFF_ENABLED" in script
    assert "MANAGERS_GROUP_ID" in script
    assert "docker compose --env-file .env -f compose.yml -f compose.vps.yml config" in script


def test_release_gate_script_requires_langfuse_stateful_secrets() -> None:
    """The production env preflight must reject empty Langfuse stateful credentials."""
    script = (ROOT / "scripts" / "validate_prod_env.sh").read_text()
    assert "CLICKHOUSE_PASSWORD" in script
    assert "MINIO_ROOT_PASSWORD" in script
    assert "is required in production env" in script


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


def test_release_gate_script_requires_all_compose_required_vars() -> None:
    """The production env preflight must check every ?:required variable from compose.yml."""
    script = (ROOT / "scripts" / "validate_prod_env.sh").read_text()
    required_vars = [
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "LITELLM_MASTER_KEY",
        "TELEGRAM_BOT_TOKEN",
        "GDRIVE_SYNC_DIR",
        "NEXTAUTH_SECRET",
        "SALT",
        "ENCRYPTION_KEY",
        "LANGFUSE_REDIS_PASSWORD",
    ]
    for var in required_vars:
        assert var in script, f"{var} missing from validate_prod_env.sh"


def test_release_gate_script_enforces_password_length() -> None:
    """The production env preflight must reject passwords shorter than 12 characters."""
    script = (ROOT / "scripts" / "validate_prod_env.sh").read_text()
    assert "-lt 12" in script or "must be at least 12 characters" in script


def test_release_gate_script_uses_safe_env_parsing() -> None:
    """The production env preflight must not blindly source .env (shell-injection safe)."""
    script = (ROOT / "scripts" / "validate_prod_env.sh").read_text()
    assert ". ./.env" not in script
    assert "source .env" not in script
    assert "Invalid .env line" in script


# ── Healthcheck contract tests (PR #1256 runtime blockers) ──────────────


_PYTHON_SLIM_DOCKERFILES = [
    ROOT / "src" / "api" / "Dockerfile",
    ROOT / "src" / "voice" / "Dockerfile",
]


def _extract_healthcheck_cmd(dockerfile: Path) -> str:
    """Extract the HEALTHCHECK CMD line from a Dockerfile."""
    text = dockerfile.read_text()
    m = re.search(r"HEALTHCHECK.*?\n\s+CMD\s+(.+)", text)
    return m.group(1) if m else ""


def test_python_slim_healthchecks_do_not_use_wget() -> None:
    """Python slim runtime images do not install wget; healthchecks must not rely on it."""
    for df in _PYTHON_SLIM_DOCKERFILES:
        cmd = _extract_healthcheck_cmd(df)
        assert "wget" not in cmd, (
            f"{df.name} HEALTHCHECK uses wget but runtime is python:3.14-slim-bookworm "
            "(no wget installed). Use Python urllib.request instead."
        )
        assert "urllib.request" in cmd or "python -c" in cmd, (
            f"{df.name} HEALTHCHECK should use a Python stdlib HTTP check "
            "since the runtime image is python:3.14-slim-bookworm."
        )


def test_compose_rag_api_voice_agent_healthchecks_do_not_use_wget() -> None:
    """compose.yml healthchecks for rag-api and voice-agent run in python:slim images;
    wget is not available there."""
    compose_text = (ROOT / "compose.yml").read_text()

    # Find rag-api healthcheck section
    rag_api_match = re.search(
        r"rag-api:.*?healthcheck:\s*\n(.*?)(?=\n  \w|\n\w|\Z)",
        compose_text,
        re.DOTALL,
    )
    voice_agent_match = re.search(
        r"voice-agent:.*?healthcheck:\s*\n(.*?)(?=\n  \w|\n\w|\Z)",
        compose_text,
        re.DOTALL,
    )

    if rag_api_match:
        assert "wget" not in rag_api_match.group(1), (
            "rag-api compose healthcheck uses wget; Python urllib.request should be used instead."
        )
    if voice_agent_match:
        assert "wget" not in voice_agent_match.group(1), (
            "voice-agent compose healthcheck uses wget; Python urllib.request should be used instead."
        )


def test_bot_dockerfile_healthcheck_command_is_runtime_available() -> None:
    """Bot HEALTHCHECK must use a command guaranteed in the runtime image OR install it."""
    bot_df = ROOT / "telegram_bot" / "Dockerfile"
    text = bot_df.read_text()

    cmd = _extract_healthcheck_cmd(bot_df)
    has_procps_install = bool(
        re.search(
            r"apt-get install.*procps",
            text,
        )
    )

    if "pgrep" in cmd:
        assert has_procps_install, (
            "telegram_bot/Dockerfile HEALTHCHECK uses pgrep but runtime stage "
            "does not install procps. python:3.14-slim-bookworm does not include pgrep."
        )


def test_bot_k8s_probes_are_runtime_available() -> None:
    """Bot k8s probes must use a command guaranteed in the bot image."""
    k8s_text = (ROOT / "k8s" / "base" / "bot" / "deployment.yaml").read_text()
    bot_df_text = (ROOT / "telegram_bot" / "Dockerfile").read_text()

    has_pgrep = "pgrep" in k8s_text
    has_procps_install = bool(
        re.search(
            r"apt-get install.*procps",
            bot_df_text,
        )
    )

    if has_pgrep:
        assert has_procps_install, (
            "k8s bot probes use pgrep but telegram_bot/Dockerfile does not install procps."
        )


def test_qdrant_healthcheck_does_not_use_wget() -> None:
    """qdrant/qdrant:v1.17.1 does not include wget/curl/busybox;
    the compose healthcheck must use a runtime-available command."""
    compose_text = (ROOT / "compose.yml").read_text()

    qdrant_hc = _extract_compose_service_healthcheck(compose_text, "qdrant")
    assert qdrant_hc is not None, "qdrant healthcheck section not found in compose.yml"
    assert "wget" not in qdrant_hc, (
        "qdrant compose healthcheck uses wget but qdrant/qdrant:v1.17.1 does not "
        "include wget/curl/busybox. Use bash /dev/tcp instead."
    )


def test_promtail_healthcheck_does_not_use_wget() -> None:
    """grafana/promtail:3.6.7 does not include wget/curl/busybox;
    the compose healthcheck must use a runtime-available command."""
    compose_text = (ROOT / "compose.yml").read_text()

    promtail_hc = _extract_compose_service_healthcheck(compose_text, "promtail")
    assert promtail_hc is not None, "promtail healthcheck section not found in compose.yml"
    assert "wget" not in promtail_hc, (
        "promtail compose healthcheck uses wget but grafana/promtail:3.6.7 does not "
        "include wget/curl/busybox. Use bash /dev/tcp instead."
    )


def test_qdrant_healthcheck_uses_bash_dev_tcp() -> None:
    """qdrant/qdrant:v1.17.1 has bash with /dev/tcp support;
    the compose healthcheck must use bash /dev/tcp to hit /readyz."""
    compose_text = (ROOT / "compose.yml").read_text()

    qdrant_hc = _extract_compose_service_healthcheck(compose_text, "qdrant")
    assert qdrant_hc is not None, "qdrant healthcheck section not found in compose.yml"
    assert "bash" in qdrant_hc, (
        "qdrant compose healthcheck must invoke bash explicitly since /bin/sh is dash "
        "and does not support /dev/tcp."
    )
    assert "/dev/tcp" in qdrant_hc, (
        "qdrant compose healthcheck must use bash /dev/tcp since wget/curl/busybox "
        "are not installed in qdrant/qdrant:v1.17.1."
    )
    assert "readyz" in qdrant_hc, (
        "qdrant compose healthcheck must check the canonical readiness endpoint /readyz."
    )


def test_promtail_healthcheck_uses_bash_dev_tcp() -> None:
    """grafana/promtail:3.6.7 has bash with /dev/tcp support;
    the compose healthcheck must use bash /dev/tcp to hit /ready."""
    compose_text = (ROOT / "compose.yml").read_text()

    promtail_hc = _extract_compose_service_healthcheck(compose_text, "promtail")
    assert promtail_hc is not None, "promtail healthcheck section not found in compose.yml"
    assert "bash" in promtail_hc, (
        "promtail compose healthcheck must invoke bash explicitly since /bin/sh is dash "
        "and does not support /dev/tcp."
    )
    assert "/dev/tcp" in promtail_hc, (
        "promtail compose healthcheck must use bash /dev/tcp since wget/curl/busybox "
        "are not installed in grafana/promtail:3.6.7."
    )
    assert "ready" in promtail_hc, (
        "promtail compose healthcheck must check the canonical readiness endpoint /ready."
    )


def _extract_compose_service_healthcheck(compose_text: str, service_name: str) -> str | None:
    """Extract the healthcheck test section for a named compose service.

    Returns the multiline content between the healthcheck key and the next
    compose key that is at the same or shallower indentation, or None if
    the service or its healthcheck section is not found.
    """
    m = re.search(
        rf"  {service_name}:.*?healthcheck:\s*\n(.*?)(?=\n  \w|\n\w|\Z)",
        compose_text,
        re.DOTALL,
    )
    return m.group(1) if m else None
