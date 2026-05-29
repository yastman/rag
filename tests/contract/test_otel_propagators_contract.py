"""Contract: OTEL_PROPAGATORS is explicitly declared in compose (#2246 F3).

The OpenTelemetry Python SDK defaults its global propagator to
``tracecontext,baggage``, so cross-service W3C TraceContext + Baggage
propagation is *currently* correct even without an explicit setting. But that
default is implicit — a base-image bump or an ``OTEL_PROPAGATORS`` shift in the
environment could silently change it and break cross-service trace continuity
with zero signal.

#2246 F3 hardens this for defense-in-depth: every OTEL-instrumented compose
service (identified by setting ``OTEL_SERVICE_NAME``) must also declare
``OTEL_PROPAGATORS`` with a default that includes both ``tracecontext`` and
``baggage``. This contract pins that so the explicit declaration cannot be
silently dropped.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "compose.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

REQUIRED_PROPAGATORS = ("tracecontext", "baggage")


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _get_service_env(compose: dict, service: str) -> dict[str, str]:
    """Normalize a compose service's ``environment`` (mapping or list) to a dict."""
    svc = compose.get("services", {}).get(service) or {}
    env = svc.get("environment", {})
    if isinstance(env, list):
        return {
            item.split("=", 1)[0]: (item.split("=", 1)[1] if "=" in item else "") for item in env
        }
    return env or {}


@pytest.fixture(scope="module")
def compose_base() -> dict:
    return _load_yaml(COMPOSE)


def _otel_instrumented_services(compose: dict) -> list[str]:
    """Services that set OTEL_SERVICE_NAME — i.e., emit OTel/Langfuse spans."""
    services = []
    for name in compose.get("services", {}):
        env = _get_service_env(compose, name)
        if "OTEL_SERVICE_NAME" in env:
            services.append(name)
    return services


def test_some_services_are_otel_instrumented(compose_base: dict) -> None:
    """Sanity: the scan is not vacuous."""
    instrumented = _otel_instrumented_services(compose_base)
    assert instrumented, (
        "No compose service sets OTEL_SERVICE_NAME — the OTEL_PROPAGATORS "
        "contract would be vacuous. Verify compose.yml / the env shape (#2246 F3)."
    )


def test_otel_services_declare_propagators(compose_base: dict) -> None:
    """Every OTEL-instrumented service declares OTEL_PROPAGATORS w/ the W3C pair."""
    missing: list[str] = []
    wrong: list[tuple[str, str]] = []
    for name in _otel_instrumented_services(compose_base):
        env = _get_service_env(compose_base, name)
        value = env.get("OTEL_PROPAGATORS")
        if value is None:
            missing.append(name)
            continue
        lowered = str(value).lower()
        if not all(p in lowered for p in REQUIRED_PROPAGATORS):
            wrong.append((name, str(value)))

    assert not missing, (
        "OTEL-instrumented compose services missing an explicit OTEL_PROPAGATORS "
        f"declaration (#2246 F3): {sorted(missing)}. Add "
        'OTEL_PROPAGATORS: "${OTEL_PROPAGATORS:-tracecontext,baggage}".'
    )
    assert not wrong, (
        "OTEL_PROPAGATORS must include both 'tracecontext' and 'baggage' "
        f"(#2246 F3). Offending services: {wrong}."
    )


def test_env_example_documents_propagators() -> None:
    """`.env.example` documents OTEL_PROPAGATORS so operators can see/override it."""
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "OTEL_PROPAGATORS" in text, (
        ".env.example must document OTEL_PROPAGATORS (tracecontext,baggage) so the "
        "propagation contract is discoverable and overridable (#2246 F3)."
    )
