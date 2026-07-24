"""Regression guards for public repository governance cleanup."""

from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_apartment_sample_contract_matches_default_path() -> None:
    """Default apartment ingestion path must either exist or docs must not claim it exists."""
    csv_path = ROOT / "data" / "apartments.csv"
    ingest_script = (ROOT / "scripts" / "apartments" / "ingest.py").read_text(encoding="utf-8")
    runner = (ROOT / "src" / "ingestion" / "apartments" / "runner.py").read_text(encoding="utf-8")

    assert "data/apartments.csv" in ingest_script
    assert "data/apartments.csv" in runner
    assert csv_path.exists(), "default apartment sample CSV is missing"


def test_docs_index_does_not_reference_deleted_superpowers_tree() -> None:
    """Docs navigation must not point readers at deleted private planning paths."""
    docs = [
        ROOT / "docs" / "README.md",
    ]
    for path in docs:
        text = path.read_text(encoding="utf-8")
        assert "docs/superpowers" not in text
