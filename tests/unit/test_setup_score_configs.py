"""Tests for scripts/setup_score_configs.py (TDD red-green-refactor)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock


def _load_module():
    """Load setup_score_configs as a module without executing main()."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "setup_score_configs.py"
    spec = importlib.util.spec_from_file_location("setup_score_configs", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---- SCORE_CONFIGS structure tests ----

EXPECTED_CONFIG_NAMES = {
    "user_feedback",
    "user_feedback_reason",
    "implicit_retry",
    "judge_faithfulness",
    "judge_answer_relevance",
    "judge_context_relevance",
    "latency_total_ms",
    "confidence_score",
}


def test_score_configs_has_all_required_names():
    module = _load_module()
    names = {cfg["name"] for cfg in module.SCORE_CONFIGS}
    assert names == EXPECTED_CONFIG_NAMES


def test_user_feedback_is_numeric_0_to_1():
    module = _load_module()
    cfg = next(c for c in module.SCORE_CONFIGS if c["name"] == "user_feedback")
    assert cfg["data_type"] == "NUMERIC"
    assert cfg["min_value"] == 0.0
    assert cfg["max_value"] == 1.0


def test_user_feedback_reason_is_categorical_with_6_categories():
    module = _load_module()
    cfg = next(c for c in module.SCORE_CONFIGS if c["name"] == "user_feedback_reason")
    assert cfg["data_type"] == "CATEGORICAL"
    assert len(cfg["categories"]) == 6
    for cat in cfg["categories"]:
        assert "label" in cat
        assert "value" in cat


def test_implicit_retry_is_boolean():
    module = _load_module()
    cfg = next(c for c in module.SCORE_CONFIGS if c["name"] == "implicit_retry")
    assert cfg["data_type"] == "BOOLEAN"


def test_judge_scores_are_numeric_0_to_1():
    module = _load_module()
    judge_names = {"judge_faithfulness", "judge_answer_relevance", "judge_context_relevance"}
    for cfg in module.SCORE_CONFIGS:
        if cfg["name"] in judge_names:
            assert cfg["data_type"] == "NUMERIC"
            assert cfg["min_value"] == 0.0
            assert cfg["max_value"] == 1.0


def test_latency_total_ms_is_numeric_no_range():
    module = _load_module()
    cfg = next(c for c in module.SCORE_CONFIGS if c["name"] == "latency_total_ms")
    assert cfg["data_type"] == "NUMERIC"
    assert cfg.get("min_value") is None
    assert cfg.get("max_value") is None


def test_confidence_score_is_numeric_0_to_1():
    module = _load_module()
    cfg = next(c for c in module.SCORE_CONFIGS if c["name"] == "confidence_score")
    assert cfg["data_type"] == "NUMERIC"
    assert cfg["min_value"] == 0.0
    assert cfg["max_value"] == 1.0


# ---- get_existing_configs() tests ----


def test_get_existing_configs_returns_name_id_mapping():
    module = _load_module()
    mock_item = MagicMock(spec=["name", "id", "is_archived"])
    mock_item.name = "user_feedback"
    mock_item.id = "uuid-123"
    mock_item.is_archived = False

    mock_api = MagicMock()
    mock_api.score_configs.get.return_value.data = [mock_item]

    result = module.get_existing_configs(mock_api)
    assert result == {"user_feedback": "uuid-123"}


def test_get_existing_configs_excludes_archived():
    module = _load_module()
    mock_item = MagicMock(spec=["name", "id", "is_archived"])
    mock_item.name = "old_config"
    mock_item.id = "uuid-old"
    mock_item.is_archived = True

    mock_api = MagicMock()
    mock_api.score_configs.get.return_value.data = [mock_item]

    result = module.get_existing_configs(mock_api)
    assert result == {}


def test_get_existing_configs_empty_when_no_configs():
    module = _load_module()
    mock_api = MagicMock()
    mock_api.score_configs.get.return_value.data = []

    result = module.get_existing_configs(mock_api)
    assert result == {}


# ---- setup_score_configs() tests ----


def test_setup_score_configs_creates_all_when_none_exist():
    module = _load_module()
    mock_api = MagicMock()
    mock_api.score_configs.get.return_value.data = []

    created = MagicMock()
    created.id = "new-id"
    mock_api.score_configs.create.return_value = created

    result = module.setup_score_configs(mock_api)

    assert mock_api.score_configs.create.call_count == len(module.SCORE_CONFIGS)
    assert len(result) == len(module.SCORE_CONFIGS)


def test_setup_score_configs_skips_existing():
    module = _load_module()
    existing_data = []
    for cfg in module.SCORE_CONFIGS:
        item = MagicMock(spec=["name", "id", "is_archived"])
        item.name = cfg["name"]
        item.id = f"id-{cfg['name']}"
        item.is_archived = False
        existing_data.append(item)

    mock_api = MagicMock()
    mock_api.score_configs.get.return_value.data = existing_data

    result = module.setup_score_configs(mock_api)

    mock_api.score_configs.create.assert_not_called()
    assert len(result) == len(module.SCORE_CONFIGS)


def test_setup_score_configs_creates_only_missing():
    module = _load_module()
    existing = MagicMock(spec=["name", "id", "is_archived"])
    existing.name = "user_feedback"
    existing.id = "existing-id"
    existing.is_archived = False

    mock_api = MagicMock()
    mock_api.score_configs.get.return_value.data = [existing]

    created = MagicMock()
    created.id = "new-id"
    mock_api.score_configs.create.return_value = created

    result = module.setup_score_configs(mock_api)

    assert mock_api.score_configs.create.call_count == len(module.SCORE_CONFIGS) - 1
    assert result["user_feedback"] == "existing-id"
