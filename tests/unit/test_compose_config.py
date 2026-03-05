"""Tests for Docker Compose configuration correctness.

Covers three issues (M7, M8, M9):
  M7 - bot service must declare depends_on postgres in unified base compose
  M8 - Makefile docker-* profile flags must exist in effective dev compose
  M9 - security defaults must remain intact after dev/vps overrides
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[2]
BASE_COMPOSE = ROOT / "compose.yml"
DEV_OVERRIDE = ROOT / "compose.dev.yml"
VPS_OVERRIDE = ROOT / "compose.vps.yml"
MAKEFILE = ROOT / "Makefile"


def _load_compose(path: Path) -> dict:
    with path.open() as f:
        return yaml.full_load(f)


@pytest.fixture(scope="module")
def base() -> dict:
    return _load_compose(BASE_COMPOSE)


@pytest.fixture(scope="module")
def dev_override() -> dict:
    return _load_compose(DEV_OVERRIDE)


@pytest.fixture(scope="module")
def vps_override() -> dict:
    return _load_compose(VPS_OVERRIDE)


# =============================================================================
# M7 — bot depends_on postgres
# =============================================================================


class TestBotDependsOnPostgres:
    """M7: bot service must wait for postgres before starting."""

    def test_base_bot_depends_on_postgres(self, base: dict) -> None:
        """bot in base compose must declare depends_on: postgres."""
        bot = base["services"]["bot"]
        assert "depends_on" in bot, "bot service has no depends_on"
        depends = bot["depends_on"]
        # depends_on can be a list or a dict (with condition)
        if isinstance(depends, dict):
            assert "postgres" in depends, "bot.depends_on does not include postgres"
        else:
            assert "postgres" in depends, "bot.depends_on does not include postgres"

    def test_base_bot_postgres_dependency_is_healthy(self, base: dict) -> None:
        """bot in base compose must wait for postgres to be healthy."""
        bot = base["services"]["bot"]
        depends = bot["depends_on"]
        assert isinstance(depends, dict), "bot.depends_on must be a dict with conditions"
        assert depends["postgres"]["condition"] == "service_healthy", (
            "bot.depends_on.postgres must use condition: service_healthy"
        )

    def test_dev_override_does_not_replace_bot_depends_on(self, dev_override: dict) -> None:
        """dev override should not drop/replace bot depends_on from base compose."""
        bot = dev_override.get("services", {}).get("bot", {})
        assert "depends_on" not in bot, "compose.dev.yml must not override bot.depends_on"

    def test_vps_override_does_not_replace_bot_depends_on(self, vps_override: dict) -> None:
        """vps override should not drop/replace bot depends_on from base compose."""
        bot = vps_override.get("services", {}).get("bot", {})
        assert "depends_on" not in bot, "compose.vps.yml must not override bot.depends_on"


# =============================================================================
# M8 — Makefile profile drift: docker-ai-up must use an existing profile
# =============================================================================


class TestMakefileAiProfile:
    """M8: all --profile flags in Makefile docker-* targets must exist in dev compose."""

    def _get_effective_profiles(self, base_compose: dict, dev_compose: dict) -> set[str]:
        """Compute effective dev profiles from base + dev override."""
        effective: dict[str, set[str]] = {}

        for svc_name, svc in base_compose.get("services", {}).items():
            if "profiles" in svc:
                effective[svc_name] = {str(p) for p in (svc.get("profiles") or [])}

        for svc_name, svc in dev_compose.get("services", {}).items():
            if "profiles" in svc:
                effective[svc_name] = {str(p) for p in (svc.get("profiles") or [])}

        profiles: set[str] = set()
        for vals in effective.values():
            profiles.update(vals)
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

    def test_docker_up_profiles_exist_in_dev_compose(self, base: dict, dev_override: dict) -> None:
        """Every --profile in Makefile docker-*-up targets must exist in dev compose."""
        compose_profiles = self._get_effective_profiles(base, dev_override)
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

# Services that have security defaults applied in base compose (via <<: *security-defaults)
_SECURITY_SERVICES = ["bge-m3", "user-base", "docling", "litellm", "bot"]


class TestVpsSecurityBaseline:
    """M9: Security baseline must be present in base and preserved by overrides."""

    @pytest.mark.parametrize("svc_name", _SECURITY_SERVICES)
    def test_base_service_has_security_opt(self, base: dict, svc_name: str) -> None:
        """Base service must have security_opt: no-new-privileges."""
        services = base["services"]
        svc = services[svc_name]
        assert "security_opt" in svc, f"base:{svc_name} missing security_opt (no-new-privileges)"
        assert "no-new-privileges:true" in svc["security_opt"], (
            f"base:{svc_name}.security_opt must include 'no-new-privileges:true'"
        )

    @pytest.mark.parametrize("svc_name", _SECURITY_SERVICES)
    def test_base_service_has_cap_drop_all(self, base: dict, svc_name: str) -> None:
        """Base service must drop ALL Linux capabilities."""
        services = base["services"]
        svc = services[svc_name]
        assert "cap_drop" in svc, f"base:{svc_name} missing cap_drop"
        assert "ALL" in svc["cap_drop"], f"base:{svc_name}.cap_drop must include 'ALL'"

    def test_base_has_x_security_defaults_anchor(self) -> None:
        """Base compose must define x-security-defaults YAML extension anchor."""
        content = BASE_COMPOSE.read_text()
        assert "x-security-defaults" in content, (
            "compose.yml is missing x-security-defaults extension field"
        )

    @pytest.mark.parametrize("svc_name", ["bge-m3", "user-base", "bot"])
    def test_base_service_has_read_only(self, base: dict, svc_name: str) -> None:
        """Security-hardened services in base must be read_only."""
        services = base["services"]
        svc = services[svc_name]
        assert svc.get("read_only") is True, f"base:{svc_name} must have read_only: true"

    @pytest.mark.parametrize("svc_name", ["bge-m3", "user-base", "bot"])
    def test_base_service_has_tmpfs(self, base: dict, svc_name: str) -> None:
        """Security-hardened services must have tmpfs /tmp with read_only."""
        services = base["services"]
        svc = services[svc_name]
        tmpfs = svc.get("tmpfs", [])
        assert "/tmp" in tmpfs, (
            f"base:{svc_name} missing tmpfs: [/tmp] (needed with read_only: true)"
        )

    @pytest.mark.parametrize("svc_name", _SECURITY_SERVICES)
    def test_vps_override_does_not_relax_security_opt(
        self, vps_override: dict, svc_name: str
    ) -> None:
        """compose.vps.yml must not remove/relax security_opt if overridden."""
        svc = vps_override.get("services", {}).get(svc_name, {})
        if "security_opt" not in svc:
            return
        assert "no-new-privileges:true" in svc["security_opt"]

    @pytest.mark.parametrize("svc_name", _SECURITY_SERVICES)
    def test_vps_override_does_not_relax_cap_drop(self, vps_override: dict, svc_name: str) -> None:
        """compose.vps.yml must not remove cap_drop if overridden."""
        svc = vps_override.get("services", {}).get(svc_name, {})
        if "cap_drop" not in svc:
            return
        assert "ALL" in svc["cap_drop"]

    @pytest.mark.parametrize("svc_name", ["bge-m3", "user-base", "bot"])
    def test_vps_override_does_not_disable_read_only(
        self, vps_override: dict, svc_name: str
    ) -> None:
        """compose.vps.yml must not disable read_only for hardened services."""
        svc = vps_override.get("services", {}).get(svc_name, {})
        if "read_only" not in svc:
            return
        assert svc["read_only"] is True

    @pytest.mark.parametrize("svc_name", ["bge-m3", "user-base", "bot"])
    def test_vps_override_does_not_remove_tmpfs(self, vps_override: dict, svc_name: str) -> None:
        """compose.vps.yml must not remove /tmp tmpfs for hardened services."""
        svc = vps_override.get("services", {}).get(svc_name, {})
        if "tmpfs" not in svc:
            return
        assert "/tmp" in (svc.get("tmpfs") or [])

    @pytest.mark.parametrize("svc_name", _SECURITY_SERVICES)
    def test_dev_override_does_not_relax_security_opt(
        self, dev_override: dict, svc_name: str
    ) -> None:
        """compose.dev.yml must not remove/relax security_opt if overridden."""
        svc = dev_override.get("services", {}).get(svc_name, {})
        if "security_opt" not in svc:
            return
        assert "no-new-privileges:true" in svc["security_opt"]

    @pytest.mark.parametrize("svc_name", _SECURITY_SERVICES)
    def test_dev_override_does_not_relax_cap_drop(self, dev_override: dict, svc_name: str) -> None:
        """compose.dev.yml must not remove cap_drop if overridden."""
        svc = dev_override.get("services", {}).get(svc_name, {})
        if "cap_drop" not in svc:
            return
        assert "ALL" in svc["cap_drop"]

    @pytest.mark.parametrize("svc_name", ["bge-m3", "user-base", "bot"])
    def test_dev_override_does_not_disable_read_only(
        self, dev_override: dict, svc_name: str
    ) -> None:
        """compose.dev.yml must not disable read_only for hardened services."""
        svc = dev_override.get("services", {}).get(svc_name, {})
        if "read_only" not in svc:
            return
        assert svc["read_only"] is True

    @pytest.mark.parametrize("svc_name", ["bge-m3", "user-base", "bot"])
    def test_dev_override_does_not_remove_tmpfs(self, dev_override: dict, svc_name: str) -> None:
        """compose.dev.yml must not remove /tmp tmpfs for hardened services."""
        svc = dev_override.get("services", {}).get(svc_name, {})
        if "tmpfs" not in svc:
            return
        assert "/tmp" in (svc.get("tmpfs") or [])

    def test_vps_override_exists(self, vps_override: dict) -> None:
        assert "services" in vps_override

    def test_dev_override_exists(self, dev_override: dict) -> None:
        assert "services" in dev_override

    def test_security_services_exist_in_base(self, base: dict) -> None:
        base_services = base.get("services", {})
        missing = [svc for svc in _SECURITY_SERVICES if svc not in base_services]
        assert not missing, (
            f"Expected security-hardened services are missing in compose.yml: {missing}"
        )
