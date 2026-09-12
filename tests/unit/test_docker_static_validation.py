"""Native Docker Compose / Dockerfile static validation (audit A07/A09, #3424).

Single owner of the Compose/Docker contract surface. Every Compose assertion
runs against the configuration the Compose **engine** renders
(``docker compose config``) — never against a handwritten YAML merge, a
host-port string parser, or a Dockerfile COPY scanner. The one module-scoped
``rendered_full`` fixture renders the base+dev project with the ``full``
profile once per module; the ``rendered_core_minimal`` fixture pins the
unprofiled minimal core mode (#3451 — the deleted ``compose.core.yml``
projection renders from base+dev now); scenario tests render their own
profile explicitly through the same helper. Build correctness is proven by
the real build engine: a missing COPY source or a nonexistent build context
must fail an actual ``docker compose build`` (the native replacement for the
#1993 parser contract), and an unhealthy service makes ``up --wait`` exit
nonzero (#3361 — pinned by the Makefile wait contracts in
``tests/unit/test_local_compose_contract.py`` and DOCKER.md).

Dockerfile policy (#1814): Langfuse-importing app images pin Python
``LANGFUSE_PY_FLOOR`` with an immutable ``@sha256`` digest on every external
``FROM`` line; the registry images stay digest-pinned in compose too.

Docker availability is checked at runtime; tests skip gracefully when absent
(#2009). The graceful-skip helper is deliberately not meta-tested (#3424).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
import yaml
from aiogram.utils.token import validate_token


DOCKERFILES = [
    "Dockerfile.ingestion",
    "telegram_bot/Dockerfile",
    "services/bge-m3-api/Dockerfile",
]

# Images that import telegram_bot.observability (Langfuse SDK) must stay on
# LANGFUSE_PY_FLOOR: Langfuse 4.x imports pydantic.v1 compatibility code that
# crashes under Python 3.14 (#1307, #1381).
LANGFUSE_RUNTIME_DOCKERFILES = [
    "telegram_bot/Dockerfile",
    "Dockerfile.ingestion",
]
LANGFUSE_PY_FLOOR = "3.13"
LANGFUSE_PY_FORBIDDEN = ("3.14",)

_DIGEST_RE = re.compile(r"@sha256:[a-f0-9]{64}")

COMPOSE_CI_ENV = Path("tests/fixtures/compose.ci.env")
COMPOSE_FILE = Path("compose.yml")
ENV_EXAMPLE = Path(".env.example")

FULL_PROFILE_SERVICES = {"postgres", "redis", "qdrant", "bge-m3", "bot", "ingestion"}
ALWAYS_ON_SERVICES = {"redis", "qdrant", "bge-m3"}
EXPECTED_DEV_HOST_PORTS = {"5432", "6333", "6334", "6379", "8000"}


def _docker_available() -> bool:
    """Return True only when both ``docker`` and the Compose v2 plugin are usable.

    On hosts that ship the engine without the Compose plugin
    (lightweight CI sandboxes, default Amazon Linux 2023, etc.)
    ``shutil.which("docker")`` returns truthy but ``docker compose ...``
    exits 125 ("looking up compose provider failed"). Probing the plugin
    here lets the static-validation tests skip gracefully instead of
    asserting on the plugin error message. Tracked under #2009.
    """
    if shutil.which("docker") is None:
        return False
    try:
        probe = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def _run_docker_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    if not _docker_available():
        pytest.skip("Docker / Compose plugin not available")
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        pytest.skip("Docker / Compose plugin not available")
    # Defensive: if the Compose plugin disappeared between the probe and
    # this call (or the host emits the same "compose provider failed"
    # error from a different path), downgrade to skip so we never flip a
    # missing-runtime condition into a hard FAIL.
    if result.returncode == 125 and "compose provider failed" in (result.stderr or ""):
        pytest.skip("Docker Compose plugin missing at runtime")
    return result


def _render_compose_config(
    *compose_args: str,
    config_args: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    """Render the merged base+dev config (the engine is the merge authority).

    ``compose_args`` are top-level Compose flags (e.g. ``--profile full``);
    ``config_args`` are flags of the ``config`` command itself
    (e.g. ``--format json``, ``--quiet``).
    """
    return _run_docker_command(
        [
            "docker",
            "compose",
            "--env-file",
            str(COMPOSE_CI_ENV),
            "-f",
            "compose.yml",
            "-f",
            "compose.dev.yml",
            *compose_args,
            "config",
            *config_args,
        ],
    )


def _render_compose_json(*compose_args: str) -> dict:
    """Render the merged base+dev config as a parsed JSON dict."""
    result = _render_compose_config(*compose_args, config_args=("--format", "json"))
    assert result.returncode == 0, f"Compose config rendering failed:\n{result.stderr}"
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def rendered_full() -> dict:
    """The native base+dev render with the ``full`` profile, parsed once (#3424)."""
    return _render_compose_json("--profile", "full")


def _published_ports(rendered: dict) -> list[tuple[str, str, str]]:
    """Return ``(service, host_ip, published)`` for every rendered port."""
    entries: list[tuple[str, str, str]] = []
    for svc_name, svc in rendered["services"].items():
        for port in svc.get("ports") or []:
            entries.append((svc_name, str(port.get("host_ip")), str(port.get("published"))))
    return entries


# =============================================================================
# Rendered topology: services, profiles, ports (#3424 — engine-rendered)
# =============================================================================


def test_compose_full_profile_renders_exactly_six_healthy_capable_services(
    rendered_full: dict,
) -> None:
    """Full-profile success means exactly six services, each with a healthcheck.

    #3361: "Success means exactly six expected services are healthy" — the
    rendered full profile must contain exactly postgres, redis, qdrant,
    bge-m3, bot, ingestion, and every one of them must declare a healthcheck
    so `up --wait` gates on real health rather than process presence.
    """
    services = rendered_full["services"]
    assert set(services) == FULL_PROFILE_SERVICES, (
        f"full profile must render exactly {sorted(FULL_PROFILE_SERVICES)}, "
        f"got {sorted(services)} (#3361)"
    )
    missing_healthcheck = sorted(
        name for name, svc in services.items() if not (svc.get("healthcheck") or {}).get("test")
    )
    assert not missing_healthcheck, (
        f"every full-profile service must declare a healthcheck so `up --wait` "
        f"gates on real health; missing: {missing_healthcheck} (#3361)"
    )


def test_rendered_profile_gating_matches_documented_groups(rendered_full: dict) -> None:
    """Profile gates must match the documented groups; core services stay unprofiled.

    postgres is an opt-in domain DB behind ``postgres``/``full`` (#3241), the
    bot behind ``bot``/``full``, ingestion behind ``ingest``/``full``, while
    redis/qdrant/bge-m3 form the always-on core demo topology (#555).
    """
    services = rendered_full["services"]
    expected_profiles = {
        "postgres": {"postgres", "full"},
        "bot": {"bot", "full"},
        "ingestion": {"ingest", "full"},
    }
    for svc_name, required in expected_profiles.items():
        rendered_profiles = set(services[svc_name].get("profiles") or [])
        assert required <= rendered_profiles, (
            f"{svc_name} must be gated behind {sorted(required)}, got {sorted(rendered_profiles)}"
        )
    unprofiled = [name for name in ALWAYS_ON_SERVICES if services[name].get("profiles")]
    assert not unprofiled, (
        f"core demo services must render without a profile gate: {unprofiled} (#555)"
    )


def test_rendered_published_ports_are_loopback_unique_and_expected(rendered_full: dict) -> None:
    """Dev exposes exactly the documented host ports, loopback-bound, no collisions.

    Native replacement for the handwritten short-syntax host-port parser
    (#555): the engine renders long-syntax mappings, so duplicates and
    non-loopback binds are visible directly.
    """
    entries = _published_ports(rendered_full)
    host_ports = [published for _, _, published in entries]
    duplicates = sorted({p for p in host_ports if host_ports.count(p) > 1})
    assert not duplicates, f"duplicate rendered host ports: {duplicates} (#555)"
    assert set(host_ports) == EXPECTED_DEV_HOST_PORTS, (
        f"rendered dev host ports must be exactly {sorted(EXPECTED_DEV_HOST_PORTS)}, "
        f"got {sorted(host_ports)}"
    )
    non_loopback = [(s, ip, p) for s, ip, p in entries if ip != "127.0.0.1"]
    assert not non_loopback, (
        f"all dev host binds must be loopback: {non_loopback} (DOCKER.md ports table)"
    )
    for svc_name in ("bot", "ingestion"):
        assert not (rendered_full["services"][svc_name].get("ports") or []), (
            f"{svc_name} must not publish host ports"
        )


def test_compose_bot_profile_keeps_postgres_optional_and_core_always_on() -> None:
    """Non-full profile retains optional PostgreSQL semantics (#3361/#3241).

    Rendering `--profile bot` must not pull in postgres, the rendered bot
    dependency on postgres must be ``required: false`` so Compose skips it
    when postgres is not part of the active profiles, and the unprofiled core
    services must still render (they are always on).
    """
    result = _render_compose_config("--profile", "bot")
    assert result.returncode == 0, f"Compose bot-profile config failed:\n{result.stderr}"

    services = yaml.safe_load(result.stdout)["services"]
    assert "bot" in services, "bot profile must render the bot service"
    assert "postgres" not in services, (
        "the bot profile must not include postgres: non-full profiles keep "
        "PostgreSQL optional (#3241, #3361)"
    )
    assert set(services) >= ALWAYS_ON_SERVICES, (
        "unprofiled core services must render under --profile bot (always on, #555)"
    )
    postgres_dep = services["bot"]["depends_on"]["postgres"]
    assert postgres_dep.get("required") is False, (
        "rendered bot.depends_on.postgres must be required: false so Compose "
        "skips the dependency when postgres is not active (#3361)"
    )
    assert postgres_dep.get("condition") == "service_healthy"


# =============================================================================
# Single-projection topology: the third core projection stays deleted (#3451)
# =============================================================================

COMPOSE_SOURCE_FILES = (Path("compose.yml"), Path("compose.dev.yml"))
NOAUTH_REDIS_VARIANT_MARKER = "8.10.1-alpine"
MINIMAL_MODE_SERVICES = {"redis", "qdrant", "bge-m3"}
MINIMAL_MODE_VOLUMES = {"hf_cache", "qdrant_data", "redis_data"}


def test_third_core_projection_stays_deleted() -> None:
    """compose.core.yml must stay deleted; every mode renders from base+dev (#3451).

    The minimal core stack is the unprofiled base+dev render (the stack
    ``make docker-core-up`` starts), not a third compose projection:
    re-adding compose.core.yml, the CORE_MIN_COMPOSE_FILE variable, or any
    other Makefile reference would reintroduce the third topology projection
    that audit A12 eliminated.
    """
    assert not Path("compose.core.yml").exists(), (
        "compose.core.yml must stay deleted (#3451): minimal and full modes "
        "render from compose.yml + compose.dev.yml only"
    )
    makefile = Path("Makefile").read_text(encoding="utf-8")
    assert "compose.core" not in makefile, (
        "the Makefile must not reference the deleted compose.core.yml projection (#3451)"
    )


@pytest.mark.parametrize("compose_file", COMPOSE_SOURCE_FILES)
def test_compose_sources_have_no_noauth_redis_duplicate(compose_file: Path) -> None:
    """The no-auth alpine redis variant must not survive as a duplicate (#3451).

    The deleted projection carried a second, no-auth alpine redis alongside
    the authenticated base redis. Exactly one redis service may exist per
    compose source file, and the alpine no-auth image variant must stay
    deleted with the projection (#3354/#3402: redis auth is the base contract).
    """
    text = compose_file.read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    redis_services = [name for name in (loaded.get("services") or {}) if "redis" in name]
    assert redis_services == ["redis"], (
        f"{compose_file} must define exactly one redis service (no no-auth "
        f"redis duplicate), got: {redis_services} (#3451)"
    )
    assert NOAUTH_REDIS_VARIANT_MARKER not in text, (
        f"{compose_file} must not reintroduce the no-auth alpine redis "
        f"variant deleted with compose.core.yml (#3451)"
    )


@pytest.fixture(scope="module")
def rendered_core_minimal() -> dict:
    """The minimal core-mode render: unprofiled base+dev, parsed once (#3451).

    This is the stack ``make docker-core-up`` starts — the engine-rendered
    replacement for the deleted compose.core.yml projection.
    """
    return _render_compose_json()


def test_minimal_core_mode_renders_exactly_the_sidecar_set(
    rendered_core_minimal: dict,
) -> None:
    """The unprofiled base+dev render is the minimal core mode (#3451).

    Engine-rendered replacement for the deleted
    tests/unit/test_core_compose_contract.py pins: exactly redis, qdrant,
    bge-m3 (no postgres/bot/ingestion), every service healthcheck-gated, and
    exactly the three sidecar volumes.
    """
    services = rendered_core_minimal["services"]
    assert set(services) == MINIMAL_MODE_SERVICES, (
        f"the minimal core mode must render exactly {sorted(MINIMAL_MODE_SERVICES)}, "
        f"got {sorted(services)} (#3451)"
    )
    missing_healthcheck = sorted(
        name for name, svc in services.items() if not (svc.get("healthcheck") or {}).get("test")
    )
    assert not missing_healthcheck, (
        f"every minimal-mode service must declare a healthcheck; missing: "
        f"{missing_healthcheck} (#3361 applies to every mode)"
    )
    assert set(rendered_core_minimal.get("volumes") or {}) == MINIMAL_MODE_VOLUMES, (
        f"the minimal core mode must carry exactly {sorted(MINIMAL_MODE_VOLUMES)} (#3451)"
    )


def test_minimal_core_mode_redis_enforces_requirepass(
    rendered_core_minimal: dict,
) -> None:
    """The minimal mode's single redis is the authenticated one (#3451/#3354).

    The no-auth redis of the deleted projection must not reappear: the
    minimal render enforces --requirepass and receives REDIS_PASSWORD (#3402).
    """
    redis = rendered_core_minimal["services"]["redis"]
    command = redis["command"]
    assert isinstance(command, list) and "--requirepass" in command, (
        "the minimal-mode redis must enforce authentication via --requirepass "
        "(no no-auth redis duplicate, #3451)"
    )
    assert redis["environment"].get("REDIS_PASSWORD"), (
        "the minimal-mode redis must receive REDIS_PASSWORD (#3402)"
    )


def test_minimal_core_mode_publishes_loopback_native_dev_ports(
    rendered_core_minimal: dict,
) -> None:
    """The minimal mode keeps the loopback native-dev surface (#3451).

    The deleted projection exposed qdrant 6333/6334 and redis 6379 on
    loopback with zero profile flags; the unprofiled base+dev render must
    keep exactly that surface plus the bge-m3 health port.
    """
    entries = _published_ports(rendered_core_minimal)
    assert {published for _, _, published in entries} == {"6333", "6334", "6379", "8000"}, (
        f"minimal-mode host ports must be exactly 6333/6334/6379/8000, got "
        f"{sorted({p for _, _, p in entries})} (#3451)"
    )
    non_loopback = [(s, ip, p) for s, ip, p in entries if ip != "127.0.0.1"]
    assert not non_loopback, f"minimal-mode binds must stay loopback: {non_loopback}"


# =============================================================================
# Rendered dependencies and capability-honest health (#3361)
# =============================================================================


def test_rendered_bot_waits_for_healthy_dependencies(rendered_full: dict) -> None:
    """bot must wait for healthy core deps; postgres stays required: false (#3361)."""
    depends = rendered_full["services"]["bot"]["depends_on"]
    postgres_dep = depends.get("postgres")
    assert isinstance(postgres_dep, dict), (
        "bot.depends_on must declare postgres as a mapping (#3361): in the "
        "full profile the bot must wait for a healthy PostgreSQL before "
        "capability setup; in non-full profiles the dependency is skipped"
    )
    assert postgres_dep.get("condition") == "service_healthy", (
        "bot.depends_on.postgres must use condition: service_healthy so the "
        "bookmarks capability setup never races a cold PostgreSQL (#3361)"
    )
    assert postgres_dep.get("required") is False, (
        "bot.depends_on.postgres must set required: false (#3361): "
        "PostgreSQL stays optional outside the postgres/full profiles (#3241)"
    )
    for svc in ("redis", "qdrant", "bge-m3"):
        dep = depends.get(svc) or {}
        assert dep.get("condition") == "service_healthy", (
            f"bot.depends_on.{svc} must use condition: service_healthy"
        )
        assert dep.get("required") is True, f"bot.depends_on.{svc} is a CRITICAL dependency"


def test_rendered_ingestion_depends_on_qdrant_and_bge_healthy(rendered_full: dict) -> None:
    """ingestion starts only after Qdrant and BGE-M3 are healthy (#3361)."""
    depends = rendered_full["services"]["ingestion"]["depends_on"]
    for svc in ("qdrant", "bge-m3"):
        dep = depends.get(svc) or {}
        assert dep.get("condition") == "service_healthy", (
            f"ingestion.depends_on.{svc} must use condition: service_healthy (#3361)"
        )


def _rendered_healthcheck_command(rendered_full: dict, service: str) -> str:
    healthcheck = rendered_full["services"][service].get("healthcheck")
    assert healthcheck and healthcheck.get("test"), (
        f"rendered {service} must declare a healthcheck (#3361)"
    )
    test = healthcheck["test"]
    assert isinstance(test, list), f"{service} healthcheck test must be a list"
    return " ".join(str(part) for part in test)


def test_rendered_bot_healthcheck_probes_capability_not_only_process(
    rendered_full: dict,
) -> None:
    """bot healthcheck must probe real dependency capability, not just pgrep.

    #3361: "process-only checks are insufficient" — a bot whose Redis, Qdrant,
    or BGE-M3 dependency became unreachable must report unhealthy instead of
    green. The probe covers the three CRITICAL dependencies; PostgreSQL is
    deliberately absent because it stays an optional capability (#3241).
    """
    command = _rendered_healthcheck_command(rendered_full, "bot")

    assert "pgrep" in command, "bot healthcheck must still prove the process is alive"
    assert "qdrant:6333" in command, (
        "bot healthcheck must probe Qdrant capability (http://qdrant:6333/readyz)"
    )
    assert "bge-m3:8000" in command, (
        "bot healthcheck must probe BGE-M3 capability (http://bge-m3:8000/health)"
    )
    assert "redis" in command, "bot healthcheck must probe Redis reachability"
    assert "postgres" not in command, (
        "bot healthcheck must not require PostgreSQL: it stays an optional "
        "capability and a degraded-but-working bot is still healthy (#3241)"
    )


def test_rendered_ingestion_healthcheck_probes_capability_not_only_process(
    rendered_full: dict,
) -> None:
    """ingestion healthcheck must probe Qdrant readiness and BGE-M3 model load.

    #3361: "process-only checks are insufficient". The probe must stay
    cold-start-safe: it checks Qdrant readiness and the BGE-M3 model-loaded
    capability without requiring the collection to exist (a fresh volume has
    no collection until the first ingest runs).
    """
    command = _rendered_healthcheck_command(rendered_full, "ingestion")

    assert "pgrep" in command, "ingestion healthcheck must still prove the process is alive"
    assert "qdrant:6333/readyz" in command, (
        "ingestion healthcheck must probe Qdrant readiness "
        "(http://qdrant:6333/readyz), not a collection that may not exist yet"
    )
    assert "bge-m3:8000/health" in command, (
        "ingestion healthcheck must probe the BGE-M3 health capability"
    )
    assert "model_loaded" in command, (
        "ingestion healthcheck must assert the BGE-M3 model is actually loaded "
        "(model_loaded), not merely that the endpoint answers"
    )


# =============================================================================
# Rendered environment and auth
# =============================================================================


def test_rendered_bot_defaults_to_single_instance_redis_mode(rendered_full: dict) -> None:
    """The rendered bot must default REDIS_MODE to single_instance (#3354).

    Decision #3354: "Defaults: reusable core disabled; Compose bot
    explicitly single_instance; scaled deployment explicitly multi_instance."
    Asserting the RENDERED value proves the interpolation default, not just
    the template text.
    """
    env = rendered_full["services"]["bot"]["environment"]
    assert env.get("REDIS_MODE") == "single_instance", (
        f"rendered bot REDIS_MODE must default to single_instance, "
        f"found: {env.get('REDIS_MODE')!r} (#3354)"
    )


def test_rendered_bge_m3_url_consumers_use_container_network(rendered_full: dict) -> None:
    """All rendered consumers referencing BGE_M3_URL must use http://bge-m3:8000.

    Container-internal URL prevents the Docker/compose drift bug class
    (#2182, #2188, #2185) where BGE-M3 is reachable on a wrong host port.
    """
    offending: list[tuple[str, str]] = []
    for svc_name, svc in rendered_full["services"].items():
        env = svc.get("environment") or {}
        url = env.get("BGE_M3_URL") or env.get("bge_m3_url")
        if url is not None and url != "http://bge-m3:8000":
            offending.append((svc_name, url))
    assert not offending, f"BGE_M3_URL consumers must use the container URL: {offending}"


def test_rendered_redis_enforces_requirepass_auth(rendered_full: dict) -> None:
    """The rendered redis service must enforce --requirepass auth (#3402)."""
    redis = rendered_full["services"]["redis"]
    command = redis["command"]
    assert isinstance(command, list) and "--requirepass" in command, (
        "rendered redis command must enforce authentication via --requirepass"
    )
    assert redis["environment"].get("REDIS_PASSWORD"), (
        "rendered redis environment must receive REDIS_PASSWORD"
    )


def test_env_example_documents_redis_mode() -> None:
    """.env.example must document REDIS_MODE so native operators see the contract."""
    content = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "REDIS_MODE=" in content, (
        ".env.example must document REDIS_MODE (disabled | single_instance | multi_instance)"
    )
    assert "single_instance" in content, (
        ".env.example REDIS_MODE docs must mention the single_instance default"
    )


# =============================================================================
# Rendered security defaults and capabilities
# =============================================================================


def test_rendered_services_keep_security_defaults(rendered_full: dict) -> None:
    """Every rendered service keeps no-new-privileges and cap_drop ALL (#3402).

    Native replacement for the x-security-defaults anchor text check: the
    rendered config proves the anchor actually reached every service.
    """
    for svc_name, svc in rendered_full["services"].items():
        security_opt = svc.get("security_opt") or []
        assert "no-new-privileges:true" in security_opt, (
            f"{svc_name} must render no-new-privileges:true (x-security-defaults)"
        )
        assert svc.get("cap_drop") == ["ALL"], (
            f"{svc_name} must render cap_drop: [ALL] (x-security-defaults)"
        )


def test_rendered_postgres_keeps_base_cap_drop_with_dev_only_cap_add(rendered_full: dict) -> None:
    """Dev Postgres keeps base cap_drop while adding only startup capabilities."""
    postgres = rendered_full["services"]["postgres"]
    assert set(postgres["cap_add"]) == {
        "CHOWN",
        "FOWNER",
        "DAC_OVERRIDE",
        "SETGID",
        "SETUID",
    }


def test_rendered_ingestion_keeps_caps_required_by_gosu_entrypoint(rendered_full: dict) -> None:
    """ingestion must keep the minimal caps its gosu entrypoint needs to start.

    The image entrypoint runs as root and drops to the fixed non-root
    ``ingestion`` user via gosu (setuid/setgid) after chowning the manifest
    volume. Under the base ``cap_drop: [ALL]`` hardening the container
    crash-loops with "failed switching to ingestion: operation not permitted",
    so a cold full-profile start can never reach six healthy services (#3361
    cold-start proof). The caps are exactly the entrypoint's needs; the
    dropped-to python process runs as a non-root user without them.
    """
    caps = set(rendered_full["services"]["ingestion"].get("cap_add") or [])
    assert {"CHOWN", "SETGID", "SETUID"} <= caps, (
        f"ingestion.cap_add must include CHOWN, SETGID, SETUID for the gosu "
        f"entrypoint under cap_drop: [ALL]; got {sorted(caps)}"
    )


def test_rendered_hub_images_are_digest_pinned(rendered_full: dict) -> None:
    """Every registry image in the render must pin an immutable digest (#1814).

    Locally built services (the rendered config carries a ``build`` block for
    them) are excluded; the Dockerfile FROM-line digest contract covers their
    contents.
    """
    unpinned: list[str] = []
    for svc_name, svc in rendered_full["services"].items():
        if svc.get("build"):
            continue
        if not _DIGEST_RE.search(svc["image"]):
            unpinned.append(f"{svc_name}: {svc['image']}")
    assert not unpinned, f"registry images must pin @sha256 digests: {unpinned} (#1814)"


# Qdrant server pin (#3395): the characterized, digest-pinned server image.
# v1.19.1 is a patch release over v1.19.0 (fixes + performance only, no API
# change for the dense/sparse/ColBERT surface); the digest is the official
# multi-arch OCI index digest of the ``v1.19.1`` tag.
QDRANT_SERVER_IMAGE = (
    "qdrant/qdrant:v1.19.1@sha256:12364fe851b9f17356fc88189fc06d1b521262e04659ec7345975b00c9246a10"
)


def test_rendered_qdrant_server_image_is_the_characterized_pin(rendered_full: dict) -> None:
    """The single qdrant declaration must pin the characterized 1.19.1 digest (#3395)."""
    image = rendered_full["services"]["qdrant"]["image"]
    assert image == QDRANT_SERVER_IMAGE, (
        f"the qdrant server image must be exactly {QDRANT_SERVER_IMAGE} "
        f"(#3395 characterization), got {image}"
    )


# =============================================================================
# Dockerfile runtime policy (#1814, #1307, #1381 — absorbed from A09 contract)
# =============================================================================


@pytest.mark.parametrize("dockerfile", DOCKERFILES)
def test_dockerfile_exists(dockerfile: str) -> None:
    assert Path(dockerfile).is_file(), f"{dockerfile} not found"


@pytest.mark.parametrize("dockerfile", LANGFUSE_RUNTIME_DOCKERFILES)
def test_langfuse_dockerfile_does_not_use_forbidden_python(dockerfile: str) -> None:
    """Forbidden Python versions must not appear in Langfuse-importing runtimes.

    Langfuse SDK uses pydantic.v1 compatibility that crashes under Python 3.14
    (#1307) and warns on import (#1381).
    """
    text = Path(dockerfile).read_text(encoding="utf-8")
    for forbidden in LANGFUSE_PY_FORBIDDEN:
        assert f"python:{forbidden}" not in text, (
            f"{dockerfile} pins forbidden runtime python:{forbidden} "
            f"(Langfuse SDK uses pydantic.v1 incompatible with Python {forbidden}; "
            f"see #1307, #1381)."
        )
        assert f"python{forbidden}" not in text, (
            f"{dockerfile} pins forbidden uv image python{forbidden} (see #1307, #1381)."
        )


@pytest.mark.parametrize("dockerfile", LANGFUSE_RUNTIME_DOCKERFILES)
def test_langfuse_dockerfile_uses_floor_python(dockerfile: str) -> None:
    """Langfuse-importing app images must use the policy Python floor (#1346-#1348)."""
    text = Path(dockerfile).read_text(encoding="utf-8")
    floor = LANGFUSE_PY_FLOOR
    # Accept ``python:{floor}-...`` (runtime image) OR ``python{floor}-...`` (uv image).
    assert (f"python:{floor}" in text) or (f"python{floor}" in text), (
        f"{dockerfile} must pin Python {floor} runtime per the runtime policy (see #1307, #1381)."
    )


@pytest.mark.parametrize("dockerfile", DOCKERFILES)
def test_dockerfile_from_lines_are_digest_pinned(dockerfile: str) -> None:
    """Every external FROM line must keep an ``@sha256:<digest>`` pin (#1814)."""
    text = Path(dockerfile).read_text(encoding="utf-8")
    from_lines = [line for line in text.splitlines() if line.lstrip().startswith("FROM ")]
    base_image_lines = [
        line
        for line in from_lines
        # Skip multi-stage refs of the form ``FROM <stage> AS ...`` where
        # ``<stage>`` is a previously declared stage name (no ``/`` or ``:``).
        if (":" in line.split(" AS ")[0] or "/" in line.split(" AS ")[0])
    ]
    assert base_image_lines, f"{dockerfile} has no external FROM lines"
    for line in base_image_lines:
        assert _DIGEST_RE.search(line), (
            f"{dockerfile}: FROM line missing @sha256 digest pin (policy #1814): {line!r}"
        )


# =============================================================================
# Real build-engine proof (native replacement for the #1993 COPY parser)
# =============================================================================


def _isolated_compose_project() -> str:
    return f"rag-compose-contract-{uuid.uuid4().hex[:8]}"


@pytest.mark.slow
@pytest.mark.timeout(180)
def test_missing_copy_source_fails_real_build(tmp_path: Path) -> None:
    """A Dockerfile COPY whose source is missing must fail the real build (#1993).

    Issue #1993 reported a hard build break from ``COPY pyproject.toml ...``
    with those files absent from the build context. The engine is the
    authority: instead of parsing COPY lines, this proof runs a real
    ``docker compose build`` on a disposable throwaway project and requires
    a nonzero exit naming the missing path. No image is produced by the
    failing build.
    """
    if not _docker_available():
        pytest.skip("Docker / Compose plugin not available")
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.13-slim-bookworm\nCOPY missing.txt /missing.txt\n",
        encoding="utf-8",
    )
    (tmp_path / "compose.yaml").write_text(
        "services:\n  app:\n    build: .\n",
        encoding="utf-8",
    )
    project = _isolated_compose_project()
    try:
        result = subprocess.run(
            ["docker", "compose", "-p", project, "build"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=150,
        )
    finally:
        # Hygiene: if the build unexpectedly succeeded, do not leak the image.
        subprocess.run(
            ["docker", "image", "rm", "-f", f"{project}-app"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    output = result.stdout + result.stderr
    assert result.returncode != 0, f"build with a missing COPY source must fail; output:\n{output}"
    assert "not found" in output, (
        f"the failure must name the missing COPY source; output:\n{output}"
    )


@pytest.mark.slow
@pytest.mark.timeout(60)
def test_nonexistent_build_context_fails_real_build(tmp_path: Path) -> None:
    """A build context that does not exist must fail the real build (#3424)."""
    if not _docker_available():
        pytest.skip("Docker / Compose plugin not available")
    (tmp_path / "compose.yaml").write_text(
        "services:\n  app:\n    build:\n      context: ./does-not-exist\n"
        "      dockerfile: Dockerfile\n",
        encoding="utf-8",
    )
    project = _isolated_compose_project()
    result = subprocess.run(
        ["docker", "compose", "-p", project, "build"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0, f"build with a nonexistent context must fail; output:\n{output}"
    assert "not found" in output, (
        f"the failure must name the missing context path; output:\n{output}"
    )


# =============================================================================
# Makefile consistency (M8/#3379): profile flags and removed aliases
# =============================================================================


def _makefile_docker_up_profiles() -> set[str]:
    """Extract --profile values from Makefile docker-*-up target recipes only."""
    content = Path("Makefile").read_text(encoding="utf-8")
    # Extract only the docker-*-up section (from docker-core-up to the
    # dev-setup development-workflow target; #3379 removed the docker-up
    # alias that previously ended this section).
    section = re.search(r"(docker-core-up:.*?dev-setup:)", content, re.DOTALL)
    if not section:
        return set()
    return set(re.findall(r"--profile\s+(\S+)", section.group(1)))


def test_makefile_docker_profiles_exist_in_compose(rendered_full: dict) -> None:
    """Every --profile in Makefile docker-*-up targets must exist in compose."""
    compose_profiles: set[str] = set()
    for svc in rendered_full["services"].values():
        compose_profiles.update(str(p) for p in svc.get("profiles") or [])
    unknown = _makefile_docker_up_profiles() - compose_profiles
    assert not unknown, (
        f"Makefile docker-*-up targets reference profile(s) not in compose: "
        f"{sorted(unknown)}. Defined profiles: {sorted(compose_profiles)}"
    )


def test_removed_compose_aliases_stay_removed() -> None:
    """#3379 removed the docker-up/core-up/docker-ai-up/docker-ingest-up aliases."""
    content = Path("Makefile").read_text(encoding="utf-8")
    for target in ("core-up", "docker-up", "docker-ai-up", "docker-ingest-up"):
        assert not re.search(rf"^{re.escape(target)}:", content, re.MULTILINE), (
            f"Removed compose alias `{target}` reappeared in the Makefile (#3379)"
        )


# =============================================================================
# CI policy: deterministic rendering fixture (#3367, #3402)
# =============================================================================


def test_compose_dev_config_renders() -> None:
    result = _render_compose_config(config_args=("--quiet",))
    assert result.returncode == 0, f"Compose dev config failed:\n{result.stderr}"


@pytest.mark.parametrize("env_var", ["POSTGRES_PASSWORD", "REDIS_PASSWORD"])
def test_compose_password_vars_are_required_not_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_var: str,
) -> None:
    """POSTGRES_PASSWORD/REDIS_PASSWORD must be required Compose variables.

    Rendering without the variable must fail naming it; a hardcoded ``:-``
    fallback would let ``docker compose config`` succeed without any secret
    (#3402). The Compose engine is the authority here — it interpolates every
    service in both compose.yml and compose.dev.yml.
    """
    monkeypatch.delenv(env_var, raising=False)
    env_lines = [
        line
        for line in COMPOSE_CI_ENV.read_text(encoding="utf-8").splitlines(keepends=True)
        if not line.startswith(f"{env_var}=")
    ]
    env_file = tmp_path / "compose.ci.no-password.env"
    env_file.write_text("".join(env_lines), encoding="utf-8")

    result = _run_docker_command(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            "compose.yml",
            "-f",
            "compose.dev.yml",
            "config",
            "--quiet",
        ],
    )
    assert result.returncode != 0, (
        f"{env_var} must be a required Compose variable; a ':-' fallback "
        "let config rendering succeed without it"
    )
    assert env_var in (result.stderr or ""), (
        f"rendering without {env_var} must report the missing required "
        f"variable by name, got: {result.stderr}"
    )


def test_compose_ci_telegram_token_is_sdk_valid() -> None:
    """Fallback env must let `make bot` reach runtime startup, not fail token parsing."""
    values = dict(
        line.split("=", 1)
        for line in COMPOSE_CI_ENV.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )

    validate_token(values["TELEGRAM_BOT_TOKEN"])


# =============================================================================
# BGE-M3 ONNX runtime packaging gate (#2229, #3366)
# =============================================================================


def test_bge_m3_build_uses_onnx_model_context() -> None:
    """bge-m3 must bake ONNX INT8 artifacts into the image at build time (#2229)."""
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    build = compose["services"]["bge-m3"]["build"]
    assert build["additional_contexts"]["bge_m3_onnx_model"].startswith(
        "${BGE_M3_ONNX_MODEL_HOST_DIR:"
    ), (
        "bge-m3 build must use BGE_M3_ONNX_MODEL_HOST_DIR as a named build "
        "context for ONNX INT8 artifacts"
    )


def test_bge_m3_has_hf_subdirectory_mount() -> None:
    """bge-m3 should mount a narrower HF-only subdirectory (e.g. /models/hf)
    so the ONNX path /models/onnx remains usable (#2229)."""
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    volumes = compose["services"]["bge-m3"].get("volumes", [])
    targets: set[str] = set()
    for vol in volumes:
        target = vol.split(":")[1].split("@")[0] if isinstance(vol, str) else vol.get("target", "")
        targets.add(target)
    assert "/models/hf" in targets, (
        "bge-m3 needs a narrow HF cache mount at /models/hf so "
        "/models/onnx for ONNX artifacts is not masked"
    )
    assert "/models/onnx" not in targets, (
        "bge-m3 must not mount /models/onnx at runtime; the INT8 model is "
        "baked into the Docker image during build"
    )


def test_bge_m3_model_cache_dir_uses_writable_hf_cache() -> None:
    """The tokenizer cache must use the HF volume, not /models root (#2229)."""
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    environment = compose["services"]["bge-m3"]["environment"]
    assert environment["MODEL_CACHE_DIR"] == "/models/hf"
    assert environment["HF_HOME"] == "/models/hf"
    assert environment["TRANSFORMERS_CACHE"] == "/models/hf"


def test_bge_m3_dockerfile_prepares_model_dirs_for_appuser() -> None:
    """Named volumes inherit target ownership on first use; prepare /models."""
    dockerfile = Path("services/bge-m3-api/Dockerfile").read_text(encoding="utf-8")
    assert "mkdir -p /models/hf /models/artifact" in dockerfile
    assert "chown -R appuser:appgroup /models" in dockerfile


def test_bge_m3_dockerfile_bakes_verified_artifact_from_build_context() -> None:
    """The image must verify the pinned artifact (manifest + sha256) before baking
    it, so the 41-byte dummy fixtures can never be silently substituted (#3366)."""
    dockerfile = Path("services/bge-m3-api/Dockerfile").read_text(encoding="utf-8")
    assert "from=bge_m3_onnx_model" in dockerfile
    assert "verify_artifact.py" in dockerfile, "build must run the manifest verifier"
    assert "artifact_manifest.json" in dockerfile
    assert "model.onnx" in dockerfile
    assert "model.onnx_data" in dockerfile
    assert "cp /tmp/bge-m3-onnx/model.onnx" in dockerfile
    assert "cp -r /tmp/bge-m3-onnx/tokenizer/" in dockerfile, "tokenizer assets must be baked"


def test_bge_m3_dockerfile_verifies_against_repository_pin_manifest() -> None:
    """The expected manifest at the build boundary must be the repository's
    committed artifact_manifest.json, never the artifact-folder's own manifest:
    replacing model bytes together with their folder manifest must fail the
    build (#3366 audit blocker)."""
    dockerfile = Path("services/bge-m3-api/Dockerfile").read_text(encoding="utf-8")
    assert "COPY artifact_manifest.json /tmp/repository_artifact_manifest.json" in dockerfile, (
        "the trusted pin manifest must be copied from the repository build context"
    )
    assert "--expected-manifest /tmp/repository_artifact_manifest.json" in dockerfile, (
        "verification must run in pin mode against the repository manifest"
    )
    assert "--manifest /tmp/bge-m3-onnx/artifact_manifest.json" not in dockerfile, (
        "the artifact-folder manifest must not be its own verification authority"
    )
    assert (
        "cp /tmp/repository_artifact_manifest.json /models/artifact/artifact_manifest.json"
        in dockerfile
    ), "the baked runtime manifest must be the repository pin copy, not the artifact folder's"


def test_bge_m3_dockerfile_sets_offline_env() -> None:
    """Runtime must be strictly offline: hub access disabled, tokenizer local."""
    dockerfile = Path("services/bge-m3-api/Dockerfile").read_text(encoding="utf-8")
    assert "HF_HUB_OFFLINE=1" in dockerfile
    assert "TRANSFORMERS_OFFLINE=1" in dockerfile
    assert "ONNX_MODEL_DIR=/models/artifact" in dockerfile
    assert "TOKENIZER_DIR=/models/artifact/tokenizer" in dockerfile


def test_bge_m3_dockerfile_ships_offline_smoke_script() -> None:
    """The network-disabled container smoke must be runnable inside the image."""
    dockerfile = Path("services/bge-m3-api/Dockerfile").read_text(encoding="utf-8")
    assert "smoke_offline.py" in dockerfile
    assert Path("services/bge-m3-api/smoke_offline.py").is_file()


def test_bge_m3_onnx_model_dir_env_in_ci_env() -> None:
    """tests/fixtures/compose.ci.env must define BGE_M3_ONNX_MODEL_HOST_DIR so
    Compose config rendering can resolve the build context source (#2229)."""
    ci_env = dict(
        line.split("=", 1)
        for line in COMPOSE_CI_ENV.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )
    assert "BGE_M3_ONNX_MODEL_HOST_DIR" in ci_env, (
        "BGE_M3_ONNX_MODEL_HOST_DIR is missing from tests/fixtures/compose.ci.env; "
        "Compose config rendering requires it for the ONNX model build context"
    )
    model_dir = Path(ci_env["BGE_M3_ONNX_MODEL_HOST_DIR"])
    assert not model_dir.is_absolute(), (
        "tests/fixtures/compose.ci.env must use a repo-relative ONNX fixture path, "
        f"not a host-specific absolute path: {model_dir}"
    )
    assert (model_dir / "model.onnx").is_file(), (
        "Compose CI BGE model context must include model.onnx so "
        "`docker compose build bge-m3` does not depend on host-local artifacts"
    )
    assert (model_dir / "model.onnx_data").is_file(), (
        "Compose CI BGE model context must include model.onnx_data so "
        "`docker compose build bge-m3` does not depend on host-local artifacts"
    )


def test_bge_m3_onnx_model_dir_env_in_env_example() -> None:
    """.env.example must document BGE_M3_ONNX_MODEL_HOST_DIR as a local-dev
    path for the ONNX INT8 artifact bind mount (#2229)."""
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "BGE_M3_ONNX_MODEL_HOST_DIR" in text, (
        "BGE_M3_ONNX_MODEL_HOST_DIR must be documented in .env.example "
        "for local ONNX model provisioning"
    )
    assert "/home/user/" not in text, (
        ".env.example must not hardcode developer-local absolute paths"
    )


def test_compose_dev_bge_m3_renders_with_canonical_port(rendered_full: dict) -> None:
    """bge-m3 must render publishing the canonical 127.0.0.1:8000->8000 mapping.

    Guards the Docker/compose drift bug class (#2182, #2188, #2185): a
    healthy internal container without the canonical host port mapping.
    """
    bge_m3 = rendered_full["services"]["bge-m3"]
    assert bge_m3["build"]["context"], "bge-m3 must render with a build context"
    canonical = [
        port
        for port in bge_m3.get("ports") or []
        if str(port.get("host_ip")) == "127.0.0.1"
        and str(port.get("published")) == "8000"
        and str(port.get("target")) == "8000"
    ]
    assert canonical, (
        f"bge-m3 must publish 127.0.0.1:8000->8000, rendered ports: "
        f"{bge_m3.get('ports')} (#2182, #2188, #2185)"
    )
