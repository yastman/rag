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
