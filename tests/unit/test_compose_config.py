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
DEV_COMPOSE = ROOT / "docker-compose.dev.yml"
VPS_COMPOSE = ROOT / "docker-compose.vps.yml"
MAKEFILE = ROOT / "Makefile"


def _load_compose(path: Path) -> dict:
    with path.open() as f:
        return yaml.full_load(f)


@pytest.fixture(scope="module")
def dev() -> dict:
    return _load_compose(DEV_COMPOSE)


@pytest.fixture(scope="module")
def vps() -> dict:
    return _load_compose(VPS_COMPOSE)


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

    def test_vps_has_x_security_defaults_anchor(self) -> None:
        """VPS compose must define x-security-defaults YAML extension anchor."""
        content = VPS_COMPOSE.read_text()
        assert "x-security-defaults" in content, (
            "docker-compose.vps.yml is missing x-security-defaults extension field"
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
