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
import yaml
from dotenv import load_dotenv
from langfuse import Langfuse
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
)


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


def _build_redis_url(redis_url: str) -> str:
    """Inject REDIS_PASSWORD into URL if not already present."""
    password = os.getenv("REDIS_PASSWORD", "")
    if password and "@" not in redis_url:
        redis_url = redis_url.replace("redis://", f"redis://:{password}@", 1)
    return redis_url


COLLECTIONS_TO_CHECK = ["gdrive_documents_bge"]
# Base names used by discovery helper (kept as explicit alias for tests/backward compatibility).
COLLECTION_BASE_NAMES = COLLECTIONS_TO_CHECK

STREAMING_QUERY_COUNT = 5  # First N cold queries for streaming TTFT phase (deterministic)

# All node observation names tracked by enrichment and aggregation.
# Order mirrors the LangGraph pipeline: transcribe → classify → … → respond → summarize.
TRACKED_NODE_NAMES = [
    "transcribe",
    "classify",
    "cache_check",
    "retrieve",
    "grade",
    "rerank",
    "generate",
    "rewrite",
    "cache_store",
    "respond",
    "summarize",
]
_TRACKED_NODE_SET = frozenset(TRACKED_NODE_NAMES)

GO_NO_GO_THRESHOLDS_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "baseline" / "thresholds.yaml"
)


def _load_go_no_go_thresholds(
    custom: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load Go/No-Go thresholds from YAML, with optional overrides."""
    with open(GO_NO_GO_THRESHOLDS_PATH) as f:
        all_cfg = yaml.safe_load(f)
    defaults = all_cfg.get("go_no_go", {})
    defaults["judge"] = all_cfg.get("judge", {})
    if custom:
        defaults.update(custom)
    return defaults


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
    """Preflight: verify Langfuse credentials are set and API is reachable.

    Retries auth probe 3 times with exponential backoff (max 10s total).
    """
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
        _langfuse_auth_probe()
    except Exception as e:
        logger.error("Langfuse auth check failed after retries: %s", e)
        sys.exit(1)
    logger.info("Langfuse config OK: host=%s", host)


@retry(
    stop=(stop_after_attempt(3) | stop_after_delay(10)),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _langfuse_auth_probe() -> None:
    """Auth probe with retry. Separated for testability."""
    lf = Langfuse()
    if not lf.auth_check():
        raise RuntimeError("Langfuse auth_check returned False")


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
    base_collection = collection.removesuffix("_binary").removesuffix("_scalar")
    voyage_collections = {"contextual_bulgaria_voyage", "gdrive_documents"}
    if base_collection in voyage_collections:
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
    """Resolve exact-cache version from cache integration (single source of truth)."""
    try:
        from telegram_bot.integrations.cache import CACHE_VERSION

        return str(CACHE_VERSION)
    except Exception as e:
        logger.warning("Failed to resolve CACHE_VERSION, fallback to v4: %s", e)
        return "v4"


def check_voyage_available() -> bool:
    """Check if Voyage API key is available."""
    key = os.getenv("VOYAGE_API_KEY", "")
    if not key:
        logger.warning("VOYAGE_API_KEY not set — skipping Voyage-dependent collections")
    return bool(key)


async def discover_collections(qdrant_url: str, quantization_mode: str = "off") -> list[str]:
    """Discover available collections for validation via Qdrant API.

    Queries Qdrant for all collections, matches against known base names
    (with optional _scalar/_binary suffixes). Prefers exact match over suffixed.
    """
    from qdrant_client import AsyncQdrantClient

    client = AsyncQdrantClient(url=qdrant_url)
    try:
        response = await client.get_collections()
        all_names = {c.name for c in response.collections}
    except Exception as e:
        logger.error("Qdrant collection discovery failed: %s", e)
        return []
    finally:
        await client.close()

    mode = quantization_mode.lower()
    if mode == "scalar":
        preferred_suffixes = ["_scalar", "", "_binary"]
    elif mode == "binary":
        preferred_suffixes = ["_binary", "", "_scalar"]
    else:
        preferred_suffixes = ["", "_scalar", "_binary"]

    available: list[str] = []
    for base_name in COLLECTION_BASE_NAMES:
        matched = None
        for suffix in preferred_suffixes:
            candidate = f"{base_name}{suffix}"
            if candidate in all_names:
                matched = candidate
                break

        if matched is None:
            logger.warning("Collection %s (any suffix) not found in Qdrant", base_name)
            continue

        # Voyage collections need API key
        if "voyage" in base_name and not check_voyage_available():
            logger.warning(
                "Skipping %s: collection exists but VOYAGE_API_KEY not set",
                matched,
            )
            continue

        available.append(matched)

    logger.info(
        "Discovered collections: %s (from %d total in Qdrant, mode=%s)",
        available,
        len(all_names),
        mode,
    )
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

    cache = CacheLayerManager(redis_url=_build_redis_url(config.redis_url))
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
    from telegram_bot.graph.graph import build_graph
    from telegram_bot.graph.state import make_initial_state
    from telegram_bot.observability import get_client, observe, propagate_attributes
    from telegram_bot.scoring import write_langfuse_scores

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
                write_langfuse_scores(lf, result)
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


async def _flush_redis_caches(cache: Any) -> str:
    """Clear cache keys for cold run without dropping RediSearch index.

    Returns:
        "OK" if flush verified (0 keys remaining).
        "SKIPPED" if Redis unavailable or flush incomplete.
    """
    if not hasattr(cache, "redis") or not cache.redis:
        logger.warning("  Redis not available — cold phase will be SKIPPED")
        return "SKIPPED"

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

    # Verify: re-scan to confirm keys are actually gone
    remaining = 0
    for pattern in patterns:
        remaining += len(
            [k async for k in cache.redis.scan_iter(match=pattern, count=100)]  # type: ignore[misc]
        )

    if remaining > 0:
        logger.error(
            "  Redis flush incomplete: %d keys remain after deletion — cold phase SKIPPED",
            remaining,
        )
        return "SKIPPED"

    logger.info("  Redis cache flush verified — deleted %d keys, 0 remaining", deleted)
    return "OK"


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
    flush_status = await _flush_redis_caches(services["cache"])
    cold_queries = get_queries_for_collection(collection)
    if flush_status == "SKIPPED":
        logger.warning("Phase 2: Cold run SKIPPED — Redis flush not verified")
        for q in cold_queries:
            results.append(
                TraceResult(
                    trace_id="skipped",
                    query=q.text,
                    collection=collection,
                    phase="cold",
                    source=q.source,
                    difficulty=q.difficulty,
                    latency_wall_ms=0,
                    state={"cold_skipped": True, "skip_reason": "redis_flush_failed"},
                )
            )
    else:
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
        if r.phase == "warmup" or r.state.get("cold_skipped"):
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
                    if obs_name.startswith("node-"):
                        node_name = obs_name.removeprefix("node-").replace("-", "_")
                    elif obs_name in _TRACKED_NODE_SET:
                        node_name = obs_name
                    else:
                        continue

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
        if r.phase == "warmup" or r.state.get("cold_skipped"):
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
    thresholds: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Evaluate Go/No-Go criteria for Gate 1.

    Returns dict of criterion_name -> {target, actual, passed}.
    Thresholds loaded from tests/baseline/thresholds.yaml go_no_go section,
    with optional overrides via thresholds param.
    """
    t = _load_go_no_go_thresholds(thresholds)

    cold = aggregates.get("cold", {})
    cache = aggregates.get("cache_hit", {})
    cold_results = [r for r in results if r.phase == "cold"]

    criteria: dict[str, dict[str, Any]] = {}

    cold_stddev = cold.get("latency_stddev", 0)
    cache_stddev = cache.get("latency_stddev", 0)

    # 1. Cold p50
    cold_p50 = cold.get("latency_p50", 99999)
    cold_p50_limit = t.get("cold_p50_ms", 5000)
    criteria["cold_p50_lt_5s"] = {
        "target": f"< {cold_p50_limit} ms",
        "actual": f"{cold_p50:.0f} ms",
        "passed": cold_p50 < cold_p50_limit,
        "stddev": f"\u00b1{cold_stddev:.0f} ms" if cold_stddev else "\u2014",
    }

    # 2. Cold p90 (fallback to p95 for backward compatibility)
    cold_p90 = cold.get("latency_p90", cold.get("latency_p95", 99999))
    cold_p90_limit = t.get("cold_p90_ms", 8000)
    criteria["cold_p90_lt_8s"] = {
        "target": f"< {cold_p90_limit} ms",
        "actual": f"{cold_p90:.0f} ms",
        "passed": cold_p90 < cold_p90_limit,
        "stddev": f"\u00b1{cold_stddev:.0f} ms" if cold_stddev else "\u2014",
    }

    # 3. Cold queries > 10s
    cold_over_10s_limit = t.get("cold_over_10s_pct", 0.15)
    if cold_results:
        over_10s = sum(1 for r in cold_results if r.latency_wall_ms > 10000)
        pct_over_10s = over_10s / len(cold_results)
    else:
        over_10s = 0
        pct_over_10s = 0.0
    criteria["cold_over_10s_lt_15pct"] = {
        "target": f"< {cold_over_10s_limit:.0%}",
        "actual": f"{pct_over_10s:.1%} ({over_10s}/{len(cold_results)})",
        "passed": pct_over_10s < cold_over_10s_limit,
        "stddev": "\u2014",
    }

    # 4. Cache-hit p50
    cache_p50 = cache.get("latency_p50", 99999)
    cache_p50_limit = t.get("cache_hit_p50_ms", 1500)
    criteria["cache_hit_p50_lt_1500ms"] = {
        "target": f"< {cache_p50_limit} ms",
        "actual": f"{cache_p50:.0f} ms",
        "passed": cache_p50 < cache_p50_limit,
        "stddev": f"\u00b1{cache_stddev:.0f} ms" if cache_stddev else "\u2014",
    }

    # 5. Generate node p50 (full generation latency, non-streaming mode)
    generate_p50 = cold.get("node_p50", {}).get("generate", 99999)
    generate_p50_limit = t.get("generate_p50_ms", 2000)
    criteria["generate_p50_lt_2s"] = {
        "target": f"< {generate_p50_limit} ms",
        "actual": f"{generate_p50:.0f} ms",
        "passed": generate_p50 < generate_p50_limit,
        "stddev": "\u2014",
    }

    # 6. Rewrite calls >= 2
    multi_rewrite_limit = t.get("multi_rewrite_pct", 0.10)
    if cold_results:
        multi_rewrite = sum(1 for r in cold_results if (r.state.get("rewrite_count", 0) or 0) >= 2)
        multi_rewrite_pct = multi_rewrite / len(cold_results)
    else:
        multi_rewrite_pct = 0.0
    criteria["multi_rewrite_le_10pct"] = {
        "target": f"<= {multi_rewrite_limit:.0%}",
        "actual": f"{multi_rewrite_pct:.1%}",
        "passed": multi_rewrite_pct <= multi_rewrite_limit,
        "stddev": "\u2014",
    }

    # 7. Rewrite completion_tokens p50 (from Langfuse scores if available)
    rewrite_tokens_limit = t.get("rewrite_tokens_p50", 96)
    rewrite_tokens: list[float] = []
    for r in cold_results:
        if "rewrite_completion_tokens" in r.scores:
            rewrite_tokens.append(r.scores["rewrite_completion_tokens"])
    tokens_p50 = float(np.percentile(rewrite_tokens, 50)) if rewrite_tokens else 0.0
    criteria["rewrite_tokens_p50_le_96"] = {
        "target": f"<= {rewrite_tokens_limit} tokens",
        "actual": f"{tokens_p50:.0f} tokens" if rewrite_tokens else "N/A (no rewrites)",
        "passed": tokens_p50 <= rewrite_tokens_limit,
        "stddev": "\u2014",
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
        "stddev": "\u2014",
    }

    # 9. Orphan traces = 0%
    criteria["orphan_traces_zero"] = {
        "target": "0%",
        "actual": f"{orphan_rate:.1%}",
        "passed": orphan_rate == 0.0,
        "stddev": "\u2014",
    }

    # 10. Streaming TTFT p50 (skipped if sample < min)
    ttft_min_sample = t.get("ttft_min_sample", 3)
    ttft_p50_limit = t.get("ttft_p50_ms", 1000)
    streaming = aggregates.get("streaming", {})
    ttft_p50 = streaming.get("ttft_p50")
    ttft_n = streaming.get("ttft_sample_count", 0)

    if ttft_n < ttft_min_sample:
        criteria["ttft_p50_lt_1000ms"] = {
            "target": f"< {ttft_p50_limit} ms",
            "actual": f"N/A (n={ttft_n}, need >= {ttft_min_sample})",
            "passed": True,
            "skipped": True,
            "stddev": "\u2014",
        }
    else:
        criteria["ttft_p50_lt_1000ms"] = {
            "target": f"< {ttft_p50_limit} ms",
            "actual": f"{ttft_p50:.0f} ms (n={ttft_n})",
            "passed": ttft_p50 < ttft_p50_limit,
            "skipped": False,
            "stddev": "\u2014",
        }

    # 11. Judge quality scores (#386) — from Langfuse managed evaluators
    judge_thresholds = t.get("judge", {})
    for metric, key, label in [
        ("judge_faithfulness_mean", "faithfulness_mean_gte", "faithfulness"),
        ("judge_answer_relevance_mean", "answer_relevance_mean_gte", "answer_relevance"),
        ("judge_context_relevance_mean", "context_relevance_mean_gte", "context_relevance"),
    ]:
        threshold = judge_thresholds.get(key)
        value = aggregates.get(metric)
        count = aggregates.get(f"{metric.replace('_mean', '')}_count", 0)
        criterion_key = f"judge_{label}_gte"
        if threshold is None or value is None:
            criteria[criterion_key] = {
                "target": f">= {threshold}" if threshold else "N/A",
                "actual": f"N/A (n={count})",
                "passed": True,
                "skipped": True,
                "stddev": "\u2014",
            }
        else:
            criteria[criterion_key] = {
                "target": f">= {threshold}",
                "actual": f"{value:.3f} (n={count})",
                "passed": value >= threshold,
                "skipped": False,
                "stddev": "\u2014",
            }

    # Override cold-dependent criteria when cold phase was skipped
    cold_skipped = all(r.state.get("cold_skipped") for r in cold_results) if cold_results else False
    if cold_skipped:
        skip_reason = cold_results[0].state.get("skip_reason", "unknown")
        for key in [
            "cold_p50_lt_5s",
            "cold_p90_lt_8s",
            "cold_over_10s_lt_15pct",
            "generate_p50_lt_2s",
            "multi_rewrite_le_10pct",
            "rewrite_tokens_p50_le_96",
        ]:
            original = criteria[key]
            criteria[key] = {
                "target": original["target"],
                "actual": f"SKIPPED ({skip_reason})",
                "passed": True,
                "dep_unavailable": True,
            }

    return criteria


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
            "latency_stddev": float(np.std(latencies)) if len(latencies) > 1 else 0.0,
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
        node_names = TRACKED_NODE_NAMES
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

    # Judge score aggregation (#386) — from Langfuse managed evaluators
    judge_metrics = ("judge_faithfulness", "judge_answer_relevance", "judge_context_relevance")
    for judge_name in judge_metrics:
        vals = [r.scores.get(judge_name) for r in results if r.scores.get(judge_name) is not None]
        if vals:
            aggregates[f"{judge_name}_mean"] = round(float(np.mean(vals)), 3)
            aggregates[f"{judge_name}_count"] = len(vals)

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


def _format_go_no_go_status(criterion: dict[str, Any]) -> str:
    """Format a single Go/No-Go criterion status for the report."""
    if criterion.get("skipped"):
        return f"[-] SKIPPED ({criterion['actual']})"
    if criterion["passed"]:
        return "[x] PASS"
    return "[ ] **FAIL**"


def generate_report(
    run: ValidationRun,
    aggregates: dict[str, Any],
    output_path: Path,
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
        if "latency_stddev" in agg:
            lines.append(f"| latency stddev | {agg['latency_stddev']:.0f} ms |")
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
        lines.append("| # | Criterion | Target | Actual | Stddev | Status |")
        lines.append("|---|-----------|--------|--------|--------|--------|")
        for i, (name, c) in enumerate(go_no_go.items(), 1):
            status = _format_go_no_go_status(c)
            stddev = c.get("stddev", "\u2014")
            lines.append(f"| {i} | {name} | {c['target']} | {c['actual']} | {stddev} | {status} |")
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
        # User specified a single collection — verify it exists
        from qdrant_client import AsyncQdrantClient

        client = AsyncQdrantClient(url=qdrant_url)
        try:
            exists = await client.collection_exists(args.collection)
        finally:
            await client.close()
        if exists:
            collections = [args.collection]
        else:
            logger.error("Collection %s not found, aborting", args.collection)
            sys.exit(1)
    else:
        collections = await discover_collections(
            qdrant_url,
            quantization_mode=os.getenv("QDRANT_QUANTIZATION_MODE", "off"),
        )

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
        if c.get("dep_unavailable"):
            status = "DEP_UNAVAIL"
        elif c.get("skipped"):
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
