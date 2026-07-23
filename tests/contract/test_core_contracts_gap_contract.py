"""Contract test gap coverage for #3017.

One concrete gap identified by audit:

Qdrant collection schema in ingestion code statically declares all three
vector namespaces: ``dense``, ``bm42``, ``colbert``.

All checks are static (no Docker, no network, no imports of heavy deps).
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Qdrant collection schema declares dense + bm42 + colbert
# ---------------------------------------------------------------------------

_SCHEMA_FILES = [
    REPO_ROOT / "src" / "ingestion" / "unified" / "commands.py",
    REPO_ROOT / "src" / "ingestion" / "indexer.py",
]

_REQUIRED_VECTORS = ("dense", "bm42", "colbert")


def test_qdrant_collection_schema_declares_required_vector_names() -> None:
    """Ingestion code that calls create_collection must declare dense, bm42, colbert.

    Verifies statically that the BGE-M3 full profile schema is wired in the
    ingestion layer, preventing silent schema regression (#3018/#3012).
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
