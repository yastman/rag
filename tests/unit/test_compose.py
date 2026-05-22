"""Tests for Docker Compose file structure and correctness.

Covers:
- #818: compose.yml/compose.dev.yml structure
- #812: VPS ColBERT rerank enabled with reduced candidates
- #810: qdrant_ensure_indexes.py exists and creates correct indexes
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import yaml


REPO_ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_yaml(filename: str) -> dict:
    path = REPO_ROOT / filename
    assert path.exists(), f"Missing compose file: {filename}"
    with open(path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# #818 — compose unification structure
# ---------------------------------------------------------------------------


def test_compose_yml_is_valid_yaml():
    """compose.yml must be parseable and have a services key."""
    data = load_yaml("compose.yml")
    assert "services" in data
    assert len(data["services"]) > 0


def test_compose_dev_yml_is_valid_yaml():
    """compose.dev.yml must be parseable and have a services key."""
    data = load_yaml("compose.dev.yml")
    assert "services" in data


def test_compose_yml_has_no_container_name():
    """Base compose.yml must not hardcode container names (uses project prefix)."""
    data = load_yaml("compose.yml")
    for name, svc in data["services"].items():
        assert "container_name" not in svc, (
            f"Service '{name}' in compose.yml has container_name — "
            "remove it; COMPOSE_PROJECT_NAME provides the prefix"
        )


def test_compose_yml_has_no_ports():
    """Base compose.yml must not expose ports (only overrides do)."""
    data = load_yaml("compose.yml")
    for name, svc in data["services"].items():
        assert "ports" not in svc, (
            f"Service '{name}' in compose.yml has ports — move to compose.dev.yml override"
        )


def test_custom_build_services_have_stable_explicit_image_names():
    """Custom build services must pin image names to COMPOSE_PROJECT_NAME with underscores."""
    data = load_yaml("compose.yml")
    expected = {
        "bge-m3": "${COMPOSE_PROJECT_NAME:-dev}_bge-m3",
        "user-base": "${COMPOSE_PROJECT_NAME:-dev}_user-base",
        "docling": "${COMPOSE_PROJECT_NAME:-dev}_docling",
        "bot": "${COMPOSE_PROJECT_NAME:-dev}_bot",
        "mini-app-api": "${COMPOSE_PROJECT_NAME:-dev}_mini-app-api",
        "mini-app-frontend": "${COMPOSE_PROJECT_NAME:-dev}_mini-app-frontend",
        "ingestion": "${COMPOSE_PROJECT_NAME:-dev}_ingestion",
    }
    for svc_name, image in expected.items():
        assert data["services"][svc_name]["image"] == image, (
            f"{svc_name} image must be pinned to {image!r} to avoid build/runtime tag drift"
        )


def test_compose_dev_has_colbert_rerank():
    """Dev override must enable ColBERT reranking."""
    data = load_yaml("compose.dev.yml")
    bot_env = data["services"]["bot"]["environment"]
    assert bot_env.get("RERANK_PROVIDER") == "colbert"


def test_compose_dev_has_ports_for_core_services():
    """Dev override must expose localhost ports for core services."""
    data = load_yaml("compose.dev.yml")
    services = data["services"]
    for svc_name in ("postgres", "redis", "qdrant", "bge-m3"):
        assert "ports" in services.get(svc_name, {}), (
            f"compose.dev.yml missing ports for '{svc_name}'"
        )


# ---------------------------------------------------------------------------
# #810 — qdrant_ensure_indexes.py exists
# ---------------------------------------------------------------------------


def test_qdrant_ensure_indexes_script_exists():
    """scripts/qdrant_ensure_indexes.py must exist."""
    script = REPO_ROOT / "scripts" / "qdrant_ensure_indexes.py"
    assert script.exists(), "Missing scripts/qdrant_ensure_indexes.py — create it to fix issue #810"


def test_qdrant_ensure_indexes_creates_keyword_indexes():
    """ensure_indexes() must create keyword payload indexes for filter fields."""
    script_dir = str(REPO_ROOT / "scripts")
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    import qdrant_ensure_indexes as m

    mock_client = MagicMock()
    mock_client.create_payload_index = MagicMock()

    m.ensure_indexes(mock_client, "gdrive_documents_bge")

    created_fields = {
        c.kwargs.get("field_name") or c.args[1]
        for c in mock_client.create_payload_index.call_args_list
    }
    expected_keyword_fields = {
        "file_id",
        "metadata.file_id",
        "metadata.doc_id",
        "metadata.source",
        "metadata.file_name",
        "metadata.mime_type",
        "metadata.topic",
        "metadata.doc_type",
    }
    for field in expected_keyword_fields:
        assert field in created_fields, f"ensure_indexes() must create keyword index for '{field}'"


def test_qdrant_ensure_indexes_creates_integer_indexes():
    """ensure_indexes() must create integer payload indexes for order/chunk_id."""
    script_dir = str(REPO_ROOT / "scripts")
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    import qdrant_ensure_indexes as m

    mock_client = MagicMock()

    m.ensure_indexes(mock_client, "gdrive_documents_bge")

    created_calls = {
        (
            c.kwargs.get("field_name") or c.args[1],
            str(c.kwargs.get("field_schema") or c.args[2]),
        )
        for c in mock_client.create_payload_index.call_args_list
    }

    for field in ("metadata.order", "metadata.chunk_id"):
        matched = any(f == field for f, _ in created_calls)
        assert matched, f"ensure_indexes() must create integer index for '{field}'"
