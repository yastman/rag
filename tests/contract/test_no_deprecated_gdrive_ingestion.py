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
- Unified ingestion now consumes local files and uses ``FileManifest`` for
  stable file identity. It intentionally has no Google Drive behavior.

Decision: delete the deprecated modules and their dedicated tests. The
local-file unified ingestion surface is the canonical owner for ingestion.
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


def test_deprecated_gdrive_integration_test_deleted() -> None:
    """``tests/integration/test_gdrive_ingestion.py`` imported the deleted API."""
    path = REPO_ROOT / "tests" / "integration" / "test_gdrive_ingestion.py"
    assert not path.exists(), (
        f"{path.relative_to(REPO_ROOT)} still exists; it imports the now-deleted "
        "gdrive_flow API and must be removed or rewritten against unified ingestion."
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


def test_no_stale_metadata_references_to_deleted_gdrive_modules() -> None:
    """Repository metadata must not keep config/fixture references to deleted modules."""
    checked_files = [
        REPO_ROOT / "pyproject.toml",
        REPO_ROOT / "src" / "ingestion" / "README.md",
        REPO_ROOT / "tests" / "data" / "known_duplicate_test_names.json",
    ]
    needles = (
        "src/ingestion/gdrive_indexer.py",
        "src/ingestion/gdrive_flow.py",
        "tests/unit/ingestion/test_gdrive_indexer.py",
        "tests/unit/ingestion/test_gdrive_flow.py",
        "tests/integration/test_gdrive_ingestion.py",
        "src.ingestion.gdrive_indexer",
        "src.ingestion.gdrive_flow",
    )

    violations: list[str] = []
    for path in checked_files:
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle in text:
                violations.append(f"{path.relative_to(REPO_ROOT)} contains {needle!r}")

    assert not violations, (
        "Deleted GDrive ingestion modules/tests still appear in repository "
        "metadata:\n" + "\n".join(f"  {v}" for v in violations)
    )


def test_unified_ingestion_file_manifest_surface_present() -> None:
    """Unified ingestion must retain local-file identity after GDrive removal."""
    manifest_path = REPO_ROOT / "src" / "ingestion" / "unified" / "manifest.py"
    flow_path = REPO_ROOT / "src" / "ingestion" / "unified" / "flow.py"

    manifest_src = manifest_path.read_text(encoding="utf-8")
    assert "class FileManifest:" in manifest_src

    flow_src = flow_path.read_text(encoding="utf-8")
    assert "from src.ingestion.unified.manifest import FileManifest" in flow_src
    assert "_manifest = FileManifest(" in flow_src
