"""Tests for the run-owned Qdrant collection helpers (#3414).

The #3414 harness owns collections only under the ``rag_e2e_<run-id>``
namespace: names are generated per run/worker, known production collection
names are rejected everywhere, and ownership is enforced before any delete.
"""

import os
import re
from unittest import mock

import pytest

from tests.e2e_core.qdrant_helpers import (
    HarnessSafetyError,
    QdrantTestContext,
    assert_owned_collection_name,
    generate_collection_name,
    production_collection_names,
    should_keep_collection,
)


RUN_ID = "0f1e2d3c4b5a"


class TestGenerateCollectionName:
    """Generated names are run/worker-namespaced and collision resistant."""

    def test_name_uses_rag_e2e_run_and_worker_namespace(self):
        name = generate_collection_name(RUN_ID, "gw0")
        assert name == f"rag_e2e_{RUN_ID}_gw0_{name.rsplit('_', 1)[1]}", name
        assert name.startswith(f"rag_e2e_{RUN_ID}_gw0_")

    def test_name_has_uuid_hex_suffix(self):
        name = generate_collection_name(RUN_ID, "main")
        suffix = name.rsplit("_", 1)[1]
        assert 8 <= len(suffix) <= 32, f"Suffix too short: '{suffix}'"
        try:
            int(suffix, 16)
        except ValueError:
            pytest.fail(f"Suffix '{suffix}' is not valid hex")

    def test_names_are_unique_across_calls(self):
        names = {generate_collection_name(RUN_ID, "gw0") for _ in range(100)}
        assert len(names) == 100

    def test_workers_get_disjoint_prefixes(self):
        first = generate_collection_name(RUN_ID, "gw0")
        second = generate_collection_name(RUN_ID, "gw1")
        assert first.startswith(f"rag_e2e_{RUN_ID}_gw0_")
        assert second.startswith(f"rag_e2e_{RUN_ID}_gw1_")
        assert first != second

    @pytest.mark.parametrize(
        "bad_run_id", ["", "short", "gdrive_documents_bge", "with-dash", "0f1e2d3c4b5azz"]
    )
    def test_invalid_run_id_is_rejected(self, bad_run_id):
        with pytest.raises(HarnessSafetyError):
            generate_collection_name(bad_run_id, "gw0")

    def test_worker_with_invalid_characters_is_rejected(self):
        with pytest.raises(HarnessSafetyError):
            generate_collection_name(RUN_ID, "../escape")


class TestProductionCollectionNames:
    """The known production collection names are blocked for test writes."""

    def test_known_production_names_are_listed(self):
        names = production_collection_names()
        assert "gdrive_documents_bge" in names
        assert "file_documents_bge" in names
        assert "gdrive_documents_bge_scalar" in names
        assert "gdrive_documents_bge_binary" in names

    def test_production_names_cannot_be_owned(self):
        for name in production_collection_names():
            with pytest.raises(HarnessSafetyError):
                assert_owned_collection_name(name, RUN_ID)


class TestAssertOwnedCollectionName:
    """Ownership guard: only rag_e2e_<run-id> names may be created/deleted."""

    @pytest.mark.parametrize(
        "name",
        [
            f"rag_e2e_{RUN_ID}_gw0_deadbeef",
            f"rag_e2e_{RUN_ID}_main_00112233",
        ],
    )
    def test_accepts_run_owned_names(self, name):
        assert assert_owned_collection_name(name, RUN_ID) == name

    @pytest.mark.parametrize(
        "name",
        [
            "gdrive_documents_bge",
            "file_documents_bge",
            "rag_e2e_ffffffffffff_gw0_deadbeef",  # another run's collection
            "e2e_core_1c3c3d15b1dc4c18",  # legacy un-namespaced prefix
            "rag_e2e_",  # unlabeled
            "my_test_collection",
        ],
    )
    def test_rejects_unlabeled_shared_or_foreign_names(self, name):
        with pytest.raises(HarnessSafetyError):
            assert_owned_collection_name(name, RUN_ID)


class TestShouldKeepCollection:
    """Tests for keep/delete policy decision."""

    def test_returns_false_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            assert should_keep_collection() is False

    def test_returns_false_when_e2e_keep_collection_is_zero(self):
        with mock.patch.dict(os.environ, {"E2E_KEEP_COLLECTION": "0"}, clear=True):
            assert should_keep_collection() is False

    @pytest.mark.parametrize("value", ["false", "False", "no", "NO", "off", "Off"])
    def test_returns_false_when_e2e_keep_collection_is_false_like(self, value):
        with mock.patch.dict(os.environ, {"E2E_KEEP_COLLECTION": value}, clear=True):
            assert should_keep_collection() is False

    def test_returns_false_when_e2e_keep_collection_is_empty(self):
        with mock.patch.dict(os.environ, {"E2E_KEEP_COLLECTION": ""}, clear=True):
            assert should_keep_collection() is False

    def test_returns_true_when_e2e_keep_collection_is_one(self):
        with mock.patch.dict(os.environ, {"E2E_KEEP_COLLECTION": "1"}, clear=True):
            assert should_keep_collection() is True


class TestQdrantTestContext:
    """Tests for the QdrantTestContext metadata and creation."""

    def test_context_stores_metadata(self):
        ctx = QdrantTestContext(
            collection_name=f"rag_e2e_{RUN_ID}_gw0_deadbeef",
            qdrant_url="http://127.0.0.1:6333",
            keep=False,
            run_id=RUN_ID,
        )
        assert ctx.collection_name == f"rag_e2e_{RUN_ID}_gw0_deadbeef"
        assert ctx.qdrant_url == "http://127.0.0.1:6333"
        assert ctx.keep is False
        assert ctx.run_id == RUN_ID

    def test_context_has_readable_repr(self):
        ctx = QdrantTestContext(
            collection_name=f"rag_e2e_{RUN_ID}_main_00112233",
            qdrant_url="http://127.0.0.1:6333",
            keep=False,
            run_id=RUN_ID,
        )
        r = repr(ctx)
        assert f"rag_e2e_{RUN_ID}_main_00112233" in r
        assert "keep" in r.lower()


class TestNameFormatContract:
    """The generated name must pass the ownership guard of the same run."""

    def test_generated_name_passes_ownership_guard(self):
        name = generate_collection_name(RUN_ID, "gw1")
        assert assert_owned_collection_name(name, RUN_ID) == name

    def test_name_is_qdrant_safe(self):
        name = generate_collection_name(RUN_ID, "gw1")
        assert re.fullmatch(r"[A-Za-z0-9_-]{1,255}", name), name
