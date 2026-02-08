# tests/unit/ingestion/test_unified_manifest.py
"""Tests for unified manifest: content-hash → stable UUID identity."""

import json
from pathlib import Path

import pytest

from src.ingestion.unified.manifest import GDriveManifest, compute_content_hash_from_bytes


class TestComputeContentHash:
    """Test compute_content_hash_from_bytes()."""

    def test_deterministic(self):
        """Same content → same hash."""
        h1 = compute_content_hash_from_bytes(b"hello world")
        h2 = compute_content_hash_from_bytes(b"hello world")
        assert h1 == h2

    def test_different_content_different_hash(self):
        """Different content → different hash."""
        h1 = compute_content_hash_from_bytes(b"hello")
        h2 = compute_content_hash_from_bytes(b"world")
        assert h1 != h2

    def test_returns_16_char_hex(self):
        """Hash is 16-char hex string (SHA-256 prefix)."""
        h = compute_content_hash_from_bytes(b"test")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_bytes(self):
        """Empty input produces a valid hash."""
        h = compute_content_hash_from_bytes(b"")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_unicode_bytes(self):
        """Unicode content encoded to bytes produces valid hash."""
        content = "Кримінальний кодекс України — §42".encode()
        h = compute_content_hash_from_bytes(content)
        assert len(h) == 16
        # Deterministic
        assert h == compute_content_hash_from_bytes(content)

    def test_large_content(self):
        """Large input still produces 16-char hash."""
        content = b"x" * 10_000_000  # 10 MB
        h = compute_content_hash_from_bytes(content)
        assert len(h) == 16


class TestGDriveManifest:
    """Test GDriveManifest identity management."""

    @pytest.fixture
    def manifest_dir(self, tmp_path: Path) -> Path:
        """Provide a temp directory for manifest storage."""
        return tmp_path

    @pytest.fixture
    def manifest(self, manifest_dir: Path) -> GDriveManifest:
        """Create a fresh manifest instance."""
        return GDriveManifest(manifest_dir)

    # --- Load / Save ---

    def test_fresh_manifest_no_file(self, manifest: GDriveManifest):
        """New manifest with no file on disk starts empty."""
        assert manifest._key_to_id == {}
        assert manifest._hash_to_id == {}
        assert manifest._path_to_hash == {}

    def test_save_and_load_roundtrip(self, manifest_dir: Path):
        """Manifest persists to disk and loads back correctly."""
        m1 = GDriveManifest(manifest_dir)
        file_id = m1.get_or_create_id("docs/a.pdf", "hash_aaa")

        m2 = GDriveManifest(manifest_dir)
        assert m2._hash_to_id["hash_aaa"] == file_id
        assert m2._key_to_id["docs/a.pdf:hash_aaa"] == file_id
        assert m2._path_to_hash["docs/a.pdf"] == "hash_aaa"

    def test_load_corrupt_json_starts_fresh(self, manifest_dir: Path):
        """Corrupt JSON on disk → starts fresh without crashing."""
        manifest_path = manifest_dir / ".gdrive_manifest.json"
        manifest_path.write_text("NOT VALID JSON {{{", encoding="utf-8")

        m = GDriveManifest(manifest_dir)
        assert m._key_to_id == {}
        assert m._hash_to_id == {}

    def test_save_atomic_via_tmp(self, manifest_dir: Path):
        """Save uses .tmp → rename for atomic writes."""
        m = GDriveManifest(manifest_dir)
        m.get_or_create_id("a.txt", "hash1")

        manifest_path = manifest_dir / ".gdrive_manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "hash_to_id" in data
        assert "key_to_id" in data
        assert "path_to_hash" in data

    # --- get_or_create_id: 3 identity paths ---

    def test_new_file_generates_id(self, manifest: GDriveManifest):
        """New file (unseen hash + path) generates a fresh file_id."""
        file_id = manifest.get_or_create_id("docs/new.pdf", "hash_new")
        assert isinstance(file_id, str)
        assert len(file_id) == 16  # uuid4().hex[:16]

    def test_exact_match_returns_same_id(self, manifest: GDriveManifest):
        """Same path + same hash → same file_id (exact match)."""
        id1 = manifest.get_or_create_id("docs/a.pdf", "hash_a")
        id2 = manifest.get_or_create_id("docs/a.pdf", "hash_a")
        assert id1 == id2

    def test_renamed_file_reuses_id(self, manifest: GDriveManifest):
        """Same content hash at different path → reuses original file_id (rename-stable)."""
        id_original = manifest.get_or_create_id("old/path.pdf", "hash_content")
        id_renamed = manifest.get_or_create_id("new/path.pdf", "hash_content")
        assert id_original == id_renamed

    def test_different_content_different_id(self, manifest: GDriveManifest):
        """Different content hashes → different file_ids."""
        id1 = manifest.get_or_create_id("docs/a.pdf", "hash_1")
        id2 = manifest.get_or_create_id("docs/b.pdf", "hash_2")
        assert id1 != id2

    def test_same_path_new_content_new_id(self, manifest: GDriveManifest):
        """File at same path but different content → new file_id."""
        id_v1 = manifest.get_or_create_id("docs/a.pdf", "hash_v1")
        id_v2 = manifest.get_or_create_id("docs/a.pdf", "hash_v2")
        assert id_v1 != id_v2

    def test_updates_path_to_hash(self, manifest: GDriveManifest):
        """get_or_create_id updates path_to_hash mapping."""
        manifest.get_or_create_id("docs/a.pdf", "hash_a")
        assert manifest._path_to_hash["docs/a.pdf"] == "hash_a"

    # --- remove ---

    def test_remove_path(self, manifest: GDriveManifest):
        """remove() deletes path_to_hash entry but keeps hash_to_id."""
        file_id = manifest.get_or_create_id("docs/a.pdf", "hash_a")
        manifest.remove("docs/a.pdf")

        assert "docs/a.pdf" not in manifest._path_to_hash
        # hash_to_id preserved for future reuse
        assert manifest._hash_to_id["hash_a"] == file_id

    def test_remove_nonexistent_path_is_noop(self, manifest: GDriveManifest):
        """remove() on unknown path does nothing."""
        manifest.remove("nonexistent.pdf")  # Should not raise

    # --- Migration ---

    def test_migration_backfills_hash_to_id(self, manifest_dir: Path):
        """Legacy manifest (key_to_id only) gets hash_to_id backfilled."""
        legacy_data = {
            "key_to_id": {
                "docs/a.pdf:hash_aaa": "id_aaa",
                "docs/b.pdf:hash_bbb": "id_bbb",
            },
            "hash_to_id": {},
            "path_to_hash": {},
        }
        manifest_path = manifest_dir / ".gdrive_manifest.json"
        manifest_path.write_text(json.dumps(legacy_data), encoding="utf-8")

        m = GDriveManifest(manifest_dir)
        assert m._hash_to_id["hash_aaa"] == "id_aaa"
        assert m._hash_to_id["hash_bbb"] == "id_bbb"

    def test_migration_skipped_when_hash_to_id_exists(self, manifest_dir: Path):
        """If hash_to_id already populated, no migration occurs."""
        data = {
            "key_to_id": {"docs/a.pdf:hash_aaa": "id_legacy"},
            "hash_to_id": {"hash_aaa": "id_current"},
            "path_to_hash": {},
        }
        manifest_path = manifest_dir / ".gdrive_manifest.json"
        manifest_path.write_text(json.dumps(data), encoding="utf-8")

        m = GDriveManifest(manifest_dir)
        # hash_to_id was already populated → no overwrite
        assert m._hash_to_id["hash_aaa"] == "id_current"

    def test_rename_after_reload_still_stable(self, manifest_dir: Path):
        """File identity survives manifest reload + rename."""
        m1 = GDriveManifest(manifest_dir)
        original_id = m1.get_or_create_id("old/name.pdf", "hash_x")

        # Reload from disk (simulates restart)
        m2 = GDriveManifest(manifest_dir)
        renamed_id = m2.get_or_create_id("new/name.pdf", "hash_x")

        assert original_id == renamed_id
