from __future__ import annotations

import asyncio
import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

from scripts.e2e import test_scenarios as scenarios
from scripts.e2e.claude_judge import LiteLLMJudge, build_judge
from scripts.e2e.config import E2EConfig
from scripts.e2e.langfuse_trace_validator import probe_litellm_route


def _scenario() -> scenarios.TestScenario:
    return scenarios.TestScenario(
        id="x",
        name="sample",
        query="query",
        group=scenarios.TestGroup.CHITCHAT,
    )


def test_build_judge_defaults_to_litellm_provider() -> None:
    cfg = E2EConfig(telegram_api_id=1, telegram_api_hash="hash")

    with patch("scripts.e2e.claude_judge.AsyncOpenAI") as mock_openai:
        mock_openai.return_value = MagicMock()
        judge = build_judge(cfg)

    assert isinstance(judge, LiteLLMJudge)


def test_litellm_judge_uses_openai_compatible_chat_completions() -> None:
    cfg = E2EConfig(
        telegram_api_id=1,
        telegram_api_hash="hash",
        judge_provider="litellm",
        judge_api_key="test-key",
        judge_base_url="http://localhost:4000/v1",
        judge_model="gpt-4o-mini",
    )

    client = MagicMock()
    completion = MagicMock()
    completion.choices = [
        MagicMock(
            message=MagicMock(
                content='{"relevance":{"score":8,"reason":"ok"},"completeness":{"score":8,"reason":"ok"},"filter_accuracy":{"score":8,"reason":"ok"},"tone_format":{"score":8,"reason":"ok"},"no_hallucination":{"score":8,"reason":"ok"},"total_score":8.0,"pass":true,"summary":"ok"}'
            )
        )
    ]
    client.chat.completions.create = AsyncMock(return_value=completion)

    with patch("scripts.e2e.claude_judge.AsyncOpenAI", return_value=client):
        judge = LiteLLMJudge(cfg)
        result = asyncio.run(judge.evaluate(_scenario(), "bot response"))

    assert result.passed is True
    assert result.total_score == 8.0


def test_probe_litellm_route_reads_model_info_alias_mapping() -> None:
    payload = {
        "data": [
            {
                "model_name": "gpt-4o-mini",
                "litellm_params": {"model": "cerebras/zai-glm-4.7"},
            }
        ]
    }

    with patch("scripts.e2e.langfuse_trace_validator.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = io.BytesIO(
            json.dumps(payload).encode("utf-8")
        )
        proof = probe_litellm_route(base_url="http://localhost:4000/v1", model_alias="gpt-4o-mini")

    assert proof is not None
    assert proof.route_model == "cerebras/zai-glm-4.7"
    assert proof.alias == "gpt-4o-mini"


def test_probe_litellm_route_skips_non_local_host() -> None:
    proof = probe_litellm_route(base_url="https://api.openai.com/v1", model_alias="gpt-4o-mini")
    assert proof is None
