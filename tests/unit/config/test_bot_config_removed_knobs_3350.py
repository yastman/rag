"""Test that confirmed-ignored BotConfig knobs stay removed (issue #3350).

The Telegram runtime never reads or forwards these 39 fields; the A02 audit
found zero typed reads from BotConfig for the whole set. Live behaviour for
retrieval/quantization/small-to-big knobs is owned by ``src.runtime.config.GraphConfig``
and legacy ``src.config.settings.Settings``, which read the same env keys
themselves. The operator-facing BotConfig schema must not re-advertise them.
"""

from telegram_bot.config import BotConfig


REMOVED_KNOBS: frozenset[str] = frozenset(
    {
        # RAG / search
        "top_k",
        "min_score",
        "rerank_top_k",
        "rerank_candidates_max",
        # CESC
        "cesc_enabled",
        "cesc_extraction_frequency",
        "user_context_ttl",
        # Hybrid search weights
        "hybrid_dense_weight",
        "hybrid_sparse_weight",
        # Score boosting
        "freshness_boost_enabled",
        "freshness_field",
        "freshness_scale_days",
        # MMR
        "mmr_enabled",
        "mmr_lambda",
        # Qdrant quantization (single live selector: qdrant_quantization_mode)
        "qdrant_use_quantization",
        "qdrant_quantization_rescore",
        "qdrant_quantization_oversampling",
        "qdrant_quantization_always_ram",
        # HyDE
        "use_hyde",
        "hyde_min_words",
        # Semantic cache tuning
        "semantic_cache_threshold",
        "semantic_cache_ttl_default",
        # Guardrails
        "enable_confidence_scoring",
        "enable_off_topic_detection",
        "low_confidence_threshold",
        # Small-to-big expansion
        "small_to_big_mode",
        "small_to_big_window_before",
        "small_to_big_window_after",
        "max_expanded_chunks",
        "max_context_tokens",
        # Supervisor routing / call limits
        "supervisor_model",
        "supervisor_max_tokens",
        "max_llm_calls",
        "max_tool_calls",
        # LLM-as-a-Judge
        "judge_sample_rate",
        "judge_model",
        # Agent history
        "agent_max_history_messages",
        # i18n (owned by src.core.contracts.SUPPORTED_REQUEST_LANGUAGES)
        "supported_locales",
        "default_locale",
    }
)


def test_removed_ignored_knobs_are_absent() -> None:
    """All 39 ignored knobs must be gone from the BotConfig schema (#3350)."""
    present = REMOVED_KNOBS & BotConfig.model_fields.keys()
    assert not present, (
        "Ignored BotConfig knobs resurfaced in the schema; the runtime never "
        f"reads them: {sorted(present)}"
    )


def test_live_quantization_selector_is_preserved() -> None:
    """The single live quantization selector stays in the schema (#3350)."""
    assert "qdrant_quantization_mode" in BotConfig.model_fields


def test_live_search_and_rerank_surface_is_preserved() -> None:
    """Live search/rerank knobs stay in the schema (#3350)."""
    for field in ("search_top_k", "rerank_provider", "qdrant_timeout"):
        assert field in BotConfig.model_fields, f"live knob {field} must stay"
