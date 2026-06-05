"""Contract: core proof runtime starts only Qdrant and BGE-M3."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"

CORE_PROOF_SERVICES = {"qdrant", "bge-m3"}
BOT_DEV_SERVICES = {"postgres", "redis", "qdrant", "bge-m3", "litellm"}
OPTIONAL_SURFACE_SERVICES = {
    "bot",
    "docling",
    "ingestion",
    "langfuse",
    "langfuse-worker",
    "livekit",
    "mini-app-api",
    "mini-app-frontend",
    "postgres",
    "promtail",
    "redis",
    "sip",
    "voice-agent",
}


def _makefile_text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def _target_body(text: str, target: str) -> str:
    pattern = re.compile(rf"^{re.escape(target)}:.*$", re.MULTILINE)
    match = pattern.search(text)
    assert match is not None, f"Makefile must define {target!r}"

    body_lines: list[str] = []
    for line in text[match.end() :].splitlines():
        if line and not line.startswith(("\t", " ", "\\")):
            break
        body_lines.append(line)
    return "\n".join(body_lines)


def _make_var(text: str, name: str) -> set[str]:
    pattern = re.compile(rf"^{re.escape(name)}\s*:?=\s*(.*?)$", re.MULTILINE)
    match = pattern.search(text)
    assert match is not None, f"Makefile must define {name}"
    return set(match.group(1).split())


def test_core_services_are_qdrant_and_bge_only() -> None:
    text = _makefile_text()
    assert _make_var(text, "CORE_SERVICES") == CORE_PROOF_SERVICES


def test_core_up_and_down_use_only_core_services() -> None:
    text = _makefile_text()
    for target in ("core-up", "core-down"):
        body = _target_body(text, target)
        assert "$(CORE_SERVICES)" in body
        offenders = sorted(service for service in OPTIONAL_SURFACE_SERVICES if service in body)
        assert not offenders, f"{target} must not mention non-core services: {offenders}"


def test_core_up_waits_for_core_service_healthchecks() -> None:
    body = _target_body(_makefile_text(), "core-up")
    assert "--wait" in body


def test_e2e_core_live_does_not_start_optional_surfaces() -> None:
    body = _target_body(_makefile_text(), "e2e-core-live")
    forbidden = sorted(
        token
        for token in (
            "local-up",
            "docker-bot-up",
            "docker-ml-up",
            "docker-ingest-up",
            "langfuse",
            "telegram",
            "voice",
            "mini-app",
            "redis",
            "postgres",
            "litellm",
        )
        if token in body.lower()
    )
    assert not forbidden, f"e2e-core-live must stay Qdrant+BGE-only: {forbidden}"


def test_local_up_remains_broader_bot_dev_runtime_for_now() -> None:
    text = _makefile_text()
    assert _make_var(text, "LOCAL_SERVICES") == BOT_DEV_SERVICES
