# tests/unit/services/test_types.py
"""Tests for telegram_bot/services/types.py — PipelineResult frozen dataclass."""

import dataclasses

import pytest


class TestPipelineResultDefaults:
    """Tests for PipelineResult default field values."""

    def test_answer_defaults_to_empty_string(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult()
        assert result.answer == ""

    def test_sources_defaults_to_empty_list(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult()
        assert result.sources == []

    def test_query_type_defaults_to_general(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult()
        assert result.query_type == "GENERAL"

    def test_cache_hit_defaults_to_false(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult()
        assert result.cache_hit is False

    def test_needs_agent_defaults_to_false(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult()
        assert result.needs_agent is False

    def test_agent_intent_defaults_to_empty_string(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult()
        assert result.agent_intent == ""

    def test_pipeline_mode_defaults_to_client_direct(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult()
        assert result.pipeline_mode == "client_direct"

    def test_scores_defaults_to_empty_dict(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult()
        assert result.scores == {}

    def test_sent_message_defaults_to_none(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult()
        assert result.sent_message is None

    def test_response_sent_defaults_to_false(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult()
        assert result.response_sent is False


class TestPipelineResultImmutability:
    """Tests for PipelineResult frozen (immutable) behavior."""

    def test_frozen_cannot_set_answer(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult(answer="original")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            result.answer = "modified"  # type: ignore[misc]

    def test_frozen_cannot_set_needs_agent(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            result.needs_agent = True  # type: ignore[misc]

    def test_frozen_cannot_set_cache_hit(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            result.cache_hit = True  # type: ignore[misc]

    def test_frozen_cannot_add_new_attribute(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult()
        # slots=True prevents __dict__, so assignment raises TypeError or FrozenInstanceError
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            result.new_field = "value"  # type: ignore[attr-defined]

    def test_is_dataclass(self):
        from telegram_bot.services.types import PipelineResult

        assert dataclasses.is_dataclass(PipelineResult)


class TestPipelineResultNeedsAgent:
    """Tests for needs_agent flag semantics."""

    def test_needs_agent_true_with_agent_intent(self):
        """Pipeline result with needs_agent=True should carry agent_intent."""
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult(needs_agent=True, agent_intent="mortgage")
        assert result.needs_agent is True
        assert result.agent_intent == "mortgage"

    def test_needs_agent_false_by_default(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult(answer="Direct answer")
        assert result.needs_agent is False
        assert result.agent_intent == ""

    def test_needs_agent_intents_supported(self):
        """Test known agent intents per client pipeline spec."""
        from telegram_bot.services.types import PipelineResult

        for intent in ("mortgage", "handoff", "daily_summary"):
            result = PipelineResult(needs_agent=True, agent_intent=intent)
            assert result.agent_intent == intent


class TestPipelineResultConstruction:
    """Tests for PipelineResult construction with various fields."""

    def test_full_construction(self):
        from telegram_bot.services.types import PipelineResult

        result = PipelineResult(
            answer="Test answer",
            sources=[{"title": "Doc 1", "url": "http://example.com"}],
            query_type="FAQ",
            cache_hit=True,
            needs_agent=False,
            agent_intent="",
            latency_ms=120.5,
            llm_call_count=2,
            scores={"rrf": 0.015},
            pipeline_mode="client_direct",
            sent_message={"chat_id": 123, "message_id": 456},
            response_sent=True,
        )

        assert result.answer == "Test answer"
        assert result.query_type == "FAQ"
        assert result.cache_hit is True
        assert result.latency_ms == 120.5
        assert result.llm_call_count == 2
        assert result.scores == {"rrf": 0.015}
        assert result.sent_message == {"chat_id": 123, "message_id": 456}
        assert result.response_sent is True

    def test_sources_default_factory_creates_independent_lists(self):
        """Each PipelineResult gets its own sources list (not shared)."""
        from telegram_bot.services.types import PipelineResult

        r1 = PipelineResult()
        r2 = PipelineResult()
        assert r1.sources is not r2.sources

    def test_scores_default_factory_creates_independent_dicts(self):
        """Each PipelineResult gets its own scores dict (not shared)."""
        from telegram_bot.services.types import PipelineResult

        r1 = PipelineResult()
        r2 = PipelineResult()
        assert r1.scores is not r2.scores
