"""Tests for Docker Compose file structure and correctness.

Covers:
- #818: compose.yml/compose.dev.yml/compose.vps.yml structure
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


def test_compose_vps_yml_is_valid_yaml():
    """compose.vps.yml must be parseable and have a services key."""
    data = load_yaml("compose.vps.yml")
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
            f"Service '{name}' in compose.yml has ports — "
            "move to compose.dev.yml or compose.vps.yml override"
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
# #812 — VPS ColBERT rerank enabled
# ---------------------------------------------------------------------------


def test_vps_rerank_provider_is_colbert():
    """compose.vps.yml must enable ColBERT rerank (not 'none')."""
    data = load_yaml("compose.vps.yml")
    bot_env = data["services"]["bot"]["environment"]
    assert bot_env.get("RERANK_PROVIDER") == "colbert", (
        "VPS must use ColBERT rerank — set RERANK_PROVIDER=colbert in compose.vps.yml. "
        "See issue #812."
    )


def test_vps_rerank_candidates_reduced():
    """VPS must use reduced candidates to keep latency acceptable (<= 5)."""
    data = load_yaml("compose.vps.yml")
    bot_env = data["services"]["bot"]["environment"]
    candidates = int(bot_env.get("RERANK_CANDIDATES_MAX", 10))
    assert candidates <= 5, (
        f"VPS RERANK_CANDIDATES_MAX={candidates} — must be <= 5 to keep latency <2s on CPU"
    )


def test_vps_bge_m3_read_only():
    """VPS bge-m3 must run read-only for security hardening."""
    data = load_yaml("compose.vps.yml")
    bge = data["services"].get("bge-m3", {})
    assert bge.get("read_only") is True, "compose.vps.yml bge-m3 must have read_only: true"


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
