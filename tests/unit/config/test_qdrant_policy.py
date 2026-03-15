"""Tests for shared Qdrant collection policy helpers."""

from src.config.qdrant_policy import resolve_collection_name


def test_resolve_collection_name_off_mode():
    assert resolve_collection_name("docs", "off") == "docs"


def test_resolve_collection_name_scalar_mode():
    assert resolve_collection_name("docs", "scalar") == "docs_scalar"


def test_resolve_collection_name_binary_mode():
    assert resolve_collection_name("docs", "binary") == "docs_binary"


def test_resolve_collection_name_strips_existing_suffix():
    assert resolve_collection_name("docs_scalar", "binary") == "docs_binary"
