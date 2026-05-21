# tests/contract/test_no_deprecated_gdrive_ingestion.py
"""Contract: deprecated GDrive ingestion modules and their orphaned tests must
be absent from the repository.

Closes #1793.

Evidence from the audit:
- ``src/ingestion/gdrive_indexer.py`` was marked DEPRECATED: Use unified
  ingestion pipeline instead (``src.ingestion.unified``).
- ``src/ingestion/gdrive_flow.py`` — same deprecation notice.
- Both modules depended on ``voyageai`` being present. After #1773 made
  ``voyageai`` an optional extra, the tests were collection-breaking in the
  default environment and were guarded with ``pytest.importorskip("voyageai")``.
- The unified ingestion pipeline (``src.ingestion.unified``) already provides
  equivalent GDrive coverage via ``GDriveManifest`` + ``unified_gdrive_export``.
  Keeping two surfaces active creates maintenance hazard and keeps Voyage in
  scope for the default collection path.

Decision: delete the deprecated modules and their dedicated tests.
The unified ingestion surface (``src.ingestion.unified``) is the canonical owner
for any future GDrive behavior.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_deprecated_gdrive_indexer_module_deleted() -> None:
    """``src/ingestion/gdrive_indexer.py`` must be absent."""
    path = REPO_ROOT / "src" / "ingestion" / "gdrive_indexer.py"
    assert not path.exists(), (
        f"{path.relative_to(REPO_ROOT)} still exists; it was marked DEPRECATED "
        "(use src.ingestion.unified instead) and must be removed."
    )


def test_deprecated_gdrive_flow_module_deleted() -> None:
    """``src/ingestion/gdrive_flow.py`` must be absent."""
    path = REPO_ROOT / "src" / "ingestion" / "gdrive_flow.py"
    assert not path.exists(), (
        f"{path.relative_to(REPO_ROOT)} still exists; it was marked DEPRECATED "
        "(use src.ingestion.unified instead) and must be removed."
    )


def test_deprecated_gdrive_indexer_test_deleted() -> None:
    """``tests/unit/ingestion/test_gdrive_indexer.py`` must be absent."""
    path = REPO_ROOT / "tests" / "unit" / "ingestion" / "test_gdrive_indexer.py"
    assert not path.exists(), (
        f"{path.relative_to(REPO_ROOT)} still exists; it was the dedicated test for "
        "the now-deleted gdrive_indexer deprecated module and must be removed."
    )


def test_deprecated_gdrive_flow_test_deleted() -> None:
    """``tests/unit/ingestion/test_gdrive_flow.py`` must be absent."""
    path = REPO_ROOT / "tests" / "unit" / "ingestion" / "test_gdrive_flow.py"
    assert not path.exists(), (
        f"{path.relative_to(REPO_ROOT)} still exists; it was the dedicated test for "
        "the now-deleted gdrive_flow deprecated module and must be removed."
    )


def test_no_runtime_import_of_deprecated_gdrive_modules() -> None:
    """No non-test module under ``src/`` or ``telegram_bot/`` may import the
    deleted deprecated GDrive modules.

    This guard catches accidental re-introduction.
    """
    import re

    deprecated_import_pattern = re.compile(
        r"from\s+src\.ingestion\.(?:gdrive_indexer|gdrive_flow)\b"
        r"|import\s+src\.ingestion\.(?:gdrive_indexer|gdrive_flow)\b"
    )

    violations = []
    for src_root in ("src", "telegram_bot"):
        for py_file in (REPO_ROOT / src_root).rglob("*.py"):
            # Skip test files — they have their own deletion contracts above.
            if "test_" in py_file.name:
                continue
            text = py_file.read_text(encoding="utf-8")
            if deprecated_import_pattern.search(text):
                violations.append(str(py_file.relative_to(REPO_ROOT)))

    assert not violations, (
        "The following runtime modules import deleted deprecated GDrive "
        "ingestion modules:\n" + "\n".join(f"  {v}" for v in violations)
    )


def test_unified_ingestion_gdrive_surface_present() -> None:
    """The unified ingestion pipeline must retain GDrive coverage so removal
    of the deprecated modules does not reduce functional scope."""
    manifest_path = REPO_ROOT / "src" / "ingestion" / "unified" / "manifest.py"
    flow_path = REPO_ROOT / "src" / "ingestion" / "unified" / "flow.py"

    assert manifest_path.exists(), (
        "src/ingestion/unified/manifest.py missing — unified GDriveManifest "
        "surface is gone. Do not remove it."
    )
    assert flow_path.exists(), (
        "src/ingestion/unified/flow.py missing — unified GDrive export is gone."
    )

    manifest_src = manifest_path.read_text(encoding="utf-8")
    assert "GDriveManifest" in manifest_src, (
        "GDriveManifest class was removed from unified manifest.py."
    )

    flow_src = flow_path.read_text(encoding="utf-8")
    assert "gdrive" in flow_src.lower(), (
        "GDrive support seems absent from unified/flow.py."
    )
