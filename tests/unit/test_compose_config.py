"""Tests for Docker Compose configuration correctness.

Covers three issues (M7, M8, M9):
  M7 - bot service must declare depends_on postgres in dev and vps compose
  M8 - Makefile docker-ai-up target must use a profile that exists in dev compose
  M9 - VPS compose must have the same security baseline as dev compose
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[2]
BASE_COMPOSE = ROOT / "compose.yml"
DEV_OVERRIDE = ROOT / "compose.dev.yml"
MAKEFILE = ROOT / "Makefile"
MINI_APP_FRONTEND_DOCKERFILE = ROOT / "mini_app/frontend/Dockerfile"


def _load_compose(path: Path) -> dict:
    with path.open() as f:
        return yaml.full_load(f)


def _load_merged_dev() -> dict:
    """Load base + dev override (profiles/ports split across files)."""
    base = _load_compose(BASE_COMPOSE)
    override = _load_compose(DEV_OVERRIDE)
    for svc_name, svc_override in override.get("services", {}).items():
        if svc_name in base["services"]:
            base["services"][svc_name].update(svc_override)
        else:
            base["services"][svc_name] = svc_override
    return base


@pytest.fixture(scope="module")
def dev() -> dict:
    return _load_merged_dev()


@pytest.fixture(scope="module")
def vps() -> dict:
    return _load_compose(BASE_COMPOSE)


# =============================================================================
# M7 — bot depends_on postgres
# =============================================================================


class TestBotDependsOnPostgres:
    """M7: bot service must wait for postgres before starting."""

    def test_dev_bot_depends_on_postgres(self, dev: dict) -> None:
        """bot in dev compose must declare depends_on: postgres."""
        bot = dev["services"]["bot"]
        assert "depends_on" in bot, "bot service has no depends_on"
        depends = bot["depends_on"]
        # depends_on can be a list or a dict (with condition)
        if isinstance(depends, dict):
            assert "postgres" in depends, "bot.depends_on in dev compose does not include postgres"
        else:
            assert "postgres" in depends, "bot.depends_on in dev compose does not include postgres"

    def test_dev_bot_postgres_dependency_is_healthy(self, dev: dict) -> None:
        """bot in dev compose must wait for postgres to be healthy."""
        bot = dev["services"]["bot"]
        depends = bot["depends_on"]
        assert isinstance(depends, dict), "bot.depends_on must be a dict with conditions"
        assert depends["postgres"]["condition"] == "service_healthy", (
            "bot.depends_on.postgres must use condition: service_healthy"
        )

    def test_vps_bot_depends_on_postgres(self, vps: dict) -> None:
        """bot in vps compose must declare depends_on: postgres."""
        bot = vps["services"]["bot"]
        assert "depends_on" in bot, "bot service has no depends_on in vps compose"
        depends = bot["depends_on"]
        if isinstance(depends, dict):
            assert "postgres" in depends, "bot.depends_on in vps compose does not include postgres"
        else:
            assert "postgres" in depends, "bot.depends_on in vps compose does not include postgres"

    def test_vps_bot_postgres_dependency_is_healthy(self, vps: dict) -> None:
        """bot in vps compose must wait for postgres to be healthy."""
        bot = vps["services"]["bot"]
        depends = bot["depends_on"]
        assert isinstance(depends, dict), "bot.depends_on must be a dict with conditions in vps"
        assert depends["postgres"]["condition"] == "service_healthy", (
            "bot.depends_on.postgres must use condition: service_healthy in vps"
        )


# =============================================================================
# M8 — Makefile profile drift: docker-ai-up must use an existing profile
# =============================================================================


class TestMakefileAiProfile:
    """M8: all --profile flags in Makefile docker-* targets must exist in dev compose."""

    def _get_all_profiles(self, compose: dict) -> set[str]:
        profiles: set[str] = set()
        for svc in compose.get("services", {}).values():
            for p in svc.get("profiles", []) or []:
                profiles.add(str(p))
        return profiles

    def _get_docker_up_profiles(self) -> set[str]:
        """Extract --profile values from Makefile docker-*-up target recipes only."""
        content = MAKEFILE.read_text()
        # Extract only the docker-*-up section (from .PHONY declaration to docker-up alias)
        section = re.search(
            r"(docker-core-up:.*?docker-up:.*?##.*?\n)",
            content,
            re.DOTALL,
        )
        if not section:
            return set()
        return set(re.findall(r"--profile\s+(\S+)", section.group(1)))

    def test_docker_up_profiles_exist_in_dev_compose(self, dev: dict) -> None:
        """Every --profile in Makefile docker-*-up targets must exist in dev compose."""
        compose_profiles = self._get_all_profiles(dev)
        makefile_profiles = self._get_docker_up_profiles()
        unknown = makefile_profiles - compose_profiles
        assert not unknown, (
            f"Makefile docker-*-up targets reference profile(s) not in compose: "
            f"{sorted(unknown)}. Defined profiles: {sorted(compose_profiles)}"
        )

    def test_docker_ai_up_does_not_use_undefined_ai_profile(self) -> None:
        """docker-ai-up must not use '--profile ai' since 'ai' is not a compose profile."""
        content = MAKEFILE.read_text()
        match = re.search(r"docker-ai-up:.*?(?=\n[a-zA-Z])", content, re.DOTALL)
        assert match, "docker-ai-up target not found in Makefile"
        recipe = match.group(0)
        assert "--profile ai" not in recipe, (
            "docker-ai-up still uses '--profile ai' which is not defined in compose"
        )


# =============================================================================
# M9 — VPS security baseline parity with dev compose
# =============================================================================

# Services that have security defaults applied in dev compose (via <<: *security-defaults)
_SECURITY_SERVICES = ["bge-m3", "user-base", "docling", "litellm", "bot"]

# Services that exist in both dev AND vps compose
_VPS_SECURITY_SERVICES = [s for s in _SECURITY_SERVICES if s != "ingestion"]


class TestVpsSecurityBaseline:
    """M9: VPS compose services must match the security baseline from dev compose."""

    @pytest.mark.parametrize("svc_name", _VPS_SECURITY_SERVICES)
    def test_vps_service_has_security_opt(self, vps: dict, svc_name: str) -> None:
        """VPS service must have security_opt: no-new-privileges."""
        services = vps["services"]
        if svc_name not in services:
            pytest.skip(f"Service {svc_name} not present in vps compose")
        svc = services[svc_name]
        assert "security_opt" in svc, f"vps:{svc_name} missing security_opt (no-new-privileges)"
        assert "no-new-privileges:true" in svc["security_opt"], (
            f"vps:{svc_name}.security_opt must include 'no-new-privileges:true'"
        )

    @pytest.mark.parametrize("svc_name", _VPS_SECURITY_SERVICES)
    def test_vps_service_has_cap_drop_all(self, vps: dict, svc_name: str) -> None:
        """VPS service must drop ALL Linux capabilities."""
        services = vps["services"]
        if svc_name not in services:
            pytest.skip(f"Service {svc_name} not present in vps compose")
        svc = services[svc_name]
        assert "cap_drop" in svc, f"vps:{svc_name} missing cap_drop"
        assert "ALL" in svc["cap_drop"], f"vps:{svc_name}.cap_drop must include 'ALL'"

    def test_base_has_x_security_defaults_anchor(self) -> None:
        """Base compose must define x-security-defaults YAML extension anchor."""
        content = BASE_COMPOSE.read_text()
        assert "x-security-defaults" in content, (
            "compose.yml is missing x-security-defaults extension field"
        )

    @pytest.mark.parametrize("svc_name", ["bge-m3", "user-base", "bot"])
    def test_vps_service_has_read_only(self, vps: dict, svc_name: str) -> None:
        """VPS services that are read-only in dev must also be read-only in vps."""
        services = vps["services"]
        if svc_name not in services:
            pytest.skip(f"Service {svc_name} not present in vps compose")
        svc = services[svc_name]
        assert svc.get("read_only") is True, (
            f"vps:{svc_name} must have read_only: true (matching dev compose)"
        )

    @pytest.mark.parametrize("svc_name", ["bge-m3", "user-base", "bot"])
    def test_vps_service_has_tmpfs(self, vps: dict, svc_name: str) -> None:
        """VPS services must have tmpfs /tmp (required when read_only: true)."""
        services = vps["services"]
        if svc_name not in services:
            pytest.skip(f"Service {svc_name} not present in vps compose")
        svc = services[svc_name]
        tmpfs = svc.get("tmpfs", [])
        assert "/tmp" in tmpfs, (
            f"vps:{svc_name} missing tmpfs: [/tmp] (needed with read_only: true)"
        )


def _duration_to_seconds(raw: str) -> int:
    match = re.fullmatch(r"(\d+)([smh])", str(raw).strip())
    assert match, f"Unsupported duration format: {raw!r}"
    value = int(match.group(1))
    unit = match.group(2)
    return value if unit == "s" else value * 60 if unit == "m" else value * 3600


class TestModelServiceHealthcheckGrace:
    """Model services need enough healthcheck grace period for cold starts."""

    @pytest.mark.parametrize("svc_name", ["bge-m3", "user-base"])
    def test_model_service_start_period_is_sufficient(self, vps: dict, svc_name: str) -> None:
        svc = vps["services"][svc_name]
        start_period = svc.get("healthcheck", {}).get("start_period")
        assert start_period, f"{svc_name}.healthcheck.start_period is required"
        assert _duration_to_seconds(start_period) >= 300, (
            f"{svc_name}.healthcheck.start_period must be >=300s for cold model downloads; "
            f"got {start_period!r}"
        )


class TestPostgresShutdownSafety:
    """Stateful Postgres must get enough time to exit cleanly before Docker kills it."""

    def test_postgres_has_explicit_stop_grace_period(self, vps: dict) -> None:
        postgres = vps["services"]["postgres"]
        stop_grace_period = postgres.get("stop_grace_period")
        assert stop_grace_period, "postgres.stop_grace_period is required for graceful WAL flush"
        assert _duration_to_seconds(stop_grace_period) >= 30, (
            "postgres.stop_grace_period must be >=30s to avoid forced kills during shutdown; "
            f"got {stop_grace_period!r}"
        )


class TestMiniAppVpsParity:
    """Mini app must be part of the default VPS runtime stack."""

    @pytest.mark.parametrize("svc_name", ["mini-app-api", "mini-app-frontend"])
    def test_vps_mini_app_service_is_not_profile_gated(self, vps: dict, svc_name: str) -> None:
        """Default VPS compose up must include both mini-app services."""
        svc = vps["services"][svc_name]
        assert not svc.get("profiles"), (
            f"{svc_name} must not declare optional profiles in compose.yml; "
            "default VPS compose up skips profiled services"
        )


class TestMiniAppFrontendHealthcheck:
    """Mini app frontend healthcheck must match nginx's IPv4-only loopback binding."""

    _EXPECTED_PROBE = "wget -qO- http://127.0.0.1/health || exit 1"

    def test_compose_uses_ipv4_loopback_healthcheck(self, vps: dict) -> None:
        svc = vps["services"]["mini-app-frontend"]
        assert svc["healthcheck"]["test"] == ["CMD-SHELL", self._EXPECTED_PROBE]

    def test_frontend_dockerfile_uses_same_ipv4_loopback_healthcheck(self) -> None:
        content = MINI_APP_FRONTEND_DOCKERFILE.read_text()
        assert self._EXPECTED_PROBE in content


class TestHandoffComposeContract:
    """Bot compose env must expose the production handoff contract."""

    def test_vps_bot_compose_includes_handoff_flag(self, vps: dict) -> None:
        bot_env = vps["services"]["bot"]["environment"]
        assert "HANDOFF_ENABLED" in bot_env
        assert bot_env["HANDOFF_ENABLED"] == "${HANDOFF_ENABLED:-false}"

    def test_vps_bot_compose_includes_handoff_contract_env(self, vps: dict) -> None:
        bot_env = vps["services"]["bot"]["environment"]
        assert "HANDOFF_ENABLED" in bot_env
        assert "MANAGERS_GROUP_ID" in bot_env
