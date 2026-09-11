# tests/unit/ingestion/test_manifest_copy_rename.py
"""TDD tests for copy-vs-rename detection in GDriveManifest.

Issue #1603: unified manifest collapses duplicate-content files across paths.

Problem: get_or_create_id() reuses file_id whenever content_hash was seen
before, regardless of whether the original path is still active. This means
a *copy* (path A still active, path B is new) is treated the same as a
*rename* (path A gone, path B is new), collapsing two distinct source records
into one file_id.

Fix (Option B — copy detection): reuse content_hash identity ONLY when the
old path is no longer active in _path_to_hash. If the original path is still
active, the new path is a copy and must receive a distinct file_id.
"""

import json
from pathlib import Path

import pytest

from src.ingestion.unified.manifest import GDriveManifest


class TestCopyVsRenameDetection:
    """Verify that copies get distinct file_ids and renames reuse the old one."""

    @pytest.fixture
    def manifest(self, tmp_path: Path) -> GDriveManifest:
        return GDriveManifest(tmp_path)

    # ------------------------------------------------------------------
    # RED test 1: copy case — two ACTIVE paths with identical content must
    # get DIFFERENT file_ids.
    # ------------------------------------------------------------------
    def test_same_content_different_paths_get_different_file_ids(
        self, manifest: GDriveManifest
    ) -> None:
        """Two files with identical bytes at different paths are copies.

        Both paths are simultaneously active, so each must receive its own
        file_id. Collapsing them would make deletion/update of one silently
        affect the other.
        """
        HASH = "deadbeef12345678"

        id_a = manifest.get_or_create_id("docs/original.pdf", HASH)
        id_b = manifest.get_or_create_id("archive/copy.pdf", HASH)

        assert id_a != id_b, (
            "Two active paths with the same content hash must get different "
            "file_ids (copy case, not rename case)."
        )

    # ------------------------------------------------------------------
    # RED test 2: rename case — old path removed BEFORE new path appears.
    # Must reuse the original file_id.
    # ------------------------------------------------------------------
    def test_rename_preserves_file_id(self, manifest: GDriveManifest) -> None:
        """File at path A is deleted (removed), then appears at path B.

        Because the original path is no longer active, this is a rename/move.
        The new path should reuse the original file_id for downstream
        deduplication stability.
        """
        HASH = "cafebabe11223344"

        original_id = manifest.get_or_create_id("folder/original.pdf", HASH)
        # Simulate the file being removed from its original location
        manifest.remove("folder/original.pdf")
        # Now the same content appears at a new path (rename/move)
        renamed_id = manifest.get_or_create_id("new_folder/renamed.pdf", HASH)

        assert original_id == renamed_id, (
            "After the original path is removed, the same content hash at a "
            "new path should reuse the original file_id (rename/move case)."
        )

    # ------------------------------------------------------------------
    # RED test 3: delete one copy must not affect the other copy's file_id.
    # ------------------------------------------------------------------
    def test_delete_one_copy_doesnt_affect_other(self, manifest: GDriveManifest) -> None:
        """Two copies exist; deleting one must not disturb the other's file_id.

        After copy A and copy B each have their own distinct file_id, removing
        A from the manifest must leave B's file_id unchanged.
        """
        HASH = "aabbccdd00112233"

        id_a = manifest.get_or_create_id("root/copy_a.pdf", HASH)
        id_b = manifest.get_or_create_id("root/copy_b.pdf", HASH)

        # Verify they differ (copy case)
        assert id_a != id_b

        # Delete copy A
        manifest.remove("root/copy_a.pdf")

        # B's identity must be unchanged
        id_b_after = manifest.get_or_create_id("root/copy_b.pdf", HASH)
        assert id_b_after == id_b, "Deleting one copy must not change the other copy's file_id."

    # ------------------------------------------------------------------
    # RED test 4: determinism — same path+hash always returns the same ID.
    # ------------------------------------------------------------------
    def test_path_aware_file_id_is_deterministic(self, manifest: GDriveManifest) -> None:
        """Calling get_or_create_id twice with the same path+hash returns the same ID."""
        HASH = "f0f0f0f0a1a1a1a1"
        PATH = "reports/q1.pdf"

        id1 = manifest.get_or_create_id(PATH, HASH)
        id2 = manifest.get_or_create_id(PATH, HASH)

        assert id1 == id2, "get_or_create_id must be idempotent: same path+hash → same file_id."

    # ------------------------------------------------------------------
    # Bonus: after copy A is removed and the content re-appears at path C,
    # the surviving copy B's id is NOT reused — path C gets a fresh id.
    # (Because B is still active — path C is a new copy of B, not a rename.)
    # ------------------------------------------------------------------
    def test_third_copy_after_first_deleted_gets_new_id(self, manifest: GDriveManifest) -> None:
        """Adding a third path while one copy still exists is still a copy."""
        HASH = "112233440aabbccd"

        id_a = manifest.get_or_create_id("dir/file_a.pdf", HASH)
        id_b = manifest.get_or_create_id("dir/file_b.pdf", HASH)
        assert id_a != id_b

        # Remove A
        manifest.remove("dir/file_a.pdf")

        # B is still active → C is a copy of B, not a rename
        id_c = manifest.get_or_create_id("dir/file_c.pdf", HASH)
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

    @pytest.fixture
    def manifest_dir(self, tmp_path: Path) -> Path:
        return tmp_path

    @pytest.fixture
    def manifest(self, manifest_dir: Path) -> GDriveManifest:
        return GDriveManifest(manifest_dir)

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
