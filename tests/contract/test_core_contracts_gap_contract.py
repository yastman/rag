"""Contract test gap coverage for #3017.

Two concrete gaps identified by audit:

1. ``docs/architecture/STRUCTURE.md`` exists and references the active layers
   (src/core, src/runtime, src/adapters, src/ingestion).
2. The authoritative Qdrant collection setup statically declares all three
   vector namespaces: ``dense``, ``bm42``, ``colbert``.

All checks are static (no Docker, no network, no imports of heavy deps).
"""

from __future__ import annotations

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
# 2. Qdrant collection schema declares dense + bm42 + colbert
# ---------------------------------------------------------------------------

_SCHEMA_FILES = [REPO_ROOT / "scripts" / "setup_qdrant_collection.py"]

_REQUIRED_VECTORS = ("dense", "bm42", "colbert")


def test_qdrant_collection_schema_declares_required_vector_names() -> None:
    """Authoritative collection setup must declare dense, bm42, and colbert.

    Verifies statically that the BGE-M3 full profile schema is wired into the
    setup used for local and deployed collections (#3018/#3012).
    """
    inspected = 0
    for schema_file in _SCHEMA_FILES:
        if not schema_file.is_file():
            continue
        content = schema_file.read_text(encoding="utf-8")
        if "create_collection" not in content:
            continue
        inspected += 1
        missing = [v for v in _REQUIRED_VECTORS if f'"{v}"' not in content]
        assert not missing, (
            f"{schema_file.relative_to(REPO_ROOT)}: create_collection call is missing "
            f"vector name(s): {missing}. "
            "The bge_m3_full schema requires dense, bm42, and colbert (#3018)."
        )
    assert inspected > 0, (
        "no schema file with create_collection was found — "
        f"searched: {[str(f.relative_to(REPO_ROOT)) for f in _SCHEMA_FILES]}. "
        "Update _SCHEMA_FILES to point at the file that calls create_collection (#3054)."
    )
