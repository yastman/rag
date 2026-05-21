"""Contract: Single source of truth for Dockerfile base-image runtime policy.

Closes #1814. Related: #1307, #1346–#1348, #1381 (Langfuse+Pydantic v1 vs Python 3.14).

Why this file exists
--------------------
Two pre-existing test suites were enforcing the same runtime policy from
different angles:

* ``tests/unit/test_docker_static_validation.py`` — checked Python 3.14
  is absent and Python 3.13 is present in Langfuse-importing app images.
* ``tests/unit/mini_app/test_frontend_runtime_contract.py`` — checked the
  Mini App frontend Node builder pins ``node:20.20.2-slim``.

When Renovate updates (#1776, #1783) bumped Python and Node base images
without updating either test, the two contracts silently drifted out of
agreement with reality. This contract consolidates **the policy itself** in
a single place so that any future drift surfaces immediately and a single
edit is enough to evolve the policy intentionally.

Policy
------
``LANGFUSE_PY_FLOOR = "3.13"``
    Langfuse 4.x imports ``pydantic.v1.datetime_parse`` for SDK back-compat.
    Pydantic v1 emits ``UserWarning: Core Pydantic V1 functionality isn't
    compatible with Python 3.14 or greater`` on import (#1381) and crashes
    with ``pydantic.v1.errors.ConfigError`` at runtime under 3.14 (#1307).
    All Langfuse-importing Docker runtimes therefore pin Python 3.13.

``MINI_APP_NODE_FLOOR = "20.20.2"``
    Aligns with ``mini_app/frontend/package.json`` ``engines.node`` upper
    floor of ``^20.19.0`` (and lock file). Renovate bumped to Node 24
    without revalidating the React 19 / Vite 8 toolchain matrix (#1783),
    so we stay on the supported floor until that revalidation lands.

Digest pinning
--------------
The acceptance criteria for #1814 explicitly require digest pinning to be
preserved. The contract therefore asserts both the tag and that an
``@sha256:<64 hex>`` digest is present.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# ── Policy: single source of truth ───────────────────────────────────────────

LANGFUSE_PY_FLOOR: str = "3.13"
"""Required Python minor version for Langfuse-importing app runtimes."""

LANGFUSE_PY_FORBIDDEN: tuple[str, ...] = ("3.14",)
"""Python minor versions that MUST NOT appear in Langfuse-importing runtimes."""

MINI_APP_NODE_FLOOR: str = "20.20.2"
"""Required Node version for the Mini App frontend builder stage."""


# ── Subjects under contract ──────────────────────────────────────────────────

REPO_ROOT: Path = Path(__file__).resolve().parents[2]

LANGFUSE_RUNTIME_DOCKERFILES: tuple[str, ...] = (
    "telegram_bot/Dockerfile",
    "mini_app/Dockerfile",
    "src/api/Dockerfile",
    "Dockerfile.ingestion",
)
"""Dockerfiles whose runtime imports ``telegram_bot.observability`` (Langfuse)."""

MINI_APP_FRONTEND_DOCKERFILE: str = "mini_app/frontend/Dockerfile"


# ── Helpers ──────────────────────────────────────────────────────────────────

_DIGEST_RE = re.compile(r"@sha256:[a-f0-9]{64}")


def _read(rel: str) -> str:
    path = REPO_ROOT / rel
    assert path.is_file(), f"{rel} not found at {path}"
    return path.read_text(encoding="utf-8")


def _from_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.lstrip().startswith("FROM ")]


# ── Langfuse Python runtime contract ─────────────────────────────────────────


@pytest.mark.parametrize("dockerfile", LANGFUSE_RUNTIME_DOCKERFILES)
def test_langfuse_runtime_uses_floor_python(dockerfile: str) -> None:
    """Langfuse-importing runtimes must use the policy-defined Python floor."""
    text = _read(dockerfile)
    floor = LANGFUSE_PY_FLOOR
    # Accept ``python:3.13-...`` (runtime image) OR ``python3.13-...`` (uv image).
    assert (f"python:{floor}" in text) or (f"python{floor}" in text), (
        f"{dockerfile} must pin Python {floor} runtime per the runtime policy "
        f"(see #1307, #1381). Found FROM lines: {_from_lines(text)}"
    )


@pytest.mark.parametrize("dockerfile", LANGFUSE_RUNTIME_DOCKERFILES)
def test_langfuse_runtime_does_not_use_forbidden_python(dockerfile: str) -> None:
    """Forbidden Python versions must not appear in Langfuse-importing runtimes."""
    text = _read(dockerfile)
    for forbidden in LANGFUSE_PY_FORBIDDEN:
        assert f"python:{forbidden}" not in text, (
            f"{dockerfile} pins forbidden runtime python:{forbidden} "
            f"(Langfuse SDK uses pydantic.v1 incompatible with Python {forbidden}; "
            f"see #1307, #1381)."
        )
        assert f"python{forbidden}" not in text, (
            f"{dockerfile} pins forbidden uv image python{forbidden} "
            f"(see #1307, #1381)."
        )


@pytest.mark.parametrize("dockerfile", LANGFUSE_RUNTIME_DOCKERFILES)
def test_langfuse_runtime_preserves_digest_pinning(dockerfile: str) -> None:
    """Every base image FROM line must keep an ``@sha256:<digest>`` pin (#1814)."""
    text = _read(dockerfile)
    base_image_lines = [
        line
        for line in _from_lines(text)
        # Skip multi-stage refs of the form ``FROM <stage> AS ...`` where
        # ``<stage>`` is a previously declared stage name (no ``/`` or ``:``).
        if (":" in line.split(" AS ")[0] or "/" in line.split(" AS ")[0])
    ]
    assert base_image_lines, f"{dockerfile} has no external FROM lines"
    for line in base_image_lines:
        assert _DIGEST_RE.search(line), (
            f"{dockerfile}: FROM line missing @sha256 digest pin (policy #1814): {line!r}"
        )


# ── Mini App frontend Node policy ────────────────────────────────────────────


def test_mini_app_frontend_builder_uses_node_floor() -> None:
    """The Mini App frontend builder must pin ``node:<floor>-slim``."""
    text = _read(MINI_APP_FRONTEND_DOCKERFILE)
    pattern = re.compile(
        rf"FROM node:{re.escape(MINI_APP_NODE_FLOOR)}-slim(?:@sha256:[a-f0-9]{{64}})? AS builder"
    )
    assert pattern.search(text), (
        f"{MINI_APP_FRONTEND_DOCKERFILE} must pin "
        f"node:{MINI_APP_NODE_FLOOR}-slim AS builder per Mini App Node policy "
        f"(#1814). Found FROM lines: {_from_lines(text)}"
    )


def test_mini_app_frontend_builder_preserves_digest_pinning() -> None:
    """The Mini App frontend builder Node image must keep an ``@sha256:`` pin."""
    text = _read(MINI_APP_FRONTEND_DOCKERFILE)
    builder_lines = [line for line in _from_lines(text) if "node:" in line]
    assert builder_lines, (
        f"{MINI_APP_FRONTEND_DOCKERFILE}: no Node FROM line found"
    )
    for line in builder_lines:
        assert _DIGEST_RE.search(line), (
            f"{MINI_APP_FRONTEND_DOCKERFILE}: Node FROM line missing "
            f"@sha256 digest pin (policy #1814): {line!r}"
        )


# ── Cross-suite consistency: this contract drives the existing unit tests ────


def test_policy_matches_legacy_unit_test_constants() -> None:
    """Sanity: legacy unit tests must encode the same policy as this contract.

    Guards against silent drift where one suite is updated and the other
    is forgotten. The legacy ``_LANGFUSE_RUNTIME_DOCKERFILES`` list and the
    Mini App Node floor regex must continue to match this contract.
    """
    docker_static = _read("tests/unit/test_docker_static_validation.py")
    frontend_unit = _read("tests/unit/mini_app/test_frontend_runtime_contract.py")

    # Legacy suite must enforce the same Python floor.
    assert f'"python3.{LANGFUSE_PY_FLOOR.split(".")[1]}"' in docker_static or (
        f'python:{LANGFUSE_PY_FLOOR}' in docker_static
    ), (
        "tests/unit/test_docker_static_validation.py must reference Python "
        f"{LANGFUSE_PY_FLOOR}; if the policy changes, update both files."
    )

    # Legacy suite must list the same Langfuse Dockerfiles.
    for dockerfile in LANGFUSE_RUNTIME_DOCKERFILES:
        assert f'"{dockerfile}"' in docker_static, (
            f"tests/unit/test_docker_static_validation.py "
            f"_LANGFUSE_RUNTIME_DOCKERFILES must include {dockerfile}"
        )

    # Frontend unit test must reference the same Node floor.
    assert MINI_APP_NODE_FLOOR.replace(".", r"\.") in frontend_unit, (
        "tests/unit/mini_app/test_frontend_runtime_contract.py must reference "
        f"Node floor {MINI_APP_NODE_FLOOR}; if the policy changes, update both files."
    )
