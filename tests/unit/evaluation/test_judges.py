"""Tests for LLM-as-a-Judge evaluators."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.evaluation.judges import (
    judge_answer_relevance,
    judge_context_relevance,
    judge_faithfulness,
    parse_judge_response,
)


class TestParseJudgeResponse:
    def test_valid_json(self):
        result = parse_judge_response('{"score": 0.8, "reasoning": "Good answer"}')
        assert result.score == 0.8
        assert result.reasoning == "Good answer"

    def test_json_with_surrounding_text(self):
        result = parse_judge_response('Here is my eval: {"score": 0.5, "reasoning": "Ok"}')
        assert result.score == 0.5

    def test_missing_score_returns_none(self):
        result = parse_judge_response('{"reasoning": "no score"}')
        assert result.score is None
        assert result.reasoning == "no score"

    def test_invalid_json_returns_none(self):
        result = parse_judge_response("not json at all")
        assert result.score is None
        assert "parse error" in result.reasoning.lower()

    def test_score_clamped_to_0_1(self):
        result = parse_judge_response('{"score": 1.5, "reasoning": "too high"}')
        assert result.score == 1.0
        result2 = parse_judge_response('{"score": -0.3, "reasoning": "too low"}')
        assert result2.score == 0.0


class TestJudgeFunctions:
    @pytest.mark.asyncio
    async def test_judge_faithfulness_calls_llm(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content='{"score": 0.9, "reasoning": "grounded"}'))
                ]
            )
        )
        result = await judge_faithfulness(
            client=mock_client,
            model="test-model",
            query="What is X?",
            answer="X is Y",
            context="X is defined as Y in docs",
        )
        assert result.score == 0.9
        mock_client.chat.completions.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_judge_answer_relevance_calls_llm(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content='{"score": 0.7, "reasoning": "relevant"}'))
                ]
            )
        )
        result = await judge_answer_relevance(
            client=mock_client,
            model="test-model",
            query="What is X?",
            answer="X is Y",
        )
        assert result.score == 0.7

    @pytest.mark.asyncio
    async def test_judge_context_relevance_calls_llm(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(content='{"score": 0.6, "reasoning": "mostly relevant"}')
                    )
                ]
            )
        )
        result = await judge_context_relevance(
            client=mock_client,
            model="test-model",
            query="What is X?",
            context="Doc about X and Y",
        )
        assert result.score == 0.6

    @pytest.mark.asyncio
    async def test_judge_handles_llm_error(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))
        with patch("telegram_bot.evaluation.judges.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            result = await judge_faithfulness(
                client=mock_client,
                model="test-model",
                query="q",
                answer="a",
                context="c",
            )
        assert result.score is None
        assert "error" in result.reasoning.lower()
        assert mock_sleep.await_count == 2
