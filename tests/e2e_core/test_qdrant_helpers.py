"""Tests for e2e_core Qdrant ephemeral collection helper.

These tests verify unique name generation and keep/delete policy without
requiring a live Qdrant instance.
"""

import os
from unittest import mock

import pytest

from tests.e2e_core.qdrant_helpers import (
    QdrantTestContext,
    generate_collection_name,
    should_keep_collection,
)


class TestGenerateCollectionName:
    """Tests for unique collection name generation."""

    def test_generates_name_with_e2e_core_prefix(self):
        """Generated name must start with e2e_core_ prefix."""
        name = generate_collection_name()
        assert name.startswith("e2e_core_"), f"Expected e2e_core_ prefix, got '{name}'"

    def test_generates_unique_names(self):
        """Generated names must be unique across calls."""
        names = {generate_collection_name() for _ in range(100)}
        assert len(names) == 100, f"Expected 100 unique names, got {len(names)} duplicates"

    def test_name_contains_uuid_hex_substring(self):
        """Generated name must contain a collision-resistant hex suffix."""
        name = generate_collection_name()
        # The name should have e2e_core_ followed by at least 8 hex chars
        suffix = name[len("e2e_core_") :]
        assert len(suffix) >= 8, f"Suffix too short: '{suffix}'"
        try:
            int(suffix, 16)
        except ValueError:
            pytest.fail(f"Suffix '{suffix}' is not valid hex")

    def test_name_format_is_stable(self):
        """Generated names must follow a stable format: e2e_core_ plus hex."""
        name = generate_collection_name()
        # Format: e2e_core_<hex of at least 8 chars>
        assert name.startswith("e2e_core_")
        suffix = name[len("e2e_core_") :]
        assert suffix.isalnum(), f"Suffix must be alphanumeric: '{suffix}'"
        # Verify it's lowercase hex
        assert all(c in "0123456789abcdef" for c in suffix.lower())


class TestShouldKeepCollection:
    """Tests for keep/delete policy decision."""

    def test_returns_false_by_default(self):
        """When E2E_KEEP_COLLECTION is not set, should return False."""
        with mock.patch.dict(os.environ, {}, clear=True):
            assert should_keep_collection() is False

    def test_returns_false_when_e2e_keep_collection_is_zero(self):
        """E2E_KEEP_COLLECTION=0 should be treated as False."""
        with mock.patch.dict(os.environ, {"E2E_KEEP_COLLECTION": "0"}, clear=True):
            assert should_keep_collection() is False

    def test_returns_false_when_e2e_keep_collection_is_empty(self):
        """E2E_KEEP_COLLECTION='' should be treated as False."""
        with mock.patch.dict(os.environ, {"E2E_KEEP_COLLECTION": ""}, clear=True):
            assert should_keep_collection() is False

    def test_returns_true_when_e2e_keep_collection_is_one(self):
        """E2E_KEEP_COLLECTION=1 should be treated as True."""
        with mock.patch.dict(os.environ, {"E2E_KEEP_COLLECTION": "1"}, clear=True):
            assert should_keep_collection() is True

    def test_returns_true_when_e2e_keep_collection_is_truthy(self):
        """E2E_KEEP_COLLECTION with non-zero truthy value should return True."""
        with mock.patch.dict(os.environ, {"E2E_KEEP_COLLECTION": "true"}, clear=True):
            assert should_keep_collection() is True


class TestQdrantTestContext:
    """Tests for the QdrantTestContext metadata and creation."""

    def test_context_stores_metadata(self):
        """QdrantTestContext must expose collection_name, qdrant_url, and keep flag."""
        ctx = QdrantTestContext(
            collection_name="e2e_core_test123",
            qdrant_url="http://qdrant:6333",
            keep=False,
        )
        assert ctx.collection_name == "e2e_core_test123"
        assert ctx.qdrant_url == "http://qdrant:6333"
        assert ctx.keep is False

    def test_context_keep_true(self):
        """QdrantTestContext must support keep=True."""
        ctx = QdrantTestContext(
            collection_name="e2e_core_abc123",
            qdrant_url="http://localhost:6333",
            keep=True,
        )
        assert ctx.keep is True

    def test_context_has_readable_repr(self):
        """QdrantTestContext repr must include collection_name, url, and keep."""
        ctx = QdrantTestContext(
            collection_name="e2e_core_abc789",
            qdrant_url="http://localhost:6333",
            keep=False,
        )
        r = repr(ctx)
        assert "e2e_core_abc789" in r
        assert "http://localhost:6333" in r
        assert "keep" in r.lower()
