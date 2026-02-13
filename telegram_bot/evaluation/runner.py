"""Batch runner for LLM-as-a-Judge evaluation on Langfuse traces."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .judges import judge_answer_relevance, judge_context_relevance, judge_faithfulness


logger = logging.getLogger(__name__)

BATCH_SIZE = 10
DEFAULT_MODEL = "gpt-4o-mini-cerebras-glm"
DEFAULT_LITELLM_URL = "http://localhost:4000"
SCORE_NAMES = ("judge_faithfulness", "judge_answer_relevance", "judge_context_relevance")
ONLINE_JUDGE_SEMAPHORE = asyncio.Semaphore(2)


@dataclass
class TraceData:
    """Extracted data from a Langfuse trace for judge evaluation."""

    trace_id: str
    query: str
    answer: str
    context: str


def extract_trace_data(trace: Any, observations: list[Any]) -> TraceData | None:
    """Extract query, answer, and context from a Langfuse trace + observations.

    Returns None if essential data is missing (no query, no answer, no context).
    """
    query = ""
    if isinstance(trace.input, dict):
        query = trace.input.get("query", "")
    if not query:
        return None

    answer = ""
    if isinstance(trace.output, dict):
        answer = trace.output.get("response", "")
    if not answer:
        return None

    # Extract context from node-retrieve observation
    context_parts: list[str] = []
    for obs in observations:
        if getattr(obs, "name", "") != "node-retrieve":
            continue
        output = getattr(obs, "output", None)
        if not isinstance(output, dict):
            continue
        retrieved = output.get("retrieved_context", [])
        for doc in retrieved:
            if isinstance(doc, dict) and doc.get("content"):
                score = doc.get("score", 0)
                context_parts.append(f"[{score:.2f}] {doc['content']}")

    if not context_parts:
        return None

    return TraceData(
        trace_id=trace.id,
        query=query,
        answer=answer,
        context="\n\n".join(context_parts),
    )


def _has_judge_scores(trace: Any) -> bool:
    """Check if trace already has all 3 judge scores."""
    existing = {s.name for s in (trace.scores or [])}
    return set(SCORE_NAMES).issubset(existing)


async def evaluate_trace(
    langfuse: Any,
    client: Any,
    model: str,
    data: TraceData,
) -> dict[str, float | None]:
    """Run all 3 judges on a single trace and write scores to Langfuse.

    Returns dict of {score_name: value} for reporting.
    """
    results = await asyncio.gather(
        judge_faithfulness(
            client=client,
            model=model,
            query=data.query,
            answer=data.answer,
            context=data.context,
        ),
        judge_answer_relevance(
            client=client,
            model=model,
            query=data.query,
            answer=data.answer,
        ),
        judge_context_relevance(
            client=client,
            model=model,
            query=data.query,
            context=data.context,
        ),
    )

    score_map: dict[str, float | None] = {}
    for name, result in zip(SCORE_NAMES, results, strict=True):
        if result.score is None:
            langfuse.create_score(
                trace_id=data.trace_id,
                name=f"{name}_error",
                value="judge_failed",
                data_type="CATEGORICAL",
                comment=result.reasoning[:500],
            )
            score_map[name] = None
            continue

        langfuse.create_score(
            trace_id=data.trace_id,
            name=name,
            value=result.score,
            data_type="NUMERIC",
            comment=result.reasoning[:500],
        )
        score_map[name] = result.score

    return score_map


async def run_batch(
    *,
    hours: int = 24,
    tag: str = "rag",
    sample_rate: float = 1.0,
    model: str | None = None,
) -> dict[str, Any]:
    """Run batch judge evaluation on recent Langfuse traces.

    Args:
        hours: Look back N hours for traces.
        tag: Filter traces by tag.
        sample_rate: Fraction of traces to evaluate (1.0 = all).
        model: LLM model for judge (default: gpt-4o-mini-cerebras-glm).

    Returns:
        Summary dict with counts and average scores.
    """
    import random

    from langfuse import Langfuse
    from openai import AsyncOpenAI

    langfuse = Langfuse()
    llm_model = model or os.getenv("JUDGE_MODEL", DEFAULT_MODEL)
    llm_url = os.getenv("LITELLM_BASE_URL", DEFAULT_LITELLM_URL)
    client = AsyncOpenAI(api_key="not-needed", base_url=llm_url)

    from_ts = datetime.now(UTC) - timedelta(hours=hours)
    page = 1
    total = 0
    evaluated = 0
    skipped = 0
    all_scores: dict[str, list[float]] = {n: [] for n in SCORE_NAMES}

    while True:
        traces_resp = langfuse.api.trace.list(
            page=page,
            limit=BATCH_SIZE,
            tags=tag,
            from_timestamp=from_ts,
        )
        traces = traces_resp.data
        if not traces:
            break

        for trace in traces:
            total += 1

            if _has_judge_scores(trace):
                skipped += 1
                continue

            if sample_rate < 1.0 and random.random() > sample_rate:
                continue

            # Fetch observations (avoid per-id N+1 calls)
            obs_page = langfuse.api.observations.get_many(
                trace_id=trace.id,
                type="SPAN",
                page=1,
                limit=50,
            )
            observations = obs_page.data or []

            data = extract_trace_data(trace, observations)
            if data is None:
                continue

            scores = await evaluate_trace(langfuse, client, llm_model, data)
            evaluated += 1
            for name, val in scores.items():
                if val is not None:
                    all_scores[name].append(val)

            logger.info(
                "Evaluated trace %s: faith=%.2f rel=%.2f ctx=%.2f",
                data.trace_id,
                scores.get("judge_faithfulness") or 0,
                scores.get("judge_answer_relevance") or 0,
                scores.get("judge_context_relevance") or 0,
            )

        page += 1

    langfuse.flush()

    averages = {}
    for name, vals in all_scores.items():
        averages[name] = round(sum(vals) / len(vals), 3) if vals else None

    summary = {
        "total_traces": total,
        "evaluated": evaluated,
        "skipped_existing": skipped,
        "averages": averages,
    }
    logger.info("Batch complete: %s", summary)
    return summary
