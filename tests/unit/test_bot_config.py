"""Tests for BotConfig quantization settings."""

import os
from unittest.mock import patch

from telegram_bot.config import BotConfig


def _config_from_env(
    *,
    overrides: dict[str, str] | None = None,
    drop_keys: set[str] | None = None,
) -> BotConfig:
    """Create BotConfig from a patched environment snapshot."""
    test_env = os.environ.copy()
    for key in drop_keys or set():
        test_env.pop(key, None)
    if overrides:
        test_env.update(overrides)

    with patch.dict(os.environ, test_env, clear=True):
        return BotConfig(_env_file=None)


class TestBotConfigQuantization:
    """Tests for BotConfig quantization environment variable settings."""

    def test_quantization_defaults(self):
        """Test default quantization values when no environment variables set."""
        config = _config_from_env(
            drop_keys={
                "QDRANT_USE_QUANTIZATION",
                "QDRANT_QUANTIZATION_RESCORE",
                "QDRANT_QUANTIZATION_OVERSAMPLING",
                "QDRANT_QUANTIZATION_ALWAYS_RAM",
            }
        )

        assert config.qdrant_use_quantization is True
        assert config.qdrant_quantization_rescore is True
        assert config.qdrant_quantization_oversampling == 2.0
        assert config.qdrant_quantization_always_ram is True

    def test_quantization_from_env_all_enabled(self):
        """Test reading all quantization values from environment variables."""
        config = _config_from_env(
            overrides={
                "QDRANT_USE_QUANTIZATION": "true",
                "QDRANT_QUANTIZATION_RESCORE": "true",
                "QDRANT_QUANTIZATION_OVERSAMPLING": "3.5",
                "QDRANT_QUANTIZATION_ALWAYS_RAM": "true",
            }
        )

        assert config.qdrant_use_quantization is True
        assert config.qdrant_quantization_rescore is True
        assert config.qdrant_quantization_oversampling == 3.5
        assert config.qdrant_quantization_always_ram is True

    def test_quantization_from_env_all_disabled(self):
        """Test reading disabled quantization values from environment variables."""
        config = _config_from_env(
            overrides={
                "QDRANT_USE_QUANTIZATION": "false",
                "QDRANT_QUANTIZATION_RESCORE": "false",
                "QDRANT_QUANTIZATION_OVERSAMPLING": "1.0",
                "QDRANT_QUANTIZATION_ALWAYS_RAM": "false",
            }
        )

        assert config.qdrant_use_quantization is False
        assert config.qdrant_quantization_rescore is False
        assert config.qdrant_quantization_oversampling == 1.0
        assert config.qdrant_quantization_always_ram is False

    def test_quantization_oversampling_float_parsing(self):
        """Test that oversampling correctly parses various float values."""
        test_cases = [
            ("1.0", 1.0),
            ("2.5", 2.5),
            ("4.0", 4.0),
            ("0.5", 0.5),
        ]

        for env_value, expected in test_cases:
            config = _config_from_env(overrides={"QDRANT_QUANTIZATION_OVERSAMPLING": env_value})
            assert config.qdrant_quantization_oversampling == expected, (
                f"Expected {expected} for env value '{env_value}'"
            )

    def test_quantization_boolean_case_insensitive(self):
        """Test that boolean parsing is case insensitive."""
        true_values = ["true", "True", "TRUE", "TrUe"]
        for val in true_values:
            config = _config_from_env(overrides={"QDRANT_USE_QUANTIZATION": val})
            assert config.qdrant_use_quantization is True, f"Expected True for '{val}'"

        false_values = ["false", "False", "FALSE", "FaLsE"]
        for val in false_values:
            config = _config_from_env(overrides={"QDRANT_USE_QUANTIZATION": val})
            assert config.qdrant_use_quantization is False, f"Expected False for '{val}'"

    def test_history_collection_default(self):
        """Test default value for qdrant_history_collection."""
        config = _config_from_env(drop_keys={"QDRANT_HISTORY_COLLECTION"})
        assert config.qdrant_history_collection == "conversation_history"

    def test_history_collection_from_env(self):
        """Test reading QDRANT_HISTORY_COLLECTION from env."""
        config = _config_from_env(overrides={"QDRANT_HISTORY_COLLECTION": "my_history"})
        assert config.qdrant_history_collection == "my_history"

    def test_quantization_mixed_settings(self):
        """Test mixed enabled/disabled quantization settings."""
        config = _config_from_env(
            overrides={
                "QDRANT_USE_QUANTIZATION": "true",
                "QDRANT_QUANTIZATION_RESCORE": "false",
                "QDRANT_QUANTIZATION_OVERSAMPLING": "1.5",
                "QDRANT_QUANTIZATION_ALWAYS_RAM": "true",
            }
        )

        assert config.qdrant_use_quantization is True
        assert config.qdrant_quantization_rescore is False
        assert config.qdrant_quantization_oversampling == 1.5
        assert config.qdrant_quantization_always_ram is True


class TestBotConfigHistory:
    """Tests for BotConfig history search settings (#433)."""

    def test_history_relevance_threshold_default(self):
        """Default history_relevance_threshold is 0.7."""
        config = _config_from_env(drop_keys={"HISTORY_RELEVANCE_THRESHOLD"})
        assert config.history_relevance_threshold == 0.7

    def test_history_relevance_threshold_from_env(self):
        """HISTORY_RELEVANCE_THRESHOLD env var is parsed as float."""
        config = _config_from_env(overrides={"HISTORY_RELEVANCE_THRESHOLD": "0.5"})
        assert config.history_relevance_threshold == 0.5
