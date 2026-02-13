"""Tests for online LLM judge sampling."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.evaluation.judges import JudgeResult


class TestOnlineJudgeSampling:
    @pytest.mark.asyncio
    async def test_run_online_judge_writes_scores(self):
        from telegram_bot.evaluation.runner import run_online_judge

        mock_langfuse = MagicMock()
        mock_langfuse.create_score = MagicMock()

        with (
            patch(
                "telegram_bot.evaluation.runner.judge_faithfulness",
                new_callable=AsyncMock,
                return_value=JudgeResult(score=0.9, reasoning="ok"),
            ),
            patch(
                "telegram_bot.evaluation.runner.judge_answer_relevance",
                new_callable=AsyncMock,
                return_value=JudgeResult(score=0.8, reasoning="ok"),
            ),
            patch(
                "telegram_bot.evaluation.runner.judge_context_relevance",
                new_callable=AsyncMock,
                return_value=JudgeResult(score=0.7, reasoning="ok"),
            ),
        ):
            await run_online_judge(
                langfuse=mock_langfuse,
                trace_id="trace-123",
                query="test",
                answer="answer",
                context="context docs",
                model="test-model",
                llm_base_url="http://localhost:4000",
            )

        assert mock_langfuse.create_score.call_count == 3
