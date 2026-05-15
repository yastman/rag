"""Regression guards for public repository governance cleanup."""

from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]


def test_apartment_sample_contract_matches_default_path() -> None:
    """Default apartment ingestion path must either exist or docs must not claim it exists."""
    csv_path = ROOT / "data" / "apartments.csv"
    data_readme = (ROOT / "data" / "README.md").read_text(encoding="utf-8")
    ingest_script = (ROOT / "scripts" / "apartments" / "ingest.py").read_text(encoding="utf-8")
    runner = (ROOT / "src" / "ingestion" / "apartments" / "runner.py").read_text(encoding="utf-8")

    assert "data/apartments.csv" in ingest_script
    assert "data/apartments.csv" in runner
    assert csv_path.exists(), "default apartment sample CSV is missing"
    assert "apartments.csv" in data_readme


def test_k8s_ingestion_drive_sync_contract_is_not_silent_empty_pvc() -> None:
    """A base PVC must be paired with an explicit data population contract."""
    deployment = yaml.safe_load(
        (ROOT / "k8s" / "base" / "ingestion" / "deployment.yaml").read_text(encoding="utf-8")
    )
    volumes = deployment["spec"]["template"]["spec"]["volumes"]
    drive_sync = next(v for v in volumes if v["name"] == "drive-sync")

    if "persistentVolumeClaim" not in drive_sync:
        return

    pvc = yaml.safe_load(
        (ROOT / "k8s" / "base" / "ingestion" / "pvc.yaml").read_text(encoding="utf-8")
    )
    annotations = pvc.get("metadata", {}).get("annotations", {})
    readme = (ROOT / "k8s" / "base" / "ingestion" / "README.md").read_text(encoding="utf-8")

    assert annotations.get("rag-fresh.io/data-source") == "externally-provisioned"
    assert "must be pre-populated" in readme
    assert "rclone" in readme


def test_docs_index_does_not_reference_deleted_superpowers_tree() -> None:
    """Docs navigation must not point readers at deleted private planning paths."""
    docs = [
        ROOT / "docs" / "README.md",
        ROOT / "docs" / "engineering" / "docs-maintenance.md",
    ]
    for path in docs:
        text = path.read_text(encoding="utf-8")
        assert "docs/superpowers" not in text
