"""Regression checks for compose runtime contracts behind issue #1074."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]
BASE_COMPOSE = ROOT / "compose.yml"
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
