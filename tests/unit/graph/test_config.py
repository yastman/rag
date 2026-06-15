"""Tests for GraphConfig dataclass and service factories."""

from __future__ import annotations

import os
from unittest.mock import patch


class TestGraphConfig:
    def test_default_values(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig()
        assert cfg.llm_base_url == ""
        assert cfg.llm_model == "gpt-4o-mini"
        assert cfg.bge_m3_url == "http://bge-m3:8000"
        assert cfg.search_top_k == 40
        assert cfg.max_rewrite_attempts == 1
        assert cfg.rewrite_max_tokens == 64

    def test_from_env_rewrite_max_tokens(self):
        from telegram_bot.graph.config import GraphConfig

        env = {"REWRITE_MAX_TOKENS": "128"}
        with patch.dict(os.environ, env, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.rewrite_max_tokens == 128

    def test_from_env_llm_max_tokens(self):
        """Regression for #1537: LLM_MAX_TOKENS must drive llm_max_tokens.
        Before the fix the field defaulted to 4096 with no env override path."""
        from telegram_bot.graph.config import GraphConfig

        env = {"LLM_MAX_TOKENS": "2048"}
        with patch.dict(os.environ, env, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.llm_max_tokens == 2048

    def test_from_env_llm_temperature(self):
        from telegram_bot.graph.config import GraphConfig

        env = {"LLM_TEMPERATURE": "0.2"}
        with patch.dict(os.environ, env, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.llm_temperature == 0.2

    def test_from_env_llm_max_tokens_default(self):
        """When LLM_MAX_TOKENS is unset, the dataclass default (4096) is preserved."""
        from telegram_bot.graph.config import GraphConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.llm_max_tokens == 4096

    def test_from_env_max_rewrite_attempts(self):
        from telegram_bot.graph.config import GraphConfig

        env = {"MAX_REWRITE_ATTEMPTS": "3"}
        with patch.dict(os.environ, env, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.max_rewrite_attempts == 3

    def test_from_env(self):
        from telegram_bot.graph.config import GraphConfig

        env = {
            "LLM_MODEL": "test-model",
            "BGE_M3_URL": "http://bge:8000",
            "QDRANT_URL": "http://qdrant:6333",
            "SEARCH_TOP_K": "10",
            "BOT_DOMAIN": "тестовый домен",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.llm_base_url == ""
        assert cfg.llm_model == "test-model"
        assert cfg.bge_m3_url == "http://bge:8000"
        assert cfg.search_top_k == 10
        assert cfg.domain == "тестовый домен"

    def test_cache_thresholds_by_query_type(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig()
        assert cfg.cache_thresholds["FAQ"] == 0.12
        assert cfg.cache_thresholds["ENTITY"] == 0.10
        assert cfg.cache_thresholds["GENERAL"] == 0.08
        assert cfg.cache_thresholds["STRUCTURED"] == 0.05

    def test_cache_ttl_by_query_type(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig()
        assert cfg.cache_ttl["FAQ"] == 86400
        assert cfg.cache_ttl["ENTITY"] == 3600
        assert cfg.cache_ttl["GENERAL"] == 3600
        assert cfg.cache_ttl["STRUCTURED"] == 7200

    def test_create_llm(self):
        from src.runtime.llm.router import LiteLLMChatClient
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig(llm_model="test-model", llm_base_url="http://test:4000")
        llm = cfg.create_llm()

        assert isinstance(llm, LiteLLMChatClient)
        assert llm.default_model == "test-model"
        assert llm._langfuse_auto_trace is False

    def test_create_llm_auto_trace_false_uses_litellm_sdk(self):
        from src.runtime.llm.router import LiteLLMChatClient
        from telegram_bot.graph.config import GraphConfig

        with patch("langfuse.openai.AsyncOpenAI") as mock_langfuse:
            cfg = GraphConfig(llm_model="test-model", llm_base_url="http://test:4000")
            llm = cfg.create_llm(auto_trace=False)

        assert isinstance(llm, LiteLLMChatClient)
        assert llm.default_model == "test-model"
        mock_langfuse.assert_not_called()
        assert getattr(llm, "_langfuse_auto_trace", None) is False

    def test_create_embeddings(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig(bge_m3_url="http://bge:8000", bge_m3_timeout=30.0)
        emb = cfg.create_embeddings()
        from telegram_bot.integrations.embeddings import BGEM3Embeddings

        assert isinstance(emb, BGEM3Embeddings)
        assert emb.base_url == "http://bge:8000"
        assert emb.timeout == 30.0

    def test_create_sparse_embeddings(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig(bge_m3_url="http://bge:8000", bge_m3_timeout=60.0)
        sparse = cfg.create_sparse_embeddings()
        from telegram_bot.integrations.embeddings import BGEM3SparseEmbeddings

        assert isinstance(sparse, BGEM3SparseEmbeddings)
        assert sparse.base_url == "http://bge:8000"
        assert sparse.timeout == 60.0

    def test_generate_max_tokens_default(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig()
        assert cfg.generate_max_tokens == 1024

    def test_from_env_defaults(self):
        from telegram_bot.graph.config import GraphConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.llm_base_url == ""
        assert cfg.domain == "недвижимость"
        assert cfg.domain_language == "ru"

    def test_response_style_flags_default_false(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig()
        assert cfg.response_style_enabled is False
        assert cfg.response_style_shadow_mode is False

    def test_response_style_flags_from_env(self):
        from telegram_bot.graph.config import GraphConfig

        env = {"RESPONSE_STYLE_ENABLED": "true", "RESPONSE_STYLE_SHADOW_MODE": "true"}
        with patch.dict(os.environ, env, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.response_style_enabled is True
        assert cfg.response_style_shadow_mode is True

    def test_rerank_provider_default_colbert(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig()
        assert cfg.rerank_provider == "colbert"

    def test_rerank_provider_from_env(self):
        from telegram_bot.graph.config import GraphConfig

        env = {"RERANK_PROVIDER": "none"}
        with patch.dict(os.environ, env, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.rerank_provider == "none"

    def test_small_to_big_defaults(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig()
        assert cfg.small_to_big_mode == "on"
        assert cfg.small_to_big_window_before == 0
        assert cfg.small_to_big_window_after == 2
        assert cfg.max_expanded_chunks == 10
        assert cfg.max_context_tokens == 8000

    def test_small_to_big_from_env(self):
        from telegram_bot.graph.config import GraphConfig

        env = {
            "SMALL_TO_BIG_MODE": "auto",
            "SMALL_TO_BIG_WINDOW_BEFORE": "1",
            "SMALL_TO_BIG_WINDOW_AFTER": "3",
            "MAX_EXPANDED_CHUNKS": "20",
            "MAX_CONTEXT_TOKENS": "12000",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.small_to_big_mode == "auto"
        assert cfg.small_to_big_window_before == 1
        assert cfg.small_to_big_window_after == 3
        assert cfg.max_expanded_chunks == 20
        assert cfg.max_context_tokens == 12000

    # --- Reasoning control ---

    def test_reasoning_defaults_none(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig()
        assert cfg.reasoning_effort is None
        assert cfg.reasoning_format is None
        assert cfg.disable_reasoning is None

    def test_get_reasoning_kwargs_all_none(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig()
        assert cfg.get_reasoning_kwargs() == {}

    def test_get_reasoning_kwargs_effort_low(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig(reasoning_effort="low")
        assert cfg.get_reasoning_kwargs() == {"reasoning_effort": "low"}

    def test_get_reasoning_kwargs_disable_reasoning(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig(disable_reasoning=True)
        assert cfg.get_reasoning_kwargs() == {"extra_body": {"disable_reasoning": True}}

    def test_get_reasoning_kwargs_combined(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig(reasoning_effort="high", reasoning_format="hidden")
        assert cfg.get_reasoning_kwargs() == {
            "reasoning_effort": "high",
            "extra_body": {"reasoning_format": "hidden"},
        }

    def test_get_reasoning_kwargs_provider_specific_extra_body(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig(
            reasoning_effort="high",
            reasoning_format="hidden",
        )
        assert cfg.get_reasoning_kwargs() == {
            "reasoning_effort": "high",
            "extra_body": {
                "reasoning_format": "hidden",
            },
        }

    def test_disable_reasoning_is_mutually_exclusive_with_reasoning_controls(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig(
            reasoning_effort="high",
            reasoning_format="hidden",
            disable_reasoning=True,
        )
        assert cfg.get_reasoning_kwargs() == {
            "extra_body": {
                "disable_reasoning": True,
            },
        }

    def test_from_env_reasoning_effort(self):
        from telegram_bot.graph.config import GraphConfig

        env = {"REASONING_EFFORT": "low"}
        with patch.dict(os.environ, env, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.reasoning_effort == "low"

    def test_from_env_disable_reasoning(self):
        from telegram_bot.graph.config import GraphConfig

        env = {"DISABLE_REASONING": "true"}
        with patch.dict(os.environ, env, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.disable_reasoning is True

    def test_from_env_reasoning_not_set(self):
        from telegram_bot.graph.config import GraphConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.reasoning_effort is None
        assert cfg.reasoning_format is None
        assert cfg.disable_reasoning is None

    def test_skip_rerank_threshold_requires_fusion_overlap(self):
        """Default threshold must be above single-query top-1 RRF score.

        RRF with k=60: rank 1 = 1/61 ≈ 0.01639.
        skip_rerank_threshold must be > 0.01639 so that a single top-1
        result does NOT skip reranking.
        """
        from telegram_bot.graph.config import GraphConfig

        config = GraphConfig.from_env()
        single_query_top1_rrf = 1 / 61  # ≈ 0.01639
        assert config.skip_rerank_threshold > single_query_top1_rrf, (
            f"skip_rerank_threshold={config.skip_rerank_threshold} must be > "
            f"single-query top-1 RRF={single_query_top1_rrf:.5f}"
        )
