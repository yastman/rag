"""Tests for GUARD_ML_ENABLED config and state fields."""

from __future__ import annotations

import os
from unittest.mock import patch


class TestGuardMLConfig:
    """Config fields for ML guard layer."""

    def test_bot_config_guard_ml_enabled_default_false(self):
        from telegram_bot.config import BotConfig

        config = BotConfig()
        assert config.guard_ml_enabled is False

    def test_bot_config_guard_ml_enabled_from_env(self):
        with patch.dict(os.environ, {"GUARD_ML_ENABLED": "true"}, clear=False):
            from telegram_bot.config import BotConfig

            config = BotConfig()
            assert config.guard_ml_enabled is True

    def test_graph_config_guard_ml_enabled_default_false(self):
        from telegram_bot.graph.config import GraphConfig

        config = GraphConfig()
        assert config.guard_ml_enabled is False

    def test_graph_config_from_env_guard_ml(self):
        with patch.dict(os.environ, {"GUARD_ML_ENABLED": "true"}, clear=False):
            from telegram_bot.graph.config import GraphConfig

            config = GraphConfig.from_env()
            assert config.guard_ml_enabled is True

    def test_bot_config_llm_guard_url_default(self):
        from telegram_bot.config import BotConfig

        config = BotConfig()
        assert config.llm_guard_url == "http://llm-guard:8100"

    def test_bot_config_llm_guard_url_from_env(self):
        with patch.dict(os.environ, {"LLM_GUARD_URL": "http://custom:9000"}, clear=False):
            from telegram_bot.config import BotConfig

            config = BotConfig()
            assert config.llm_guard_url == "http://custom:9000"

    def test_graph_config_llm_guard_url_default(self):
        from telegram_bot.graph.config import GraphConfig

        config = GraphConfig()
        assert config.llm_guard_url == "http://llm-guard:8100"

    def test_graph_config_llm_guard_url_from_env(self):
        with patch.dict(os.environ, {"LLM_GUARD_URL": "http://custom:9000"}, clear=False):
            from telegram_bot.graph.config import GraphConfig

            config = GraphConfig.from_env()
            assert config.llm_guard_url == "http://custom:9000"


class TestGuardMLState:
    """State fields for ML guard layer."""

    def test_initial_state_has_ml_guard_fields(self):
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s", query="test")
        assert state["guard_ml_score"] == 0.0
        assert state["guard_ml_latency_ms"] == 0.0
