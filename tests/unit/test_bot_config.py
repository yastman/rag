"""Tests for BotConfig quantization settings."""

import importlib
import os
from unittest.mock import patch


class TestBotConfigQuantization:
    """Tests for BotConfig quantization environment variable settings."""

    def test_quantization_defaults(self):
        """Test default quantization values when no environment variables set."""
        # Create a clean environment without quantization vars
        env_without_quantization = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("QDRANT_QUANTIZATION") and k != "QDRANT_USE_QUANTIZATION"
        }

        with patch.dict(os.environ, env_without_quantization, clear=True):
            # Force reimport to pick up new environment
            import telegram_bot.config as config_module

            importlib.reload(config_module)
            config = config_module.BotConfig()

            # Verify all default values (True, True, 2.0, True)
            assert config.qdrant_use_quantization is True
            assert config.qdrant_quantization_rescore is True
            assert config.qdrant_quantization_oversampling == 2.0
            assert config.qdrant_quantization_always_ram is True

    def test_quantization_from_env_all_enabled(self):
        """Test reading all quantization values from environment variables."""
        test_env = os.environ.copy()
        test_env.update(
            {
                "QDRANT_USE_QUANTIZATION": "true",
                "QDRANT_QUANTIZATION_RESCORE": "true",
                "QDRANT_QUANTIZATION_OVERSAMPLING": "3.5",
                "QDRANT_QUANTIZATION_ALWAYS_RAM": "true",
            }
        )

        with patch.dict(os.environ, test_env, clear=True):
            import telegram_bot.config as config_module

            importlib.reload(config_module)
            config = config_module.BotConfig()

            assert config.qdrant_use_quantization is True
            assert config.qdrant_quantization_rescore is True
            assert config.qdrant_quantization_oversampling == 3.5
            assert config.qdrant_quantization_always_ram is True

    def test_quantization_from_env_all_disabled(self):
        """Test reading disabled quantization values from environment variables."""
        test_env = os.environ.copy()
        test_env.update(
            {
                "QDRANT_USE_QUANTIZATION": "false",
                "QDRANT_QUANTIZATION_RESCORE": "false",
                "QDRANT_QUANTIZATION_OVERSAMPLING": "1.0",
                "QDRANT_QUANTIZATION_ALWAYS_RAM": "false",
            }
        )

        with patch.dict(os.environ, test_env, clear=True):
            import telegram_bot.config as config_module

            importlib.reload(config_module)
            config = config_module.BotConfig()

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
            test_env = os.environ.copy()
            test_env["QDRANT_QUANTIZATION_OVERSAMPLING"] = env_value

            with patch.dict(os.environ, test_env, clear=True):
                import telegram_bot.config as config_module

                importlib.reload(config_module)
                config = config_module.BotConfig()
                assert config.qdrant_quantization_oversampling == expected, (
                    f"Expected {expected} for env value '{env_value}'"
                )

    def test_quantization_boolean_case_insensitive(self):
        """Test that boolean parsing is case insensitive."""
        import telegram_bot.config as config_module

        # Test various True representations
        true_values = ["true", "True", "TRUE", "TrUe"]
        for val in true_values:
            test_env = os.environ.copy()
            test_env["QDRANT_USE_QUANTIZATION"] = val

            with patch.dict(os.environ, test_env, clear=True):
                importlib.reload(config_module)
                config = config_module.BotConfig()
                assert config.qdrant_use_quantization is True, f"Expected True for '{val}'"

        # Test various False representations
        false_values = ["false", "False", "FALSE", "FaLsE"]
        for val in false_values:
            test_env = os.environ.copy()
            test_env["QDRANT_USE_QUANTIZATION"] = val

            with patch.dict(os.environ, test_env, clear=True):
                importlib.reload(config_module)
                config = config_module.BotConfig()
                assert config.qdrant_use_quantization is False, f"Expected False for '{val}'"

    def test_history_collection_default(self):
        """Test default value for qdrant_history_collection."""
        env = {k: v for k, v in os.environ.items() if k != "QDRANT_HISTORY_COLLECTION"}
        with patch.dict(os.environ, env, clear=True):
            import telegram_bot.config as config_module

            importlib.reload(config_module)
            config = config_module.BotConfig()
            assert config.qdrant_history_collection == "conversation_history"

    def test_history_collection_from_env(self):
        """Test reading QDRANT_HISTORY_COLLECTION from env."""
        test_env = os.environ.copy()
        test_env["QDRANT_HISTORY_COLLECTION"] = "my_history"
        with patch.dict(os.environ, test_env, clear=True):
            import telegram_bot.config as config_module

            importlib.reload(config_module)
            config = config_module.BotConfig()
            assert config.qdrant_history_collection == "my_history"

    def test_quantization_mixed_settings(self):
        """Test mixed enabled/disabled quantization settings."""
        test_env = os.environ.copy()
        test_env.update(
            {
                "QDRANT_USE_QUANTIZATION": "true",
                "QDRANT_QUANTIZATION_RESCORE": "false",
                "QDRANT_QUANTIZATION_OVERSAMPLING": "1.5",
                "QDRANT_QUANTIZATION_ALWAYS_RAM": "true",
            }
        )

        with patch.dict(os.environ, test_env, clear=True):
            import telegram_bot.config as config_module

            importlib.reload(config_module)
            config = config_module.BotConfig()

            assert config.qdrant_use_quantization is True
            assert config.qdrant_quantization_rescore is False
            assert config.qdrant_quantization_oversampling == 1.5
            assert config.qdrant_quantization_always_ram is True
