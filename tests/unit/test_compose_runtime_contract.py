"""Regression checks for compose runtime contracts behind issue #1074."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]
BASE_COMPOSE = ROOT / "compose.yml"
DEV_COMPOSE = ROOT / "compose.dev.yml"
LIVEKIT_URL_EXPR = "${LIVEKIT_URL:-ws://livekit-server:7880}"
LIVEKIT_CONFIG = ROOT / "docker" / "livekit" / "livekit.yaml"


def _load_compose() -> dict:
    return yaml.safe_load(BASE_COMPOSE.read_text())


def test_minio_base_command_exposes_console_address() -> None:
    compose = _load_compose()
    command = compose["services"]["minio"]["command"]

    assert '--console-address ":9001"' in command


def test_voice_agent_uses_env_driven_livekit_url() -> None:
    compose = _load_compose()
    environment = compose["services"]["voice-agent"]["environment"]

    assert environment["LIVEKIT_URL"] == LIVEKIT_URL_EXPR


def test_voice_agent_healthcheck_checks_voice_agent_process() -> None:
    compose = _load_compose()
    healthcheck = compose["services"]["voice-agent"]["healthcheck"]["test"]

    assert healthcheck == ["CMD", "python", "-m", "src.voice.healthcheck"]


def test_livekit_sip_uses_env_driven_livekit_url_everywhere() -> None:
    compose = _load_compose()
    environment = compose["services"]["livekit-sip"]["environment"]

    assert environment["LIVEKIT_WS_URL"] == LIVEKIT_URL_EXPR
    assert f"ws_url: {LIVEKIT_URL_EXPR}" in environment["SIP_CONFIG_BODY"]


def test_livekit_server_receives_api_secret() -> None:
    compose = _load_compose()
    environment = compose["services"]["livekit-server"]["environment"]

    assert environment["LIVEKIT_API_SECRET"] == "${LIVEKIT_API_SECRET:-}"


def test_livekit_template_secret_has_no_hardcoded_fallback() -> None:
    config_text = LIVEKIT_CONFIG.read_text()

    assert "${LIVEKIT_API_SECRET:-secret}" not in config_text
    assert "LIVEKIT_API_SECRET" in config_text


def test_clickhouse_command_has_no_invalid_listen_host_flag() -> None:
    """ClickHouse 26.3.9 rejects --listen_host as a CLI flag; config file is the correct mechanism."""
    compose = _load_compose()
    clickhouse = compose["services"]["clickhouse"]
    command = clickhouse.get("command", "")

    assert "--listen_host=0.0.0.0" not in str(command), (
        "compose.yml: clickhouse --listen_host=0.0.0.0 is not a valid CLI flag in ClickHouse 26.3.9 "
        "and causes a crash-loop (issue #1340). Remove it and rely on the image default config."
    )


def test_clickhouse_keeps_startup_capabilities_for_named_volumes() -> None:
    """ClickHouse entrypoint must be able to chown its named data/log volumes.

    The shared security defaults intentionally use cap_drop:[ALL]. The official
    ClickHouse image still runs an entrypoint that chowns /var/lib/clickhouse on
    startup and then drops to the clickhouse user; without these capabilities
    the local Langfuse stack crash-loops before trace validation can start.
    """
    compose = _load_compose()
    clickhouse = compose["services"]["clickhouse"]

    assert "ALL" in clickhouse.get("cap_drop", []), (
        "compose.yml: clickhouse must keep cap_drop:[ALL] from the shared security defaults."
    )
    assert clickhouse.get("cap_add") == ["CHOWN", "SETGID", "SETUID"], (
        "compose.yml: clickhouse must add only CHOWN/SETGID/SETUID so the "
        "official entrypoint can chown /var/lib/clickhouse named volumes and "
        "drop to the clickhouse user. Without this, `make validate-traces-fast` "
        "fails with ClickHouse `chown` or `setgid` Operation not permitted errors."
    )


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
