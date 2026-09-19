"""Roundtrip test for GraphConfig.from_env() env-var mapping.

Guarantees that every env-var name and default in _GraphEnvSettings maps
correctly to the corresponding GraphConfig field — the safety net for the
pydantic-settings migration (#card_176c964330b6).
"""

from __future__ import annotations

import pytest


def test_graph_config_from_env_roundtrip_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """from_env() with no env vars set must produce the documented defaults."""
    # Clear any vars that would interfere
    for var in (
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "LLM_MODEL",
        "LLM_TEMPERATURE",
        "GENERATE_MAX_TOKENS",
        "REWRITE_MODEL",
        "REWRITE_MAX_TOKENS",
        "BGE_M3_URL",
        "BGE_M3_TIMEOUT",
        "QDRANT_URL",
        "QDRANT_COLLECTION",
        "SEARCH_TOP_K",
        "RERANK_TOP_K",
        "REDIS_URL",
        "MAX_REWRITE_ATTEMPTS",
        "SKIP_RERANK_THRESHOLD",
        "RELEVANCE_THRESHOLD_RRF",
        "SCORE_IMPROVEMENT_DELTA",
        "RERANK_PROVIDER",
        "SMALL_TO_BIG_MODE",
        "SMALL_TO_BIG_WINDOW_BEFORE",
        "SMALL_TO_BIG_WINDOW_AFTER",
        "MAX_EXPANDED_CHUNKS",
        "MAX_CONTEXT_TOKENS",
        "BOT_DOMAIN",
        "BOT_LANGUAGE",
        "RESPONSE_STYLE_ENABLED",
        "RESPONSE_STYLE_SHADOW_MODE",
        "SHOW_SOURCES",
        "GUARD_MODE",
        "CONTENT_FILTER_ENABLED",
        "REASONING_EFFORT",
        "REASONING_FORMAT",
        "DISABLE_REASONING",
    ):
        monkeypatch.delenv(var, raising=False)

    from src.runtime.config import GraphConfig

    cfg = GraphConfig.from_env()

    # LLM defaults
    assert cfg.llm_model == "gpt-4o-mini"
    assert cfg.llm_temperature == 0.7
    assert cfg.generate_max_tokens == 1024
    assert cfg.rewrite_model == "gpt-4o-mini"
    assert cfg.rewrite_max_tokens == 64
    assert cfg.reasoning_effort is None
    assert cfg.reasoning_format is None
    assert cfg.disable_reasoning is None

    # Retrieval defaults
    assert cfg.bge_m3_url == "http://bge-m3:8000"
    assert cfg.bge_m3_timeout == 120.0
    assert cfg.qdrant_url == "http://qdrant:6333"
    assert cfg.qdrant_collection == "gdrive_documents_bge"
    assert cfg.search_top_k == 40
    assert cfg.rerank_top_k == 7
    assert cfg.redis_url == "redis://redis:6379"
    assert cfg.max_rewrite_attempts == 1
    assert cfg.skip_rerank_threshold == pytest.approx(0.018)
    assert cfg.relevance_threshold_rrf == pytest.approx(0.005)
    assert cfg.score_improvement_delta == pytest.approx(0.001)
    assert cfg.rerank_provider == "colbert"
    assert cfg.small_to_big_mode == "on"
    assert cfg.small_to_big_window_before == 0
    assert cfg.small_to_big_window_after == 2
    assert cfg.max_expanded_chunks == 10
    assert cfg.max_context_tokens == 8000

    # Domain defaults
    assert cfg.domain == "недвижимость"
    assert cfg.domain_language == "ru"

    # Response defaults
    assert cfg.response_style_enabled is False
    assert cfg.response_style_shadow_mode is False
    assert cfg.show_sources is False

    # Security defaults
    assert cfg.guard_mode == "hard"
    assert cfg.content_filter_enabled is True


def test_graph_config_from_env_roundtrip_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """from_env() must pick up env vars with proper type coercion."""
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.3")
    monkeypatch.setenv("SEARCH_TOP_K", "20")
    monkeypatch.setenv("RERANK_TOP_K", "5")
    monkeypatch.setenv("SHOW_SOURCES", "true")
    monkeypatch.setenv("BOT_DOMAIN", "healthcare")
    monkeypatch.setenv("BOT_LANGUAGE", "en")
    monkeypatch.setenv("GUARD_MODE", "soft")
    monkeypatch.setenv("CONTENT_FILTER_ENABLED", "false")

    # Force module reload so _GraphEnvSettings picks up monkeypatched env
    import importlib

    import src.runtime.config as _mod

    importlib.reload(_mod)
    cfg = _mod.GraphConfig.from_env()

    assert cfg.llm_model == "gpt-4o"
    assert cfg.llm_temperature == pytest.approx(0.3)
    assert cfg.search_top_k == 20
    assert cfg.rerank_top_k == 5
    assert cfg.show_sources is True
    assert cfg.domain == "healthcare"
    assert cfg.domain_language == "en"
    assert cfg.guard_mode == "soft"
    assert cfg.content_filter_enabled is False


def test_graph_config_from_env_rewrite_model_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """REWRITE_MODEL falls back to LLM_MODEL when not set."""
    monkeypatch.setenv("LLM_MODEL", "cerebras-glm")
    monkeypatch.delenv("REWRITE_MODEL", raising=False)

    import importlib

    import src.runtime.config as _mod

    importlib.reload(_mod)
    cfg = _mod.GraphConfig.from_env()

    assert cfg.rewrite_model == "cerebras-glm"


def test_graph_config_from_env_llm_api_key_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM_API_KEY and OPENAI_API_KEY aliases both work."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")

    import importlib

    import src.runtime.config as _mod

    importlib.reload(_mod)
    cfg = _mod.GraphConfig.from_env()

    assert cfg.llm_api_key == "sk-test-openai"


@pytest.mark.parametrize("from_env", [False, True])
def test_graph_config_keeps_api_key_out_of_repr(monkeypatch, from_env):
    from src.runtime.config import GraphConfig

    canary = "graph-secret-repr-canary"
    monkeypatch.setenv("LLM_API_KEY", canary)
    config = GraphConfig.from_env() if from_env else GraphConfig(llm_api_key=canary)

    assert config.llm_api_key == canary
    assert canary not in repr(config)
    assert canary not in repr(config.llm)


def test_direct_config_does_not_load_environment(monkeypatch):
    from src.runtime.config import GraphConfig

    monkeypatch.setenv("LLM_MODEL", "environment-model")
    monkeypatch.setenv("REWRITE_MODEL", "environment-rewrite")
    assert GraphConfig().llm_model == "gpt-4o-mini"
    assert GraphConfig().rewrite_model == "gpt-4o-mini"
    assert GraphConfig(llm_model="explicit-model").llm_model == "explicit-model"
    assert GraphConfig.from_env().llm_model == "environment-model"
    assert GraphConfig.from_env().rewrite_model == "environment-rewrite"
