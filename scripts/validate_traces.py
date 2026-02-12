#!/usr/bin/env python3
"""Trace validation runner.

Rebuilds pipeline, runs queries through LangGraph, collects Langfuse traces,
computes p50/p95 aggregates, and generates validation report.

Usage:
    uv run python scripts/validate_traces.py --report
    uv run python scripts/validate_traces.py --collection legal_documents --report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv
from langfuse import Langfuse


# Ensure project root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.validate_queries import (
    ValidationQuery,
    get_cache_hit_queries,
    get_queries_for_collection,
    get_warmup_queries,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Reference trace from issue #105
REFERENCE_TRACE_ID = "c2b95d86aa1f643b79016dd611c4691f"

COLLECTIONS_TO_CHECK = ["gdrive_documents_bge", "contextual_bulgaria_voyage"]

STREAMING_QUERY_COUNT = 5  # First N cold queries for streaming TTFT phase (deterministic)


class FakeSentMessage:
    """Records edit_text calls for TTFT measurement.

    Minimal aiogram sent-message stand-in: tracks first edit timestamp
    and call count without Telegram I/O.
    """

    def __init__(self) -> None:
        self.t_first_edit: float | None = None
        self.edit_calls_count: int = 0
        self.last_text_len: int = 0

    async def edit_text(self, text: str, **kwargs: Any) -> None:
        self.edit_calls_count += 1
        self.last_text_len = len(text)
        if self.t_first_edit is None:
            self.t_first_edit = time.monotonic()

    async def delete(self) -> None:
        pass


class FakeMessage:
    """Minimal aiogram Message stand-in for streaming validation.

    Provides answer() → FakeSentMessage with timestamp recording.
    TTFT = sent.t_first_edit - self.t_answer_called (seconds).
    """

    def __init__(self) -> None:
        self.t_answer_called: float | None = None
        self.sent: FakeSentMessage | None = None

    async def answer(self, text: str, **kwargs: Any) -> FakeSentMessage:
        self.t_answer_called = time.monotonic()
        self.sent = FakeSentMessage()
        return self.sent


@dataclass
class TraceResult:
    """Result from a single validation query."""

    trace_id: str
    query: str
    collection: str
    phase: str  # warmup | cold | cache_hit
    source: str
    difficulty: str
    latency_wall_ms: float
    state: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    node_spans_ms: dict[str, float] = field(default_factory=dict)
    node_payload_bytes: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class ValidationRun:
    """Complete validation run metadata."""

    run_id: str
    git_sha: str
    started_at: datetime
    collections: list[str]
    skip_rerank_threshold: float
    relevance_threshold_rrf: float
    results: list[TraceResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------


def check_langfuse_config() -> None:
    """Preflight: verify Langfuse credentials are set. Fail-fast."""
    public = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret = os.getenv("LANGFUSE_SECRET_KEY", "")
    host = os.getenv("LANGFUSE_HOST", "")
    if not public:
        logger.error("LANGFUSE_PUBLIC_KEY not set — cannot authenticate Langfuse API")
        sys.exit(1)
    if not secret:
        logger.error("LANGFUSE_SECRET_KEY not set — cannot record traces")
        sys.exit(1)
    if not host:
        logger.error("LANGFUSE_HOST not set — cannot connect to Langfuse")
        sys.exit(1)
    try:
        # Fast auth probe: catches stale/invalid keys before long validation run.
        lf = Langfuse()
        lf.api.trace.list(limit=1)
    except Exception as e:
        logger.error("Langfuse auth check failed: %s", e)
        sys.exit(1)
    logger.info("Langfuse config OK: host=%s", host)


def check_worktree_clean(strict: bool = False) -> None:
    """Preflight: warn or fail if git worktree has uncommitted changes.

    Args:
        strict: If True, exit on dirty worktree. If False, log warning only.
    """
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        capture_output=True,
        text=True,
        check=False,
    )
    is_dirty = result.returncode != 0 or bool(result.stdout.strip())
    if is_dirty:
        msg = (
            "Dirty worktree detected — uncommitted changes may cause "
            "false positives in validation results"
        )
        if strict:
            logger.error(msg)
            sys.exit(1)
        else:
            logger.warning(msg)


def detect_runner_mode(collection: str) -> str:
    """Detect runner mode based on collection embedding requirements.

    Returns:
        'langgraph_bge' for BGE-M3 collections (gdrive_documents_bge).
        'voyage_compatible' for Voyage-embedded collections (contextual_bulgaria_voyage).
    """
    voyage_collections = {"contextual_bulgaria_voyage", "gdrive_documents_scalar"}
    if collection in voyage_collections:
        return "voyage_compatible"
    return "langgraph_bge"


def get_git_sha() -> str:
    """Get current git commit SHA."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _get_cache_version() -> str:
    """Resolve exact-cache key version from cache integration module."""
    try:
        from telegram_bot.integrations.cache import CACHE_VERSION

        return str(CACHE_VERSION)
    except Exception as e:
        logger.warning("Failed to resolve CACHE_VERSION, fallback to v3: %s", e)
        return "v3"


async def check_collection_available(qdrant_url: str, collection_name: str) -> bool:
    """Check if Qdrant collection exists."""
    from qdrant_client import AsyncQdrantClient

    client = AsyncQdrantClient(url=qdrant_url)
    try:
        exists = await client.collection_exists(collection_name)
        if not exists:
            logger.warning("Collection %s not found in Qdrant — skipping", collection_name)
        return exists
    finally:
        await client.close()


def check_voyage_available() -> bool:
    """Check if Voyage API key is available."""
    key = os.getenv("VOYAGE_API_KEY", "")
    if not key:
        logger.warning("VOYAGE_API_KEY not set — skipping Voyage-dependent collections")
    return bool(key)


async def discover_collections(qdrant_url: str) -> list[str]:
    """Discover available collections for validation."""
    available: list[str] = []
    for name in COLLECTIONS_TO_CHECK:
        if await check_collection_available(qdrant_url, name):
            # contextual_bulgaria_voyage needs Voyage API key
            if "voyage" in name and not check_voyage_available():
                logger.warning(
                    "Skipping %s: collection exists but VOYAGE_API_KEY not set",
                    name,
                )
                continue
            available.append(name)
    return available


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------


async def init_services(collection: str) -> dict[str, Any]:
    """Initialize LangGraph service dependencies (mirrors PropertyBot.__init__)."""
    from telegram_bot.graph.config import GraphConfig
    from telegram_bot.integrations.cache import CacheLayerManager
    from telegram_bot.integrations.embeddings import (
        BGEM3HybridEmbeddings,
        BGEM3SparseEmbeddings,
    )
    from telegram_bot.services.colbert_reranker import ColbertRerankerService
    from telegram_bot.services.qdrant import QdrantService

    config = GraphConfig.from_env()
    # Override collection for this validation run
    config.qdrant_collection = collection

    cache = CacheLayerManager(redis_url=config.redis_url)
    await cache.initialize()

    hybrid = BGEM3HybridEmbeddings(base_url=config.bge_m3_url)
    sparse = BGEM3SparseEmbeddings(base_url=config.bge_m3_url)

    qdrant = QdrantService(
        url=config.qdrant_url,
        collection_name=collection,
    )

    reranker = ColbertRerankerService(base_url=config.bge_m3_url)
    llm = config.create_llm()

    return {
        "cache": cache,
        "embeddings": hybrid,
        "sparse_embeddings": sparse,
        "qdrant": qdrant,
        "reranker": reranker,
        "llm": llm,
        "config": config,
    }


async def run_single_query(
    query: ValidationQuery,
    services: dict[str, Any],
    run_meta: dict[str, str],
    phase: str,
    *,
    message: Any | None = None,
) -> TraceResult:
    """Execute a single query through LangGraph pipeline with Langfuse tracing."""
    from telegram_bot.bot import _write_langfuse_scores
    from telegram_bot.graph.graph import build_graph
    from telegram_bot.graph.state import make_initial_state
    from telegram_bot.observability import get_client, observe, propagate_attributes

    config = services["config"]
    session_id = f"validate-{run_meta['run_id'][:8]}"
    trace_id = str(uuid.uuid4()).replace("-", "")

    state = make_initial_state(
        user_id=0,  # validation user
        session_id=session_id,
        query=query.text,
    )
    state["max_rewrite_attempts"] = config.max_rewrite_attempts

    wall_start = time.perf_counter()

    with propagate_attributes(
        session_id=session_id,
        user_id="validation",
        tags=["validation", phase, run_meta["collection"], run_meta["run_id"]],
    ):

        @observe(name="validation-query")
        async def _run() -> Any:
            # Force streaming when fake message provided, restore in finally
            orig_streaming = config.streaming_enabled
            if message is not None:
                config.streaming_enabled = True

            try:
                graph = build_graph(
                    cache=services["cache"],
                    embeddings=services["embeddings"],
                    sparse_embeddings=services["sparse_embeddings"],
                    qdrant=services["qdrant"],
                    reranker=services["reranker"],
                    llm=services["llm"],
                    message=message,
                )
                result = await graph.ainvoke(state)
                # Compute wall-time BEFORE writing scores so latency_total_ms is correct
                result["pipeline_wall_ms"] = (time.perf_counter() - wall_start) * 1000
                # Write metadata/scores while still inside active observation context
                lf = get_client()
                lf.update_current_trace(
                    input={"query": query.text},
                    output={"response": result.get("response", "")[:200]},
                    metadata={
                        "validation_run_id": run_meta["run_id"],
                        "git_sha": run_meta["git_sha"],
                        "collection": run_meta["collection"],
                        "query_set": query.source,
                        "query_difficulty": query.difficulty,
                        "phase": phase,
                        "skip_rerank_threshold": config.skip_rerank_threshold,
                        "relevance_threshold_rrf": config.relevance_threshold_rrf,
                    },
                )
                _write_langfuse_scores(lf, result)
                return result
            finally:
                config.streaming_enabled = orig_streaming

        result = await _run(langfuse_trace_id=trace_id)

    wall_ms = result.get("pipeline_wall_ms", (time.perf_counter() - wall_start) * 1000)

    logger.info(
        "  [%s] %.0fms | cache=%s rerank=%s results=%d | %s",
        phase,
        wall_ms,
        result.get("cache_hit", False),
        result.get("rerank_applied", False),
        result.get("search_results_count", 0),
        query.text[:60],
    )

    return TraceResult(
        trace_id=trace_id,
        query=query.text,
        collection=run_meta["collection"],
        phase=phase,
        source=query.source,
        difficulty=query.difficulty,
        latency_wall_ms=wall_ms,
        state={
            k: result.get(k)
            for k in [
                "cache_hit",
                "search_cache_hit",
                "embeddings_cache_hit",
                "rerank_applied",
                "search_results_count",
                "grade_confidence",
                "rewrite_count",
                "query_type",
                "skip_rerank",
                "latency_stages",
            ]
        },
    )


async def _flush_redis_caches(cache: Any) -> None:
    """Clear cache keys for cold run without dropping RediSearch index."""
    if not hasattr(cache, "redis") or not cache.redis:
        logger.warning("  Redis not available — cannot flush caches, cold run may be warm")
        return

    deleted = 0
    cache_version = _get_cache_version()
    patterns = [
        f"embeddings:{cache_version}:*",
        f"sparse:{cache_version}:*",
        f"analysis:{cache_version}:*",
        f"search:{cache_version}:*",
        f"rerank:{cache_version}:*",
        "conversation:*",
    ]
    for pattern in patterns:
        keys = [k async for k in cache.redis.scan_iter(match=pattern)]  # type: ignore[misc]
        if keys:
            deleted += len(keys)
            await cache.redis.delete(*keys)  # type: ignore[misc]

    # Semantic cache has its own key namespace and index lifecycle.
    if hasattr(cache, "semantic_cache") and cache.semantic_cache:
        try:
            await cache.semantic_cache.aclear()
        except Exception as e:
            logger.warning("  Semantic cache clear failed: %s", e)

    logger.info("  Redis cache key clear complete — deleted %d keys", deleted)


async def run_collection_validation(
    collection: str,
    run: ValidationRun,
) -> list[TraceResult]:
    """Run full validation for a single collection."""
    logger.info("=" * 60)
    logger.info("Validating collection: %s", collection)
    logger.info("=" * 60)

    runner_mode = detect_runner_mode(collection)
    if runner_mode == "voyage_compatible":
        logger.warning(
            "Collection %s requires Voyage-compatible runner (embedding mismatch with BGE-M3); "
            "skipping in current implementation",
            collection,
        )
        return []

    services = await init_services(collection)
    run_meta = {
        "run_id": run.run_id,
        "git_sha": run.git_sha,
        "collection": collection,
    }

    results: list[TraceResult] = []

    # Phase 1: Warmup (discard) — warms up connections, LLM, embeddings
    warmup_queries = get_warmup_queries(collection, count=3)
    logger.info("Phase 1: Warmup (%d queries, discarded)", len(warmup_queries))
    for q in warmup_queries:
        await run_single_query(q, services, run_meta, phase="warmup")

    # Phase 2: Cold run — flush caches for true cold measurement
    logger.info("Phase 2: Flushing Redis caches for true cold run...")
    await _flush_redis_caches(services["cache"])
    cold_queries = get_queries_for_collection(collection)
    logger.info("Phase 2: Cold run (%d queries)", len(cold_queries))
    for q in cold_queries:
        result = await run_single_query(q, services, run_meta, phase="cold")
        results.append(result)

    # Phase 3: Cache-hit run (duplicates from cold)
    cache_queries = get_cache_hit_queries(cold_queries, count=10)
    logger.info("Phase 3: Cache-hit run (%d queries)", len(cache_queries))
    for q in cache_queries:
        result = await run_single_query(q, services, run_meta, phase="cache_hit")
        results.append(result)

    # Phase 4: Streaming TTFT (first N cold queries, deterministic)
    # Note: semantic cache may return cached_response here, bypassing LLM streaming.
    # This is acceptable for MVP — TTFT=None for those queries, excluded from aggregates.
    streaming_queries = cold_queries[:STREAMING_QUERY_COUNT]
    logger.info("Phase 4: Streaming TTFT (%d queries)", len(streaming_queries))
    for q in streaming_queries:
        fake_msg = FakeMessage()
        result = await run_single_query(
            q,
            services,
            run_meta,
            phase="streaming",
            message=fake_msg,
        )
        if (
            fake_msg.t_answer_called is not None
            and fake_msg.sent is not None
            and fake_msg.sent.t_first_edit is not None
        ):
            ttft = (fake_msg.sent.t_first_edit - fake_msg.t_answer_called) * 1000
            if ttft >= 0:
                result.state["streaming_ttft_ms"] = ttft
        results.append(result)

    # Cleanup
    await services["cache"].close()
    await services["qdrant"].close()
    if hasattr(services["embeddings"], "aclose"):
        await services["embeddings"].aclose()
    if hasattr(services["sparse_embeddings"], "aclose"):
        await services["sparse_embeddings"].aclose()

    return results


# ---------------------------------------------------------------------------
# Langfuse enrichment
# ---------------------------------------------------------------------------


async def enrich_results_from_langfuse(
    run_id: str,
    results: list[TraceResult],
) -> list[TraceResult]:
    """Enrich TraceResult.scores and .node_spans_ms from Langfuse API.

    Fetches each trace by trace_id, populates scores dict and per-node
    span durations from observations.
    """
    lf = Langfuse()
    enriched = 0
    for r in results:
        if r.phase == "warmup":
            continue
        try:
            trace = lf.api.trace.get(r.trace_id)
            # Populate scores from Langfuse
            if hasattr(trace, "scores") and trace.scores:
                for score in trace.scores:
                    name = getattr(score, "name", "")
                    value = getattr(score, "value", 0)
                    if name:
                        r.scores[name] = float(value)
            # Populate node span durations and error count from observations
            observation_error_count = 0
            if hasattr(trace, "observations") and trace.observations:
                for obs in trace.observations:
                    level = getattr(obs, "level", None)
                    if level and str(level).upper().endswith("ERROR"):
                        observation_error_count += 1
                    obs_name = getattr(obs, "name", "") or ""
                    if not obs_name.startswith("node-"):
                        continue
                    node_name = obs_name.replace("node-", "").replace("-", "_")

                    def _json_size(value: Any) -> int:
                        if value is None:
                            return 0
                        try:
                            return len(json.dumps(value, ensure_ascii=False))
                        except Exception:
                            return len(str(value))

                    input_size = _json_size(getattr(obs, "input", None))
                    output_size = _json_size(getattr(obs, "output", None))
                    metadata_size = _json_size(getattr(obs, "metadata", None))
                    r.node_payload_bytes[node_name] = {
                        "input": input_size,
                        "output": output_size,
                        "metadata": metadata_size,
                        "total": input_size + output_size + metadata_size,
                    }

                    start_time = getattr(obs, "start_time", None)
                    end_time = getattr(obs, "end_time", None)
                    if start_time and end_time:
                        delta_ms = (end_time - start_time).total_seconds() * 1000
                        r.node_spans_ms[node_name] = delta_ms
            r.state["observation_error_count"] = observation_error_count
            enriched += 1
        except Exception as e:
            logger.warning("Failed to enrich trace %s: %s", r.trace_id, e)
    logger.info("Enriched %d/%d results from Langfuse", enriched, len(results))
    lf.flush()
    return results


def check_orphan_traces(results: list[TraceResult]) -> float:
    """Check for orphan traces (missing session_id in Langfuse).

    Returns fraction of traces that are orphans (0.0 = none, 1.0 = all).
    A trace is "orphan" if Langfuse has no session_id for it.
    """
    lf = Langfuse()
    total = 0
    orphans = 0
    for r in results:
        if r.phase == "warmup":
            continue
        total += 1
        try:
            trace = lf.api.trace.get(r.trace_id)
            session_id = getattr(trace, "session_id", None)
            if not session_id:
                orphans += 1
                logger.warning("Orphan trace (no session_id): %s", r.trace_id)
        except Exception as e:
            logger.warning("Failed to check trace %s: %s", r.trace_id, e)
    lf.flush()
    rate = orphans / total if total > 0 else 0.0
    logger.info("Orphan trace check: %d/%d (%.1f%%)", orphans, total, rate * 100)
    return rate


def evaluate_go_no_go(
    aggregates: dict[str, Any],
    results: list[TraceResult],
    orphan_rate: float = 0.0,
) -> dict[str, dict[str, Any]]:
    """Evaluate Go/No-Go criteria for Gate 1.

    Returns dict of criterion_name -> {target, actual, passed}.
    Criteria from issue #101 + roadmap Gate 1:
      1. cold_p50 < 5000ms
      2. cold_p90 < 8000ms
      3. cold queries > 10s < 15%
      4. cache_hit p50 < 1500ms
      5. p50 TTFT (generate node) < 2000ms
      6. rewrite calls >= 2 <= 10%
      7. rewrite completion_tokens p50 <= 96
      8. ERROR observations = 0 new
      9. orphan traces = 0%
    """
    cold = aggregates.get("cold", {})
    cache = aggregates.get("cache_hit", {})
    cold_results = [r for r in results if r.phase == "cold"]

    criteria: dict[str, dict[str, Any]] = {}

    # 1. Cold p50 < 5s
    cold_p50 = cold.get("latency_p50", 99999)
    criteria["cold_p50_lt_5s"] = {
        "target": "< 5000 ms",
        "actual": f"{cold_p50:.0f} ms",
        "passed": cold_p50 < 5000,
    }

    # 2. Cold p90 < 8s (fallback to p95 for backward compatibility)
    cold_p90 = cold.get("latency_p90", cold.get("latency_p95", 99999))
    criteria["cold_p90_lt_8s"] = {
        "target": "< 8000 ms",
        "actual": f"{cold_p90:.0f} ms",
        "passed": cold_p90 < 8000,
    }

    # 3. Cold queries > 10s < 15%
    if cold_results:
        over_10s = sum(1 for r in cold_results if r.latency_wall_ms > 10000)
        pct_over_10s = over_10s / len(cold_results)
    else:
        over_10s = 0
        pct_over_10s = 0.0
    criteria["cold_over_10s_lt_15pct"] = {
        "target": "< 15%",
        "actual": f"{pct_over_10s:.1%} ({over_10s}/{len(cold_results)})",
        "passed": pct_over_10s < 0.15,
    }

    # 4. Cache-hit p50 < 1.5s
    cache_p50 = cache.get("latency_p50", 99999)
    criteria["cache_hit_p50_lt_1500ms"] = {
        "target": "< 1500 ms",
        "actual": f"{cache_p50:.0f} ms",
        "passed": cache_p50 < 1500,
    }

    # 5. Generate node p50 < 2s (full generation latency, non-streaming mode)
    generate_p50 = cold.get("node_p50", {}).get("generate", 99999)
    criteria["generate_p50_lt_2s"] = {
        "target": "< 2000 ms",
        "actual": f"{generate_p50:.0f} ms",
        "passed": generate_p50 < 2000,
    }

    # 6. Rewrite calls >= 2 <= 10%
    if cold_results:
        multi_rewrite = sum(1 for r in cold_results if (r.state.get("rewrite_count", 0) or 0) >= 2)
        multi_rewrite_pct = multi_rewrite / len(cold_results)
    else:
        multi_rewrite_pct = 0.0
    criteria["multi_rewrite_le_10pct"] = {
        "target": "<= 10%",
        "actual": f"{multi_rewrite_pct:.1%}",
        "passed": multi_rewrite_pct <= 0.10,
    }

    # 7. Rewrite completion_tokens p50 <= 96 (from Langfuse scores if available)
    rewrite_tokens: list[float] = []
    for r in cold_results:
        if "rewrite_completion_tokens" in r.scores:
            rewrite_tokens.append(r.scores["rewrite_completion_tokens"])
    tokens_p50 = float(np.percentile(rewrite_tokens, 50)) if rewrite_tokens else 0.0
    criteria["rewrite_tokens_p50_le_96"] = {
        "target": "<= 96 tokens",
        "actual": f"{tokens_p50:.0f} tokens" if rewrite_tokens else "N/A (no rewrites)",
        "passed": tokens_p50 <= 96,
    }

    # 8. ERROR observations = 0 new (from scores + observation levels)
    score_error_count = sum(
        1
        for r in results
        if r.phase != "warmup"
        and any(v for k, v in r.scores.items() if "error" in k.lower() and v > 0)
    )
    observation_error_count = sum(
        int(r.state.get("observation_error_count", 0) or 0) for r in results if r.phase != "warmup"
    )
    error_count = score_error_count + observation_error_count
    criteria["zero_errors"] = {
        "target": "0",
        "actual": f"{error_count} (scores={score_error_count}, observations={observation_error_count})",
        "passed": error_count == 0,
    }

    # 9. Orphan traces = 0%
    criteria["orphan_traces_zero"] = {
        "target": "0%",
        "actual": f"{orphan_rate:.1%}",
        "passed": orphan_rate == 0.0,
    }

    # 10. Streaming TTFT p50 < 1000ms (skipped if sample < 3)
    streaming = aggregates.get("streaming", {})
    ttft_p50 = streaming.get("ttft_p50")
    ttft_n = streaming.get("ttft_sample_count", 0)

    if ttft_n < 3:
        criteria["ttft_p50_lt_1000ms"] = {
            "target": "< 1000 ms",
            "actual": f"N/A (n={ttft_n}, need >= 3)",
            "passed": True,
            "skipped": True,
        }
    else:
        criteria["ttft_p50_lt_1000ms"] = {
            "target": "< 1000 ms",
            "actual": f"{ttft_p50:.0f} ms (n={ttft_n})",
            "passed": ttft_p50 < 1000,
            "skipped": False,
        }

    return criteria


async def fetch_reference_trace_metrics(
    reference_trace_id: str,
) -> dict[str, Any] | None:
    """Fetch metrics from reference trace for comparison.

    Returns dict with latency_total_ms, rerank_applied, results_count etc.
    """
    try:
        lf = Langfuse()
        trace = lf.api.trace.get(reference_trace_id)
        metrics: dict[str, Any] = {}
        if hasattr(trace, "scores") and trace.scores:
            for score in trace.scores:
                name = getattr(score, "name", "")
                value = getattr(score, "value", 0)
                if name:
                    metrics[name] = float(value)
        lf.flush()
        return metrics if metrics else None
    except Exception as e:
        logger.warning("Failed to fetch reference trace %s: %s", reference_trace_id, e)
        return None


# ---------------------------------------------------------------------------
# Aggregation and reporting
# ---------------------------------------------------------------------------


def compute_aggregates(results: list[TraceResult]) -> dict[str, Any]:
    """Compute p50/p95/mean/max aggregates, split by phase."""
    aggregates: dict[str, Any] = {}

    for phase in ["cold", "cache_hit"]:
        phase_results = [r for r in results if r.phase == phase]
        if not phase_results:
            continue

        latencies = [r.latency_wall_ms for r in phase_results]
        agg: dict[str, Any] = {
            "n": len(phase_results),
            "latency_p50": float(np.percentile(latencies, 50)),
            "latency_p90": float(np.percentile(latencies, 90)),
            "latency_p95": float(np.percentile(latencies, 95)),
            "latency_mean": float(np.mean(latencies)),
            "latency_max": float(np.max(latencies)),
        }

        # Rates from Langfuse score fields (fallback to local state if score missing)
        def score_rate(
            score_name: str,
            state_fallback: str | None = None,
            _results: list[TraceResult] = phase_results,
        ) -> float:
            vals: list[float] = []
            for r in _results:
                if score_name in r.scores:
                    vals.append(1.0 if r.scores[score_name] >= 0.5 else 0.0)
                elif state_fallback is not None:
                    vals.append(1.0 if r.state.get(state_fallback) else 0.0)
            return float(np.mean(vals)) if vals else 0.0

        agg["semantic_cache_hit_rate"] = score_rate("semantic_cache_hit", "cache_hit")
        agg["search_cache_hit_rate"] = score_rate("search_cache_hit", "search_cache_hit")
        agg["embeddings_cache_hit_rate"] = score_rate(
            "embeddings_cache_hit", "embeddings_cache_hit"
        )
        agg["rerank_applied_rate"] = score_rate("rerank_applied", "rerank_applied")
        agg["rewrite_rate"] = float(
            np.mean(
                [1.0 if (r.state.get("rewrite_count", 0) or 0) > 0 else 0.0 for r in phase_results]
            )
        )

        # Avg results count
        counts = [r.state.get("search_results_count", 0) for r in phase_results]
        agg["results_count_mean"] = float(np.mean(counts)) if counts else 0.0

        # Per-node latency p50/p95 (prefer Langfuse spans, fallback to state latency_stages)
        node_names = [
            "classify",
            "cache_check",
            "retrieve",
            "grade",
            "rerank",
            "generate",
            "rewrite",
            "cache_store",
            "respond",
        ]
        node_latencies: dict[str, list[float]] = {n: [] for n in node_names}
        for r in phase_results:
            if r.node_spans_ms:
                for node, ms in r.node_spans_ms.items():
                    if node in node_latencies:
                        node_latencies[node].append(ms)
                continue
            stages = r.state.get("latency_stages") or {}
            for node in node_names:
                if node in stages:
                    node_latencies[node].append(stages[node] * 1000)  # sec → ms

        agg["node_p50"] = {}
        agg["node_p95"] = {}
        for node in node_names:
            vals = node_latencies[node]
            if vals:
                agg["node_p50"][node] = float(np.percentile(vals, 50))
                agg["node_p95"][node] = float(np.percentile(vals, 95))

        aggregates[phase] = agg

    # Streaming TTFT aggregation (separate from cold/cache_hit latency stats)
    streaming_results = [r for r in results if r.phase == "streaming"]
    ttft_values: list[float] = []
    for r in streaming_results:
        ttft = r.state.get("streaming_ttft_ms")
        if isinstance(ttft, bool) or not isinstance(ttft, int | float):
            continue
        ttft_values.append(float(ttft))
    if ttft_values:
        aggregates["streaming"] = {
            "n": len(streaming_results),
            "ttft_sample_count": len(ttft_values),
            "ttft_p50": float(np.percentile(ttft_values, 50)),
            "ttft_p95": float(np.percentile(ttft_values, 95)),
            "ttft_mean": float(np.mean(ttft_values)),
            "ttft_max": float(np.max(ttft_values)),
        }

    return aggregates


def aggregate_node_payloads(results: list[TraceResult]) -> dict[str, dict[str, float]]:
    """Aggregate per-node payload sizes from Langfuse observations (bytes)."""
    buckets: dict[str, dict[str, list[float]]] = {}
    for r in results:
        if r.phase == "warmup":
            continue
        for node_name, payload in (r.node_payload_bytes or {}).items():
            node = buckets.setdefault(
                node_name,
                {"input": [], "output": [], "metadata": [], "total": []},
            )
            node["input"].append(float(payload.get("input", 0)))
            node["output"].append(float(payload.get("output", 0)))
            node["metadata"].append(float(payload.get("metadata", 0)))
            node["total"].append(float(payload.get("total", 0)))

    summary: dict[str, dict[str, float]] = {}
    for node_name, series in buckets.items():
        if not series["total"]:
            continue
        summary[node_name] = {
            "count": float(len(series["total"])),
            "input_p50": float(np.percentile(series["input"], 50)),
            "output_p50": float(np.percentile(series["output"], 50)),
            "metadata_p50": float(np.percentile(series["metadata"], 50)),
            "total_p50": float(np.percentile(series["total"], 50)),
            "input_max": float(np.max(series["input"])),
            "output_max": float(np.max(series["output"])),
            "metadata_max": float(np.max(series["metadata"])),
            "total_max": float(np.max(series["total"])),
        }
    return summary


def format_phase_summary(phase: str, agg: dict[str, Any]) -> str:
    """Format one-line phase summary for console logs."""
    return (
        f"{phase} (n={agg['n']}): p50={agg['latency_p50']:.0f}ms "
        f"p90={agg.get('latency_p90', agg['latency_p95']):.0f}ms "
        f"p95={agg['latency_p95']:.0f}ms mean={agg['latency_mean']:.0f}ms"
    )


def resolve_report_collections(
    discovered_collections: list[str],
    results: list[TraceResult],
) -> list[str]:
    """Resolve collections for report output from actually validated traces."""
    if not discovered_collections:
        return []

    seen = {r.collection for r in results if r.phase != "warmup"}
    if not seen:
        return discovered_collections

    validated = [c for c in discovered_collections if c in seen]
    return validated or discovered_collections


def generate_report(
    run: ValidationRun,
    aggregates: dict[str, Any],
    output_path: Path,
    reference_metrics: dict[str, Any] | None = None,
    go_no_go: dict[str, dict[str, Any]] | None = None,
    payload_summary: dict[str, dict[str, float]] | None = None,
) -> None:
    """Generate markdown validation report."""
    lines: list[str] = []
    lines.append("# Trace Validation Report")
    lines.append("")
    lines.append(f"**Run ID:** `{run.run_id}`")
    lines.append(f"**Git SHA:** `{run.git_sha}`")
    lines.append(f"**Date:** {run.started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"**Collections:** {', '.join(run.collections)}")
    lines.append(f"**skip_rerank_threshold:** {run.skip_rerank_threshold}")
    lines.append(f"**Reference trace:** `{REFERENCE_TRACE_ID}`")
    lines.append("")

    if reference_metrics:
        lines.append("## Reference Trace Comparison")
        lines.append("")
        lines.append("| Metric | Reference c2b95d86 | Cold p50 | Cold p95 | Cache p50 |")
        lines.append("|--------|--------------------|----------|----------|-----------|")
        lines.append(
            "| latency_total_ms | "
            f"{reference_metrics.get('latency_total_ms', 0):.0f} | "
            f"{aggregates.get('cold', {}).get('latency_p50', 0):.0f} | "
            f"{aggregates.get('cold', {}).get('latency_p95', 0):.0f} | "
            f"{aggregates.get('cache_hit', {}).get('latency_p50', 0):.0f} |"
        )
        lines.append(
            "| rerank_applied | "
            f"{reference_metrics.get('rerank_applied', 0):.0f} | "
            f"{aggregates.get('cold', {}).get('rerank_applied_rate', 0):.0%} | - | "
            f"{aggregates.get('cache_hit', {}).get('rerank_applied_rate', 0):.0%} |"
        )
        lines.append("")

    # Summary table per phase
    for phase_name, phase_label in [("cold", "Cold Run"), ("cache_hit", "Cache-Hit Run")]:
        agg = aggregates.get(phase_name)
        if not agg:
            continue

        lines.append(f"## {phase_label} (n={agg['n']})")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| latency p50 | {agg['latency_p50']:.0f} ms |")
        lines.append(f"| latency p90 | {agg.get('latency_p90', agg['latency_p95']):.0f} ms |")
        lines.append(f"| latency p95 | {agg['latency_p95']:.0f} ms |")
        lines.append(f"| latency mean | {agg['latency_mean']:.0f} ms |")
        lines.append(f"| latency max | {agg['latency_max']:.0f} ms |")
        lines.append(f"| semantic_cache_hit rate | {agg['semantic_cache_hit_rate']:.0%} |")
        lines.append(f"| search_cache_hit rate | {agg['search_cache_hit_rate']:.0%} |")
        lines.append(f"| rerank_applied rate | {agg['rerank_applied_rate']:.0%} |")
        lines.append(f"| rewrite rate | {agg['rewrite_rate']:.0%} |")
        lines.append(f"| results_count mean | {agg['results_count_mean']:.1f} |")
        lines.append("")

        # Node-level latencies
        if agg.get("node_p50"):
            lines.append(f"### Node Latencies ({phase_label})")
            lines.append("")
            lines.append("| Node | p50 (ms) | p95 (ms) |")
            lines.append("|------|----------|----------|")
            for node in agg["node_p50"]:
                p50 = agg["node_p50"][node]
                p95 = agg.get("node_p95", {}).get(node, 0)
                lines.append(f"| {node} | {p50:.0f} | {p95:.0f} |")
            lines.append("")

    # Streaming TTFT section
    streaming_agg = aggregates.get("streaming")
    if streaming_agg:
        lines.append(f"## Streaming TTFT (n={streaming_agg['n']})")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| ttft p50 | {streaming_agg['ttft_p50']:.0f} ms |")
        lines.append(f"| ttft p95 | {streaming_agg['ttft_p95']:.0f} ms |")
        lines.append(f"| ttft mean | {streaming_agg['ttft_mean']:.0f} ms |")
        lines.append(f"| ttft max | {streaming_agg['ttft_max']:.0f} ms |")
        lines.append(f"| sample count | {streaming_agg['ttft_sample_count']} |")
        lines.append("")

    # All trace details
    lines.append("## Trace Details")
    lines.append("")
    lines.append("| Phase | Query (truncated) | Latency (ms) | Cache | Rerank | Results |")
    lines.append("|-------|-------------------|-------------|-------|--------|---------|")
    for r in run.results:
        if r.phase == "warmup":
            continue
        cache = "HIT" if r.state.get("cache_hit") else "miss"
        rerank = "yes" if r.state.get("rerank_applied") else "no"
        results_count = r.state.get("search_results_count", 0)
        lines.append(
            f"| {r.phase} | {r.query[:50]} | {r.latency_wall_ms:.0f} | "
            f"{cache} | {rerank} | {results_count} |"
        )
    lines.append("")

    # Go/No-Go
    lines.append("## Go/No-Go Recommendation")
    lines.append("")
    if go_no_go:
        all_passed = all(c["passed"] for c in go_no_go.values())
        verdict = "GO — all criteria passed" if all_passed else "NO-GO — see failures below"
        lines.append(f"**Verdict: {verdict}**")
        lines.append("")
        lines.append("| # | Criterion | Target | Actual | Status |")
        lines.append("|---|-----------|--------|--------|--------|")
        for i, (name, c) in enumerate(go_no_go.items(), 1):
            if c.get("skipped"):
                status = "[-] SKIP"
            elif c["passed"]:
                status = "[x] PASS"
            else:
                status = "[ ] **FAIL**"
            lines.append(f"| {i} | {name} | {c['target']} | {c['actual']} | {status} |")
        lines.append("")
        passed = sum(1 for c in go_no_go.values() if c["passed"])
        lines.append(f"**Score: {passed}/{len(go_no_go)} criteria passed**")
        lines.append("")
        lines.append(
            "_Note: `generate_p50_lt_2s` measures full generation latency in "
            "non-streaming mode. `ttft_p50_lt_1000ms` measures real first-token "
            "latency from the streaming phase._"
        )
    else:
        lines.append("<!-- Go/No-Go data not available — run with --report -->")
    lines.append("")

    if payload_summary:
        lines.append("## Node Payload Sizes (Bytes, p50)")
        lines.append("")
        lines.append("| Node | Input p50 | Output p50 | Metadata p50 | Total p50 |")
        lines.append("|------|-----------|------------|--------------|-----------|")
        for node in sorted(payload_summary.keys()):
            p = payload_summary[node]
            lines.append(
                f"| {node} | {p['input_p50']:.0f} | {p['output_p50']:.0f} | "
                f"{p['metadata_p50']:.0f} | {p['total_p50']:.0f} |"
            )
        lines.append("")
        lines.append(
            "_Note: metadata is SDK-level envelope metadata. "
            "Use input/output columns to validate curated node payloads._"
        )
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    logger.info("Report saved to %s", output_path)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


async def run_validation(args: argparse.Namespace) -> None:
    """Main validation orchestrator."""
    run_id = str(uuid.uuid4())
    git_sha = get_git_sha()

    from telegram_bot.graph.config import GraphConfig

    config = GraphConfig.from_env()
    check_langfuse_config()  # fail fast if host/keys are missing
    check_worktree_clean(strict=args.strict_worktree)

    run = ValidationRun(
        run_id=run_id,
        git_sha=git_sha,
        started_at=datetime.now(UTC),
        collections=[],
        skip_rerank_threshold=config.skip_rerank_threshold,
        relevance_threshold_rrf=config.relevance_threshold_rrf,
    )

    logger.info("Starting validation run: %s", run_id)
    logger.info("Git SHA: %s", git_sha)
    logger.info("skip_rerank_threshold: %s (from env/config)", config.skip_rerank_threshold)
    logger.info("relevance_threshold_rrf: %s (from env/config)", config.relevance_threshold_rrf)

    # Discover available collections
    qdrant_url = config.qdrant_url
    if args.collection:
        # User specified a single collection
        if await check_collection_available(qdrant_url, args.collection):
            collections = [args.collection]
        else:
            logger.error("Collection %s not found, aborting", args.collection)
            sys.exit(1)
    else:
        collections = await discover_collections(qdrant_url)

    if not collections:
        logger.error("No collections available for validation, aborting")
        sys.exit(1)

    logger.info("Collections to validate: %s", collections)

    # Run validation per collection
    all_results: list[TraceResult] = []
    for collection in collections:
        results = await run_collection_validation(collection, run)
        all_results.extend(results)

    if not all_results:
        logger.error("No traces collected (all collections skipped or failed), aborting")
        sys.exit(1)

    validated_collections = resolve_report_collections(collections, all_results)
    skipped = set(collections) - set(validated_collections)
    if skipped:
        logger.warning("Collections discovered but skipped (no traces): %s", sorted(skipped))

    run.collections = validated_collections
    run.results = all_results

    # Flush Langfuse
    logger.info("Flushing Langfuse queue...")
    try:
        from telegram_bot.observability import get_langfuse_client

        lf_client = get_langfuse_client()
        if lf_client:
            lf_client.flush()
    except Exception:
        pass
    await asyncio.sleep(5)  # extra wait for async flush

    # Enrich results from Langfuse API (scores + node spans) before aggregates
    all_results = await enrich_results_from_langfuse(run_id, all_results)
    run.results = all_results
    reference_metrics = await fetch_reference_trace_metrics(REFERENCE_TRACE_ID)

    # Compute aggregates
    aggregates = compute_aggregates(all_results)
    payload_summary = aggregate_node_payloads(all_results)

    # Check orphan traces
    logger.info("Checking orphan traces...")
    orphan_rate = check_orphan_traces(all_results)

    # Evaluate Go/No-Go criteria
    go_no_go = evaluate_go_no_go(aggregates, all_results, orphan_rate=orphan_rate)
    all_passed = all(c["passed"] for c in go_no_go.values())
    passed_count = sum(1 for c in go_no_go.values() if c["passed"])
    logger.info(
        "Go/No-Go: %s (%d/%d criteria passed)",
        "GO" if all_passed else "NO-GO",
        passed_count,
        len(go_no_go),
    )
    for name, c in go_no_go.items():
        if c.get("skipped"):
            status = "SKIP"
        elif c["passed"]:
            status = "PASS"
        else:
            status = "FAIL"
        logger.info("  [%s] %s: %s (target: %s)", status, name, c["actual"], c["target"])

    # Print summary to console
    for phase, agg in aggregates.items():
        if phase == "streaming":
            continue  # handled separately below
        logger.info("%s", format_phase_summary(phase, agg))

    # Streaming TTFT summary
    streaming_agg = aggregates.get("streaming")
    if streaming_agg:
        logger.info(
            "streaming TTFT (n=%d, samples=%d): p50=%.0fms p95=%.0fms mean=%.0fms",
            streaming_agg["n"],
            streaming_agg["ttft_sample_count"],
            streaming_agg["ttft_p50"],
            streaming_agg["ttft_p95"],
            streaming_agg["ttft_mean"],
        )

    # Generate report
    if args.report:
        report_path = Path(
            f"docs/reports/{run.started_at.strftime('%Y-%m-%d')}-validation-{run_id[:8]}.md"
        )
        generate_report(
            run,
            aggregates,
            report_path,
            reference_metrics=reference_metrics,
            go_no_go=go_no_go,
            payload_summary=payload_summary,
        )

    # Also dump raw JSON for programmatic use
    raw_path = Path(
        f"docs/reports/{run.started_at.strftime('%Y-%m-%d')}-validation-{run_id[:8]}.json"
    )
    raw_data = {
        "run_id": run.run_id,
        "git_sha": run.git_sha,
        "started_at": run.started_at.isoformat(),
        "collections": run.collections,
        "collections_discovered": collections,
        "collections_validated": validated_collections,
        "collections_skipped": sorted(skipped),
        "skip_rerank_threshold": run.skip_rerank_threshold,
        "relevance_threshold_rrf": run.relevance_threshold_rrf,
        "aggregates": aggregates,
        "go_no_go": go_no_go,
        "payload_summary": payload_summary,
        "orphan_rate": orphan_rate,
        "reference_trace_id": REFERENCE_TRACE_ID,
        "reference_metrics": reference_metrics,
        "traces": [
            {
                "trace_id": r.trace_id,
                "query": r.query,
                "collection": r.collection,
                "phase": r.phase,
                "source": r.source,
                "difficulty": r.difficulty,
                "latency_wall_ms": r.latency_wall_ms,
                "state": r.state,
                "scores": r.scores,
                "node_spans_ms": r.node_spans_ms,
                "node_payload_bytes": r.node_payload_bytes,
            }
            for r in all_results
            if r.phase != "warmup"
        ],
    }
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(raw_data, indent=2, default=str))
    logger.info("Raw data saved to %s", raw_path)


def main() -> None:
    load_dotenv()  # Load .env before checking Langfuse config
    parser = argparse.ArgumentParser(description="Trace validation runner")
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help="Validate specific collection only",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate markdown report",
    )
    parser.add_argument(
        "--strict-worktree",
        action="store_true",
        default=False,
        help="Fail if git worktree is dirty (default: warn only)",
    )
    args = parser.parse_args()
    asyncio.run(run_validation(args))


if __name__ == "__main__":
    main()
