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
    def test_delete_one_copy_doesnt_affect_other(
        self, manifest: GDriveManifest
    ) -> None:
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
        assert id_b_after == id_b, (
            "Deleting one copy must not change the other copy's file_id."
        )

    # ------------------------------------------------------------------
    # RED test 4: determinism — same path+hash always returns the same ID.
    # ------------------------------------------------------------------
    def test_path_aware_file_id_is_deterministic(
        self, manifest: GDriveManifest
    ) -> None:
        """Calling get_or_create_id twice with the same path+hash returns the same ID."""
        HASH = "f0f0f0f0a1a1a1a1"
        PATH = "reports/q1.pdf"

        id1 = manifest.get_or_create_id(PATH, HASH)
        id2 = manifest.get_or_create_id(PATH, HASH)

        assert id1 == id2, (
            "get_or_create_id must be idempotent: same path+hash → same file_id."
        )

    # ------------------------------------------------------------------
    # Bonus: after copy A is removed and the content re-appears at path C,
    # the surviving copy B's id is NOT reused — path C gets a fresh id.
    # (Because B is still active — path C is a new copy of B, not a rename.)
    # ------------------------------------------------------------------
    def test_third_copy_after_first_deleted_gets_new_id(
        self, manifest: GDriveManifest
    ) -> None:
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
