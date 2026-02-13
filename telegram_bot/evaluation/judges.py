"""LLM-as-a-Judge evaluators for RAG Triad (faithfulness, relevance, context)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from .prompts import ANSWER_RELEVANCE, CONTEXT_RELEVANCE, FAITHFULNESS


logger = logging.getLogger(__name__)

_JUDGE_TEMPERATURE = 0
_JUDGE_MAX_TOKENS = 256
_JUDGE_TIMEOUT_S = 20
_JUDGE_RETRIES = 3


@dataclass
class JudgeResult:
    """Result from a judge evaluation."""

    score: float | None
    reasoning: str


def parse_judge_response(text: str) -> JudgeResult:
    """Parse JSON response from judge LLM.

    Handles: valid JSON, JSON within surrounding text, missing fields, clamping.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON from surrounding text
        match = re.search(r'\{[^{}]*"score"[^{}]*\}', text)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return JudgeResult(score=None, reasoning=f"Parse error: invalid JSON: {text[:100]}")
        else:
            return JudgeResult(score=None, reasoning=f"Parse error: invalid JSON: {text[:100]}")

    reasoning = str(data.get("reasoning", ""))
    raw_score = data.get("score")

    if raw_score is None:
        return JudgeResult(score=None, reasoning=reasoning or "No score in response")

    try:
        score = float(raw_score)
        score = max(0.0, min(1.0, score))  # clamp to [0, 1]
    except (TypeError, ValueError):
        return JudgeResult(score=None, reasoning=f"Parse error: invalid score '{raw_score}'")

    return JudgeResult(score=score, reasoning=reasoning)


async def _call_judge(client: Any, model: str, prompt: str) -> JudgeResult:
    """Call LLM judge with timeout+retry and parse response."""
    for attempt in range(1, _JUDGE_RETRIES + 1):
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=_JUDGE_TEMPERATURE,
                    max_tokens=_JUDGE_MAX_TOKENS,
                    response_format={"type": "json_object"},
                ),
                timeout=_JUDGE_TIMEOUT_S,
            )
            content = response.choices[0].message.content or "{}"
            return parse_judge_response(content)
        except Exception as e:
            if attempt == _JUDGE_RETRIES:
                logger.warning("Judge LLM call failed after %d attempts: %s", attempt, e)
                return JudgeResult(score=None, reasoning=f"LLM error: {e!s}")
            await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
    # unreachable but makes mypy happy
    return JudgeResult(score=None, reasoning="Unexpected: no attempts made")


async def judge_faithfulness(
    *, client: Any, model: str, query: str, answer: str, context: str
) -> JudgeResult:
    """Evaluate if answer is grounded in the provided context (no hallucinations)."""
    prompt = FAITHFULNESS.format(query=query, answer=answer, context=context)
    return await _call_judge(client, model, prompt)


async def judge_answer_relevance(
    *, client: Any, model: str, query: str, answer: str
) -> JudgeResult:
    """Evaluate if answer is relevant and helpful for the question."""
    prompt = ANSWER_RELEVANCE.format(query=query, answer=answer)
    return await _call_judge(client, model, prompt)


async def judge_context_relevance(
    *, client: Any, model: str, query: str, context: str
) -> JudgeResult:
    """Evaluate if retrieved documents are relevant to the question."""
    prompt = CONTEXT_RELEVANCE.format(query=query, context=context)
    return await _call_judge(client, model, prompt)
