"""Tests for GraphConfig dataclass and service factories."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch


class TestGraphConfig:
    def test_default_values(self):
        from telegram_bot.graph.config import GraphConfig

        cfg = GraphConfig()
        assert cfg.llm_base_url == "http://litellm:4000"
        assert cfg.llm_model == "gpt-4o-mini"
        assert cfg.bge_m3_url == "http://bge-m3:8000"
        assert cfg.search_top_k == 20
        assert cfg.max_rewrite_attempts == 1
        assert cfg.rewrite_max_tokens == 64

    def test_from_env_rewrite_max_tokens(self):
        from telegram_bot.graph.config import GraphConfig

        env = {"REWRITE_MAX_TOKENS": "128"}
        with patch.dict(os.environ, env, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.rewrite_max_tokens == 128

    def test_from_env_max_rewrite_attempts(self):
        from telegram_bot.graph.config import GraphConfig

        env = {"MAX_REWRITE_ATTEMPTS": "3"}
        with patch.dict(os.environ, env, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.max_rewrite_attempts == 3

    def test_from_env(self):
        from telegram_bot.graph.config import GraphConfig

        env = {
            "LLM_BASE_URL": "http://llm:4000",
            "LLM_MODEL": "test-model",
            "BGE_M3_URL": "http://bge:8000",
            "QDRANT_URL": "http://qdrant:6333",
            "SEARCH_TOP_K": "10",
            "BOT_DOMAIN": "тестовый домен",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.llm_base_url == "http://llm:4000"
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
        from telegram_bot.graph.config import GraphConfig

        with patch("langfuse.openai.AsyncOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            cfg = GraphConfig(llm_model="test-model", llm_base_url="http://test:4000")
            llm = cfg.create_llm()
        assert llm is not None
        mock_cls.assert_called_once_with(
            api_key="no-key",
            base_url="http://test:4000",
            max_retries=2,
            timeout=60.0,
        )

    def test_create_supervisor_llm(self):
        from telegram_bot.graph.config import GraphConfig

        with patch("langchain_openai.ChatOpenAI") as mock_chat_openai:
            mock_chat_openai.return_value = MagicMock()
            cfg = GraphConfig(llm_model="default-model", llm_base_url="http://test:4000")
            llm = cfg.create_supervisor_llm(model_override="router-model")

        assert llm is not None
        assert mock_chat_openai.call_args.kwargs["model"] == "router-model"
        assert mock_chat_openai.call_args.kwargs["base_url"] == "http://test:4000"

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
        assert cfg.generate_max_tokens == 2048

    def test_from_env_defaults(self):
        from telegram_bot.graph.config import GraphConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = GraphConfig.from_env()
        assert cfg.llm_base_url == "http://litellm:4000"
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
