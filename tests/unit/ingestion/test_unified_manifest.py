# tests/unit/ingestion/test_unified_manifest.py
"""Tests for unified manifest: content-hash → stable UUID identity.

Single unit owner for manifest behavior (#3407): identity paths, copy-vs-rename
detection (#1603), scan reconciliation (#3369), and rename stability across
reload. The former AST source contract for copy-detection was absorbed by the
behavioral tests here.
"""

import json
from pathlib import Path

import pytest

from src.ingestion.unified.manifest import GDriveManifest, compute_content_hash_from_bytes


@pytest.fixture
def manifest_dir(tmp_path: Path) -> Path:
    """Provide a temp directory for manifest storage."""
    return tmp_path


@pytest.fixture
def manifest(manifest_dir: Path) -> GDriveManifest:
    """Create a fresh manifest instance."""
    return GDriveManifest(manifest_dir)


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

    # --- Load / Save ---

    def test_fresh_manifest_no_file(self, manifest: GDriveManifest):
        """New manifest with no file on disk starts empty."""
        assert manifest._key_to_id == {}
        assert manifest._hash_to_id == {}
        assert manifest._path_to_hash == {}

    def test_save_and_load_roundtrip(self, manifest_dir: Path):
        """Manifest persists to disk and loads back correctly."""
        m1 = GDriveManifest(manifest_dir)
        file_id = m1.get_or_create_id("docs/a.md", "hash_aaa")

        m2 = GDriveManifest(manifest_dir)
        assert m2._hash_to_id["hash_aaa"] == file_id
        assert m2._key_to_id["docs/a.md:hash_aaa"] == file_id
        assert m2._path_to_hash["docs/a.md"] == "hash_aaa"

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

        manifest_path = manifest_dir / ".file_manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "hash_to_id" in data
        assert "key_to_id" in data
        assert "path_to_hash" in data

    # --- get_or_create_id: 3 identity paths ---

    def test_new_file_generates_id(self, manifest: GDriveManifest):
        """New file (unseen hash + path) generates a fresh file_id."""
        file_id = manifest.get_or_create_id("docs/new.md", "hash_new")
        assert isinstance(file_id, str)
        assert len(file_id) == 16  # uuid4().hex[:16]

    def test_exact_match_returns_same_id(self, manifest: GDriveManifest):
        """Same path + same hash → same file_id (exact match)."""
        id1 = manifest.get_or_create_id("docs/a.md", "hash_a")
        id2 = manifest.get_or_create_id("docs/a.md", "hash_a")
        assert id1 == id2

    def test_renamed_file_reuses_id(self, manifest: GDriveManifest):
        """Same content hash: old path removed, new path appears → reuses file_id (rename-stable).

        Updated for #1603 copy-detection: a rename is only detected when the
        original path is *no longer active* (i.e., ``remove()`` was called).
        """
        id_original = manifest.get_or_create_id("old/path.md", "hash_content")
        # Simulate the file being removed from its original location (rename/move)
        manifest.remove("old/path.md")
        id_renamed = manifest.get_or_create_id("new/path.md", "hash_content")
        assert id_original == id_renamed

    def test_different_content_different_id(self, manifest: GDriveManifest):
        """Different content hashes → different file_ids."""
        id1 = manifest.get_or_create_id("docs/a.md", "hash_1")
        id2 = manifest.get_or_create_id("docs/b.md", "hash_2")
        assert id1 != id2

    def test_same_path_new_content_new_id(self, manifest: GDriveManifest):
        """File at same path but different content → new file_id."""
        id_v1 = manifest.get_or_create_id("docs/a.md", "hash_v1")
        id_v2 = manifest.get_or_create_id("docs/a.md", "hash_v2")
        assert id_v1 != id_v2

    def test_updates_path_to_hash(self, manifest: GDriveManifest):
        """get_or_create_id updates path_to_hash mapping."""
        manifest.get_or_create_id("docs/a.md", "hash_a")
        assert manifest._path_to_hash["docs/a.md"] == "hash_a"

    # --- remove ---

    def test_remove_path(self, manifest: GDriveManifest):
        """remove() deletes path_to_hash entry but keeps hash_to_id."""
        file_id = manifest.get_or_create_id("docs/a.md", "hash_a")
        manifest.remove("docs/a.md")

        assert "docs/a.md" not in manifest._path_to_hash
        # hash_to_id preserved for future reuse
        assert manifest._hash_to_id["hash_a"] == file_id

    def test_remove_nonexistent_path_is_noop(self, manifest: GDriveManifest):
        """remove() on unknown path does nothing."""
        manifest.remove("nonexistent.md")  # Should not raise

    # --- Migration ---

    def test_migration_backfills_hash_to_id(self, manifest_dir: Path):
        """Legacy manifest (key_to_id only) gets hash_to_id backfilled."""
        legacy_data = {
            "key_to_id": {
                "docs/a.md:hash_aaa": "id_aaa",
                "docs/b.md:hash_bbb": "id_bbb",
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
            "key_to_id": {"docs/a.md:hash_aaa": "id_legacy"},
            "hash_to_id": {"hash_aaa": "id_current"},
            "path_to_hash": {},
        }
        manifest_path = manifest_dir / ".gdrive_manifest.json"
        manifest_path.write_text(json.dumps(data), encoding="utf-8")

        m = GDriveManifest(manifest_dir)
        # hash_to_id was already populated → no overwrite
        assert m._hash_to_id["hash_aaa"] == "id_current"

    def test_rename_after_reload_still_stable(self, manifest_dir: Path):
        """File identity survives manifest reload + rename.

        Updated for #1603 copy-detection: ``remove()`` must be called for the
        original path before the new path is registered, to signal a rename.
        """
        m1 = GDriveManifest(manifest_dir)
        original_id = m1.get_or_create_id("old/name.md", "hash_x")
        # Simulate removal of old path before rename appears
        m1.remove("old/name.md")

        # Reload from disk (simulates restart)
        m2 = GDriveManifest(manifest_dir)
        renamed_id = m2.get_or_create_id("new/name.md", "hash_x")

        assert original_id == renamed_id


class TestCopyVsRenameDetection:
    """Copies get distinct file_ids; renames (vanished source path) reuse the old one.

    Merged from the former copy/rename suite (#1603, #3407): a *copy* (both
    paths active) must never collapse into one identity, while a *rename*
    (old path removed) keeps the original file_id.
    """

    def test_same_content_different_paths_get_different_file_ids(
        self, manifest: GDriveManifest
    ) -> None:
        """Two files with identical bytes at different paths are copies.

        Both paths are simultaneously active, so each must receive its own
        file_id. Collapsing them would make deletion/update of one silently
        affect the other.
        """
        HASH = "deadbeef12345678"

        id_a = manifest.get_or_create_id("docs/original.md", HASH)
        id_b = manifest.get_or_create_id("archive/copy.md", HASH)

        assert id_a != id_b, (
            "Two active paths with the same content hash must get different "
            "file_ids (copy case, not rename case)."
        )

    def test_delete_one_copy_doesnt_affect_other(self, manifest: GDriveManifest) -> None:
        """Two copies exist; deleting one must not disturb the other's file_id."""
        HASH = "aabbccdd00112233"

        id_a = manifest.get_or_create_id("root/copy_a.md", HASH)
        id_b = manifest.get_or_create_id("root/copy_b.md", HASH)
        assert id_a != id_b

        manifest.remove("root/copy_a.md")

        id_b_after = manifest.get_or_create_id("root/copy_b.md", HASH)
        assert id_b_after == id_b, "Deleting one copy must not change the other copy's file_id."

    def test_third_copy_after_first_deleted_gets_new_id(self, manifest: GDriveManifest) -> None:
        """Adding a third path while one copy still exists is still a copy."""
        HASH = "112233440aabbccd"

        id_a = manifest.get_or_create_id("dir/file_a.md", HASH)
        id_b = manifest.get_or_create_id("dir/file_b.md", HASH)
        assert id_a != id_b

        manifest.remove("dir/file_a.md")

        # B is still active → C is a copy of B, not a rename
        id_c = manifest.get_or_create_id("dir/file_c.md", HASH)
        assert id_c != id_b, (
            "When at least one path with the same hash is still active, "
            "a new path is a copy and must receive its own file_id."
        )


class TestScanReconciliation:
    """Reconcile tracked paths against the live scan listing (#3369).

    Production ``run_once`` never calls ``remove()`` when a file is renamed:
    the stale path simply stops appearing in the scan. Reconciliation must
    drop those stale entries (and their composite keys) BEFORE identity
    allocation, so the same content at a new path is recognised as a rename
    (identity reuse) rather than a copy (new identity).
    """

    def test_reconcile_stale_path_makes_new_path_a_rename(self, manifest: GDriveManifest) -> None:
        """A.md ingested, then only B.md is scanned → B.md reuses A.md's id."""
        HASH = "0f1e2d3c4b5a6978"

        original_id = manifest.get_or_create_id("A.md", HASH)
        manifest.reconcile_paths({"B.md"})

        assert "A.md" not in manifest._path_to_hash, (
            "Reconciliation must drop the path entry for the vanished file."
        )
        renamed_id = manifest.get_or_create_id("B.md", HASH)
        assert renamed_id == original_id, (
            "After reconciliation removed the stale path, the same content at "
            "the new path is a rename and must reuse the original file_id."
        )

    def test_reconcile_keeps_active_copy_distinct(self, manifest: GDriveManifest) -> None:
        """A.md ingested, then A.md + B.md scanned together → copy gets its own id."""
        HASH = "1a2b3c4d5e6f7081"

        original_id = manifest.get_or_create_id("A.md", HASH)
        manifest.reconcile_paths({"A.md", "B.md"})

        copy_id = manifest.get_or_create_id("B.md", HASH)
        assert copy_id != original_id, (
            "The original path is still active after reconciliation, so the "
            "new path is a copy and must receive a distinct file_id."
        )

    def test_reconcile_prunes_stale_composite_key(self, manifest: GDriveManifest) -> None:
        """A returning old path is a copy, not a composite-key identity hit."""
        HASH = "2b3c4d5e6f708192"

        original_id = manifest.get_or_create_id("A.md", HASH)
        manifest.reconcile_paths({"B.md"})
        renamed_id = manifest.get_or_create_id("B.md", HASH)
        assert renamed_id == original_id

        # A.md comes back (e.g. the user copies B.md over the old name): both
        # paths are now active with the same content, so A.md must be its own
        # record, not silently share B.md's identity via the stale composite.
        returning_id = manifest.get_or_create_id("A.md", HASH)
        assert returning_id != original_id, (
            "A path that returns after reconciliation is a new copy while the "
            "renamed path is still active; the pruned composite key must not "
            "collapse it back onto the reused file_id."
        )

    def test_reconcile_is_idempotent(self, manifest: GDriveManifest) -> None:
        """Reconciling twice with the same listing changes nothing further."""
        HASH = "3c4d5e6f708192a3"

        original_id = manifest.get_or_create_id("A.md", HASH)
        manifest.reconcile_paths({"B.md"})
        renamed_id = manifest.get_or_create_id("B.md", HASH)
        assert renamed_id == original_id

        snapshot = (
            dict(manifest._path_to_hash),
            dict(manifest._key_to_id),
            dict(manifest._hash_to_id),
        )
        manifest.reconcile_paths({"B.md"})
        again = manifest.get_or_create_id("B.md", HASH)

        assert (
            dict(manifest._path_to_hash),
            dict(manifest._key_to_id),
            dict(manifest._hash_to_id),
        ) == snapshot, "A second reconciliation with the same listing is a no-op."
        assert again == original_id, "Identity is stable across reconciliations."

    def test_reconcile_result_survives_reload(self, manifest_dir: Path) -> None:
        """The reconciled rename decision is persisted, not just in-memory."""
        manifest = GDriveManifest(manifest_dir)
        HASH = "4d5e6f708192a3b4"

        original_id = manifest.get_or_create_id("A.md", HASH)
        manifest.reconcile_paths({"B.md"})
        manifest.get_or_create_id("B.md", HASH)

        reloaded = GDriveManifest(manifest_dir)
        assert reloaded.get_or_create_id("B.md", HASH) == original_id, (
            "The rename reuse must survive a manifest reload (process restart)."
        )

    def test_reconcile_repairs_collapsed_ids_for_active_paths(self, manifest_dir: Path) -> None:
        """Historic copy-collapse (two active paths, one id) is repaired.

        Deterministic: the first active path (sorted) keeps the original id,
        later paths are re-minted, and the repair is stable across reloads.
        """
        HASH = "5e6f708192a3b4c5"
        collapsed_id = "aaaaaaaaaaaaaaaa"
        manifest_path = manifest_dir / ".file_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "key_to_id": {
                        "A.md:" + HASH: collapsed_id,
                        "B.md:" + HASH: collapsed_id,
                    },
                    "hash_to_id": {HASH: collapsed_id},
                    "path_to_hash": {"A.md": HASH, "B.md": HASH},
                }
            ),
            encoding="utf-8",
        )

        manifest = GDriveManifest(manifest_dir)
        manifest.reconcile_paths({"A.md", "B.md"})

        id_a = manifest.get_or_create_id("A.md", HASH)
        id_b = manifest.get_or_create_id("B.md", HASH)
        assert id_a == collapsed_id, "The first active path (sorted) keeps the original file_id."
        assert id_b != collapsed_id, (
            "A second active path sharing one file_id is a collapsed copy and "
            "must be re-minted so each path owns its identity again."
        )

        reloaded = GDriveManifest(manifest_dir)
        assert reloaded.get_or_create_id("A.md", HASH) == id_a
        assert reloaded.get_or_create_id("B.md", HASH) == id_b, (
            "The repair must be idempotent across reloads."
        )
