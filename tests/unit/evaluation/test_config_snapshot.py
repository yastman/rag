"""Unit tests for src/evaluation/config_snapshot.py."""

import json

import pytest

from src.evaluation.config_snapshot import (
    CONFIG_SNAPSHOT,
    get_config_hash,
    get_config_summary,
    validate_config,
)


class TestGetConfigHash:
    def test_returns_12_char_hex_string(self):
        result = get_config_hash()
        assert isinstance(result, str)
        assert len(result) == 12
        assert all(c in "0123456789abcdef" for c in result)

    def test_is_deterministic(self):
        h1 = get_config_hash()
        h2 = get_config_hash()
        assert h1 == h2

    def test_changes_when_config_changes(self):
        original = CONFIG_SNAPSHOT["metadata"]["version"]
        try:
            CONFIG_SNAPSHOT["metadata"]["version"] = "99.99.99"
            h1 = get_config_hash()
            CONFIG_SNAPSHOT["metadata"]["version"] = "0.0.0"
            h2 = get_config_hash()
            assert h1 != h2
        finally:
            CONFIG_SNAPSHOT["metadata"]["version"] = original


class TestGetConfigSummary:
    def test_returns_dict_with_expected_keys(self):
        summary = get_config_summary()
        assert isinstance(summary, dict)
        for key in ("version", "date", "config_hash", "models", "collection", "best_engine"):
            assert key in summary, f"Missing key: {key}"

    def test_models_contains_embedder_and_dim(self):
        summary = get_config_summary()
        assert "embedder" in summary["models"]
        assert "dense_dim" in summary["models"]

    def test_collection_contains_name_and_points(self):
        summary = get_config_summary()
        assert "name" in summary["collection"]
        assert "points" in summary["collection"]

    def test_best_engine_has_expected_name(self):
        summary = get_config_summary()
        assert summary["best_engine"]["name"] == "dbsf_colbert"


class TestValidateConfig:
    def test_validates_correct_config(self):
        assert validate_config() is True

    def test_raises_on_missing_key(self):
        saved = CONFIG_SNAPSHOT.pop("metadata", None)
        try:
            with pytest.raises(ValueError, match="Missing required config key: metadata"):
                validate_config()
        finally:
            if saved is not None:
                CONFIG_SNAPSHOT["metadata"] = saved

    def test_raises_on_negative_points_count(self):
        original = CONFIG_SNAPSHOT["collection"]["points_count"]
        try:
            CONFIG_SNAPSHOT["collection"]["points_count"] = 0
            with pytest.raises(ValueError, match="points_count must be positive"):
                validate_config()
        finally:
            CONFIG_SNAPSHOT["collection"]["points_count"] = original

    def test_raises_on_zero_total_queries(self):
        original = CONFIG_SNAPSHOT["evaluation"]["total_queries"]
        try:
            CONFIG_SNAPSHOT["evaluation"]["total_queries"] = 0
            with pytest.raises(ValueError, match="Total queries must be positive"):
                validate_config()
        finally:
            CONFIG_SNAPSHOT["evaluation"]["total_queries"] = original


def test_config_snapshot_is_valid_json():
    json_str = json.dumps(CONFIG_SNAPSHOT, sort_keys=True)
    assert json.loads(json_str) == CONFIG_SNAPSHOT
