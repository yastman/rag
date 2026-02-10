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
    secret = os.getenv("LANGFUSE_SECRET_KEY", "")
    host = os.getenv("LANGFUSE_HOST", "")
    if not secret:
        logger.error("LANGFUSE_SECRET_KEY not set — cannot record traces")
        sys.exit(1)
    if not host:
        logger.error("LANGFUSE_HOST not set — cannot connect to Langfuse")
        sys.exit(1)
    logger.info("Langfuse config OK: host=%s", host)


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
            graph = build_graph(
                cache=services["cache"],
                embeddings=services["embeddings"],
                sparse_embeddings=services["sparse_embeddings"],
                qdrant=services["qdrant"],
                reranker=services["reranker"],
                llm=services["llm"],
                message=None,  # no Telegram message — headless mode
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
    patterns = [
        "embeddings:v3:*",
        "sparse:v3:*",
        "analysis:v3:*",
        "search:v3:*",
        "rerank:v3:*",
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
            # Populate node span durations from observations
            if hasattr(trace, "observations") and trace.observations:
                for obs in trace.observations:
                    obs_name = getattr(obs, "name", "") or ""
                    if not obs_name.startswith("node-"):
                        continue
                    node_name = obs_name.replace("node-", "").replace("-", "_")
                    start_time = getattr(obs, "start_time", None)
                    end_time = getattr(obs, "end_time", None)
                    if start_time and end_time:
                        delta_ms = (end_time - start_time).total_seconds() * 1000
                        r.node_spans_ms[node_name] = delta_ms
            enriched += 1
        except Exception as e:
            logger.warning("Failed to enrich trace %s: %s", r.trace_id, e)
    logger.info("Enriched %d/%d results from Langfuse", enriched, len(results))
    lf.flush()
    return results


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

    return aggregates


def generate_report(
    run: ValidationRun,
    aggregates: dict[str, Any],
    output_path: Path,
    reference_metrics: dict[str, Any] | None = None,
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
    lines.append("<!-- Fill after reviewing metrics -->")
    lines.append(
        "- [ ] Latency issues from trace c2b95d86 are reproducible → proceed with #107/#108/#109"
    )
    lines.append("- [ ] Issues NOT reproducible → close or narrow scope with evidence")
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

    run.collections = collections
    logger.info("Collections to validate: %s", collections)

    # Run validation per collection
    all_results: list[TraceResult] = []
    for collection in collections:
        results = await run_collection_validation(collection, run)
        all_results.extend(results)

    if not all_results:
        logger.error("No traces collected (all collections skipped or failed), aborting")
        sys.exit(1)

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

    # Print summary to console
    for phase, agg in aggregates.items():
        logger.info(
            "%s (n=%d): p50=%.0fms p95=%.0fms mean=%.0fms",
            phase,
            agg["n"],
            agg["latency_p50"],
            agg["latency_p95"],
            agg["latency_mean"],
        )

    # Generate report
    if args.report:
        report_path = Path(
            f"docs/reports/{run.started_at.strftime('%Y-%m-%d')}-validation-{run_id[:8]}.md"
        )
        generate_report(run, aggregates, report_path, reference_metrics=reference_metrics)

    # Also dump raw JSON for programmatic use
    raw_path = Path(
        f"docs/reports/{run.started_at.strftime('%Y-%m-%d')}-validation-{run_id[:8]}.json"
    )
    raw_data = {
        "run_id": run.run_id,
        "git_sha": run.git_sha,
        "started_at": run.started_at.isoformat(),
        "collections": run.collections,
        "skip_rerank_threshold": run.skip_rerank_threshold,
        "relevance_threshold_rrf": run.relevance_threshold_rrf,
        "aggregates": aggregates,
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
    args = parser.parse_args()
    asyncio.run(run_validation(args))


if __name__ == "__main__":
    main()
