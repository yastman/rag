"""Tests for Docker Compose configuration correctness.

Covers three issues (M7, M8, M9):
  M7 - bot/postgres startup topology (evolved by #3241: PostgreSQL is an
       opt-in profile service, the bot no longer waits for it and degrades
       gracefully — bookmarks capability disabled — without it)
  M8 - Makefile docker-ai-up target must use a profile that exists in dev compose
  M9 - base compose must define the x-security-defaults anchor overlays reuse
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


# =============================================================================
# M7 — bot/postgres startup topology (#3241: PostgreSQL is opt-in)
# =============================================================================


class TestBotDependsOnPostgres:
    """M7 (#3241): the core demo topology starts without PostgreSQL.

    PostgreSQL moved behind the ``postgres``/``full`` profiles and the bot no
    longer declares a depends_on on it: the preflight treats postgres as
    OPTIONAL and the bookmarks capability stays disabled until it is reachable.
    """

    def test_dev_bot_does_not_depend_on_postgres(self, dev: dict) -> None:
        """bot in dev compose must not gate its startup on postgres."""
        bot = dev["services"]["bot"]
        depends = bot.get("depends_on") or {}
        assert "postgres" not in depends, (
            "bot.depends_on must not include postgres (#3241): the core demo "
            "topology starts without PostgreSQL and the bot degrades gracefully"
        )

    def test_dev_bot_still_depends_on_core_services_healthy(self, dev: dict) -> None:
        """bot must keep waiting for the core CRITICAL deps to be healthy."""
        bot = dev["services"]["bot"]
        depends = bot["depends_on"]
        assert isinstance(depends, dict), "bot.depends_on must be a dict with conditions"
        for svc in ("redis", "qdrant", "bge-m3"):
            assert depends.get(svc, {}).get("condition") == "service_healthy", (
                f"bot.depends_on.{svc} must use condition: service_healthy"
            )

    def test_dev_postgres_is_profile_gated(self, dev: dict) -> None:
        """postgres must be an opt-in profile service (#3241)."""
        postgres = dev["services"]["postgres"]
        profiles = set(postgres.get("profiles") or [])
        assert {"postgres", "full"} <= profiles, (
            f"postgres must be gated behind the 'postgres' and 'full' profiles, got {profiles!r}"
        )

    @pytest.mark.parametrize("svc_name", ["redis", "qdrant", "bge-m3"])
    def test_dev_core_services_are_unprofiled(self, dev: dict, svc_name: str) -> None:
        """The core demo topology services must start by default."""
        assert not dev["services"][svc_name].get("profiles"), (
            f"{svc_name} belongs to the core demo topology and must be unprofiled"
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
# M9 — base compose security defaults (anchor reused by overlays)
# =============================================================================


class TestBaseComposeSecurityDefaults:
    """M9: base compose defines the shared security baseline overlays reuse."""

    def test_base_has_x_security_defaults_anchor(self) -> None:
        """Base compose must define x-security-defaults YAML extension anchor."""
        content = BASE_COMPOSE.read_text()
        assert "x-security-defaults" in content, (
            "compose.yml is missing x-security-defaults extension field"
        )
