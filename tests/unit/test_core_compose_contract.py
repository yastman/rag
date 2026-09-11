"""Contracts for the minimal core Compose stack (#2485)."""

from __future__ import annotations

from pathlib import Path

import yaml


CORE_COMPOSE = Path("compose.core.yml")
MAKEFILE = Path("Makefile")
README = Path("README.md")


def test_core_compose_contains_only_qdrant_and_redis() -> None:
    """The minimal stack must stay small enough for native core development."""
    data = yaml.safe_load(CORE_COMPOSE.read_text())

    assert set(data["services"]) == {"qdrant", "redis"}
    assert "core_qdrant_data" in data["volumes"]
    assert "core_redis_data" in data["volumes"]


def test_core_compose_does_not_require_platform_env() -> None:
    """Rendering the minimal stack must not require full-platform secret vars."""
    text = CORE_COMPOSE.read_text()

    forbidden = {
        "POSTGRES_PASSWORD",
        "TELEGRAM_BOT_TOKEN",
        "LANGFUSE_",
        "BGE_M3_ONNX_MODEL_HOST_DIR",
    }
    assert not any(marker in text for marker in forbidden)


def test_makefile_exposes_core_min_and_docker_core_up_targets() -> None:
    """Issue #2485 requires documented make entrypoints (#3379: canonical names only)."""
    import re

    text = MAKEFILE.read_text()

    assert "CORE_MIN_COMPOSE_FILE := -f compose.core.yml" in text
    assert "core-min-up: ## Start minimal core services only (qdrant + redis)" in text
    assert "docker compose $(CORE_MIN_COMPOSE_FILE) up -d" in text
    assert "docker-core-up: operator-env-check ## Start default local compose stack " in text
    # #3379 removed the core-up alias; docker-core-up is the canonical target.
    assert not re.search(r"^core-up:", text, re.MULTILINE)


def test_readme_documents_minimal_and_default_core_profiles() -> None:
    """Users should see the minimal vs broader compose choices up front."""
    import re

    text = README.read_text()

    assert "make core-min-up" in text
    assert "compose.core.yml" in text
    assert "make docker-core-up" in text
    assert not re.search(r"make core-up\b", text)
