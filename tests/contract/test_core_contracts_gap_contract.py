"""Contract test gap coverage for #3017.

Three concrete gaps identified by audit:

1. ``docs/architecture/STRUCTURE.md`` exists and references the active layers
   (src/core, src/runtime, src/adapters, src/ingestion).
2. ``.env.example`` contains ``RETRIEVAL_PROFILE=bge_m3_full`` (the naming
   anchor documented in README and #3018).
3. Qdrant collection schema in ingestion code statically declares all three
   vector namespaces: ``dense``, ``bm42``, ``colbert``.

All checks are static (no Docker, no network, no imports of heavy deps).
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# 1. STRUCTURE.md exists and references active layers
# ---------------------------------------------------------------------------

STRUCTURE_MD = REPO_ROOT / "docs" / "architecture" / "STRUCTURE.md"

_REQUIRED_LAYERS = ("src/core", "src/runtime", "src/adapters", "src/ingestion")


def test_architecture_structure_md_exists() -> None:
    """docs/architecture/STRUCTURE.md must exist (#3019)."""
    assert STRUCTURE_MD.is_file(), (
        "docs/architecture/STRUCTURE.md is missing. "
        "Create it as the canonical module ownership map (#3019)."
    )


def test_architecture_structure_md_references_active_layers() -> None:
    """STRUCTURE.md must mention all four active layers."""
    assert STRUCTURE_MD.is_file(), "docs/architecture/STRUCTURE.md missing — see previous test."
    content = STRUCTURE_MD.read_text(encoding="utf-8")
    missing = [layer for layer in _REQUIRED_LAYERS if layer not in content]
    assert not missing, (
        f"docs/architecture/STRUCTURE.md does not reference active layers: {missing}. "
        "Keep the structure map in sync with the active directory layout."
    )


# ---------------------------------------------------------------------------
# 2. .env.example contains RETRIEVAL_PROFILE=bge_m3_full
# ---------------------------------------------------------------------------

ENV_EXAMPLE = REPO_ROOT / ".env.example"


def test_env_example_retrieval_profile_is_bge_m3_full() -> None:
    """``RETRIEVAL_PROFILE=bge_m3_full`` must be the value in .env.example (#3018).

    This is the naming anchor for the local BGE-M3 full-output retrieval path.
    The env completeness test checks presence/absence; this test pins the value.
    """
    assert ENV_EXAMPLE.is_file(), ".env.example must exist."
    content = ENV_EXAMPLE.read_text(encoding="utf-8")
    match = re.search(r"^RETRIEVAL_PROFILE\s*=\s*(\S+)", content, re.MULTILINE)
    assert match is not None, (
        "RETRIEVAL_PROFILE is not set in .env.example. Add: RETRIEVAL_PROFILE=bge_m3_full  (#3018)"
    )
    assert match.group(1) == "bge_m3_full", (
        f"RETRIEVAL_PROFILE must be 'bge_m3_full' in .env.example, got '{match.group(1)}'. "
        "This is the canonical retrieval profile for the local BGE-M3 stack (#3018)."
    )


# ---------------------------------------------------------------------------
# 3. Qdrant collection schema declares dense + bm42 + colbert
# ---------------------------------------------------------------------------

_SCHEMA_FILES = [
    REPO_ROOT / "src" / "ingestion" / "indexer.py",
    REPO_ROOT / "src" / "ingestion" / "unified" / "cli.py",
]

_REQUIRED_VECTORS = ("dense", "bm42", "colbert")


def test_qdrant_collection_schema_declares_required_vector_names() -> None:
    """Ingestion code that calls create_collection must declare dense, bm42, colbert.

    Verifies statically that the BGE-M3 full profile schema is wired in the
    ingestion layer, preventing silent schema regression (#3018/#3012).
    """
    for schema_file in _SCHEMA_FILES:
        if not schema_file.is_file():
            continue
        content = schema_file.read_text(encoding="utf-8")
        if "create_collection" not in content:
            continue
        missing = [v for v in _REQUIRED_VECTORS if f'"{v}"' not in content]
        assert not missing, (
            f"{schema_file.relative_to(REPO_ROOT)}: create_collection call is missing "
            f"vector name(s): {missing}. "
            "The bge_m3_full schema requires dense, bm42, and colbert (#3018)."
        )
