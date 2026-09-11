"""Regression checks for compose runtime contracts behind issue #1074."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]
BASE_COMPOSE = ROOT / "compose.yml"
DEV_COMPOSE = ROOT / "compose.dev.yml"


def _load_compose() -> dict:
    return yaml.safe_load(BASE_COMPOSE.read_text())


# =============================================================================
# BGE-M3 compose contract — guardrail for #2182 / #2188 / #2185 (Docker/compose drift)
# =============================================================================


def _merge_compose_dev() -> dict:
    """Load base + dev overrides merged via YAML recursion (simulating docker compose merge)."""
    base = yaml.safe_load(BASE_COMPOSE.read_text())
    dev = yaml.safe_load(DEV_COMPOSE.read_text())

    for svc_name, svc_dev in dev.get("services", {}).items():
        if svc_name not in base.get("services", {}):
            base["services"][svc_name] = svc_dev
            continue
        svc_base = base["services"][svc_name]
        for key, value in svc_dev.items():
            if key == "environment":
                current = svc_base.get("environment", {})
                if isinstance(current, list):
                    current = {}
                env_override = (
                    value
                    if isinstance(value, dict)
                    else {e.split("=", 1)[0]: e.split("=", 1)[1] for e in value if "=" in e}
                )
                current.update(env_override)
                svc_base["environment"] = current
            elif key == "ports":
                svc_base["ports"] = value
            elif key in ("deploy", "command", "healthcheck"):
                current = svc_base.get(key, {})
                if isinstance(current, dict) and isinstance(value, dict):
                    current.update(value)
                    svc_base[key] = current
                else:
                    svc_base[key] = value
            else:
                svc_base[key] = value

    return base


def test_bge_m3_dev_publishes_canonical_port() -> None:
    """compose.dev.yml must publish bge-m3 as 127.0.0.1:8000:8000."""
    merged = _merge_compose_dev()
    ports = merged["services"]["bge-m3"].get("ports", [])
    canonical = "127.0.0.1:8000:8000"

    assert canonical in ports, (
        f"compose.dev.yml must publish bge-m3 as '{canonical}'. "
        f"Found ports: {ports}. This prevents the Docker/compose drift "
        f"bug class (#2182, #2188, #2185) where a healthy internal container "
        f"lacks the canonical host port mapping."
    )


def test_bge_m3_healthcheck_uses_localhost_8000_health() -> None:
    """compose.yml BGE-M3 healthcheck must use http://localhost:8000/health."""
    compose = _load_compose()
    test_cmd = compose["services"]["bge-m3"]["healthcheck"]["test"]

    assert isinstance(test_cmd, list)
    cmd_str = " ".join(test_cmd)
    assert "http://localhost:8000/health" in cmd_str, (
        f"compose.yml BGE-M3 healthcheck must use 'http://localhost:8000/health'. "
        f"Found: {cmd_str}. This guards against containers that are healthy "
        f"internally but reachable on a wrong port externally (#2182, #2188)."
    )


def test_all_compose_bge_m3_url_consumers_use_container_network() -> None:
    """All compose consumers referencing BGE_M3_URL must use http://bge-m3:8000."""
    compose = _load_compose()
    offending: list[tuple[str, str]] = []

    for svc_name, svc in compose.get("services", {}).items():
        env = svc.get("environment", {})
        if isinstance(env, dict):
            bge_url = env.get("BGE_M3_URL") or env.get("bge_m3_url")
        elif isinstance(env, list):
            bge_url = None
            for e in env:
                if "=" in e:
                    k, v = e.split("=", 1)
                    if k in ("BGE_M3_URL", "bge_m3_url"):
                        bge_url = v
                        break
        else:
            continue

        if bge_url is not None and bge_url != "http://bge-m3:8000":
            offending.append((svc_name, bge_url))

    assert not offending, (
        "All compose consumers must use 'http://bge-m3:8000' for BGE_M3_URL. "
        f"Offending: {offending}. Container-internal URL prevents the "
        f"Docker/compose drift bug class (#2182, #2188, #2185) where "
        f"BGE-M3 is reachable on a wrong host port."
    )


# =============================================================================
# Redis mode compose contract (#3362, decision #3354)
# =============================================================================


def test_bot_defaults_explicitly_to_single_instance_redis_mode() -> None:
    """compose.yml bot must default REDIS_MODE to single_instance explicitly.

    Decision #3354: "Defaults: reusable core disabled; Compose bot
    explicitly single_instance; scaled deployment explicitly multi_instance."
    """
    compose = _load_compose()
    env = compose["services"]["bot"]["environment"]

    assert isinstance(env, dict), "bot environment must be a mapping"
    assert "REDIS_MODE" in env, "compose.yml bot environment must set REDIS_MODE explicitly (#3354)"
    assert env["REDIS_MODE"] == "${REDIS_MODE:-single_instance}", (
        f"compose.yml bot REDIS_MODE must default to single_instance, found: {env['REDIS_MODE']!r}"
    )


# =============================================================================
# Capability-honest healthchecks (#3361)
# =============================================================================


def _healthcheck_command(service: str) -> str:
    """Return the rendered healthcheck test command for one compose service."""
    healthcheck = _load_compose()["services"][service].get("healthcheck")
    assert healthcheck, f"compose.yml {service} must declare a healthcheck (#3361)"
    test = healthcheck["test"]
    assert isinstance(test, list), f"{service} healthcheck test must be a list"
    return " ".join(str(part) for part in test)


def test_bot_healthcheck_probes_capability_not_only_process() -> None:
    """bot healthcheck must probe real dependency capability, not just pgrep.

    #3361: "process-only checks are insufficient" — a bot whose Redis, Qdrant,
    or BGE-M3 dependency became unreachable must report unhealthy instead of
    green. The probe covers the three CRITICAL dependencies; PostgreSQL is
    deliberately absent because it stays an optional capability (#3241).
    """
    command = _healthcheck_command("bot")

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


def test_ingestion_healthcheck_probes_capability_not_only_process() -> None:
    """ingestion healthcheck must probe Qdrant and BGE-M3 capability, not just pgrep.

    #3361: "process-only checks are insufficient". The probe must stay
    cold-start-safe: it checks Qdrant readiness and the BGE-M3 model-loaded
    capability without requiring the collection to exist (a fresh volume has
    no collection until the first ingest runs).
    """
    command = _healthcheck_command("ingestion")

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


def test_ingestion_keeps_caps_required_by_gosu_entrypoint() -> None:
    """ingestion must keep the minimal caps its gosu entrypoint needs to start.

    The image entrypoint runs as root and drops to the fixed non-root
    ``ingestion`` user via gosu (setuid/setgid) after chowning the manifest
    volume. Under the base ``cap_drop: [ALL]`` hardening the container
    crash-loops with "failed switching to ingestion: operation not permitted",
    so a cold full-profile start can never reach six healthy services (#3361
    cold-start proof). The caps are exactly the entrypoint's needs; the
    dropped-to python process runs as a non-root user without them.
    """
    ingestion = _load_compose()["services"]["ingestion"]
    caps = set(ingestion.get("cap_add") or [])
    assert {"CHOWN", "SETGID", "SETUID"} <= caps, (
        f"ingestion.cap_add must include CHOWN, SETGID, SETUID for the gosu "
        f"entrypoint under cap_drop: [ALL]; got {sorted(caps)}"
    )


def test_env_example_documents_redis_mode() -> None:
    """.env.example must document REDIS_MODE so native operators see the contract."""
    env_example = ROOT / ".env.example"
    content = env_example.read_text(encoding="utf-8")
    assert "REDIS_MODE=" in content, (
        ".env.example must document REDIS_MODE (disabled | single_instance | multi_instance)"
    )
    assert "single_instance" in content, (
        ".env.example REDIS_MODE docs must mention the single_instance default"
    )
