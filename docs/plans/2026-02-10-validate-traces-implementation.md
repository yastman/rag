# Validate Traces Script — Implementation Plan

**Goal:** Reusable `make validate-traces` pipeline that rebuilds containers, runs queries through LangGraph directly, collects Langfuse traces with p50/p95 aggregates, and generates a Go/No-Go report for issue #110.

**Architecture:** Two Python modules — `scripts/validate_queries.py` (query definitions) and `scripts/validate_traces.py` (runner + reporter). The runner uses deterministic trace IDs (`create_trace_id`) + `@observe` wrappers, writes/reads metrics via Langfuse SDK, and computes aggregates from Langfuse score data (with local fallback). For mixed collections, use collection-specific runner mode (LangGraph/BGE path vs Voyage-compatible path) to avoid embedding/collection mismatch. Two Makefile targets: full rebuild (`validate-traces`) and fast no-rebuild (`validate-traces-fast`).

**Tech Stack:** Python 3.12, LangGraph, Langfuse SDK v3, Qdrant client, httpx, numpy (for percentiles)

**Design doc:** `docs/plans/2026-02-10-runtime-rebuild-trace-validation.md`

**Best-practice amendments (Context7 + Exa):**
- Store `validation_run_id`, `session_id`, `collection`, `query_set`, `difficulty`, `git_sha` as trace metadata/tags for robust filtering.
- Use stable trace linking: generate explicit trace ID per query instead of trying to infer from recent traces.
- Pull final metrics from Langfuse scores/spans API for reporting; do not rely only on local in-process state.
- Keep `cold` and `cache_hit` as separate groups with explicit `n` in all aggregate tables.

---

### Task 1: Create query definitions module

**Files:**
- Create: `scripts/validate_queries.py`

**Step 1: Write the module**

```python
"""Validation query sets for trace validation runs.

Imports from existing test fixtures + manual edge cases.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationQuery:
    """Single validation query."""

    text: str
    source: str  # smoke | eval | manual
    difficulty: str  # easy | medium | hard
    collection: str  # legal_documents | contextual_bulgaria_voyage | any
    expect_rewrite: bool = False


# Bulgarian property queries (from tests/smoke/queries.py, skip CHITCHAT)
PROPERTY_QUERIES: list[ValidationQuery] = [
    # SIMPLE (6)
    ValidationQuery("Сколько стоит квартира?", "smoke", "easy", "contextual_bulgaria_voyage"),
    ValidationQuery("Какая цена на студию?", "smoke", "easy", "contextual_bulgaria_voyage"),
    ValidationQuery("Сколько стоит дом?", "smoke", "easy", "contextual_bulgaria_voyage"),
    ValidationQuery("Какая цена аренды?", "smoke", "easy", "contextual_bulgaria_voyage"),
    ValidationQuery("Двухкомнатная квартира", "smoke", "easy", "contextual_bulgaria_voyage"),
    ValidationQuery("Трёхкомнатная квартира", "smoke", "easy", "contextual_bulgaria_voyage"),
    # COMPLEX (8)
    ValidationQuery(
        "Найди двухкомнатную квартиру в Солнечном берегу до 50000 евро с видом на море",
        "smoke", "hard", "contextual_bulgaria_voyage",
    ),
    ValidationQuery(
        "Квартиры в комплексе Harmony Suites корпус 3 с мебелью",
        "smoke", "hard", "contextual_bulgaria_voyage",
    ),
    ValidationQuery(
        "Сравни цены на студии в Несебре и Равде",
        "smoke", "hard", "contextual_bulgaria_voyage",
    ),
    ValidationQuery(
        "Апартаменты с двумя спальнями рядом с пляжем, первая линия",
        "smoke", "hard", "contextual_bulgaria_voyage",
    ),
    ValidationQuery(
        "Что лучше: Sunny Beach или Sveti Vlas для инвестиций?",
        "smoke", "hard", "contextual_bulgaria_voyage",
    ),
    ValidationQuery(
        "Новостройки с рассрочкой платежа на 2 года",
        "smoke", "hard", "contextual_bulgaria_voyage",
    ),
    ValidationQuery(
        "Квартира с паркингом и кладовой в закрытом комплексе",
        "smoke", "hard", "contextual_bulgaria_voyage",
    ),
    ValidationQuery(
        "Покажи варианты до 70000 евро с ремонтом под ключ",
        "smoke", "hard", "contextual_bulgaria_voyage",
    ),
]

# Criminal Code queries (subset from src/evaluation/smoke_test.py)
LEGAL_QUERIES: list[ValidationQuery] = [
    # HARD (5)
    ValidationQuery(
        "что регулирует первая статья УК Украины о правовом обеспечении",
        "eval", "hard", "legal_documents",
    ),
    ValidationQuery(
        "как учитывается иностранный приговор при рецидиве на территории Украины?",
        "eval", "hard", "legal_documents",
    ),
    ValidationQuery(
        "какая уголовная ответственность за отказ от дальнейшего совершения преступления",
        "eval", "hard", "legal_documents",
    ),
    ValidationQuery(
        "как определяется неосторожность: предвидел или не предвидел последствия действий",
        "eval", "hard", "legal_documents",
    ),
    ValidationQuery(
        "как квалифицировать два разных преступления, совершённые одним лицом одновременно",
        "eval", "hard", "legal_documents",
    ),
    # MEDIUM (5)
    ValidationQuery(
        "какие цели и задачи ставит перед собой уголовный кодекс Украины",
        "eval", "medium", "legal_documents",
    ),
    ValidationQuery(
        "статья 1 Уголовного кодекса Украины задачи",
        "eval", "easy", "legal_documents",
    ),
    ValidationQuery(
        "стаття 115 КК України",
        "eval", "easy", "legal_documents",
    ),
    ValidationQuery(
        "відповідальність за крадіжку",
        "eval", "medium", "legal_documents",
    ),
    ValidationQuery(
        "покарання за шахрайство",
        "eval", "medium", "legal_documents",
    ),
]

# Manual edge cases
EDGE_CASE_QUERIES: list[ValidationQuery] = [
    # Should trigger rewrite (nonsensical → low relevance → rewrite)
    ValidationQuery(
        "фиолетовые документы с перламутровыми пуговицами",
        "manual", "hard", "any", expect_rewrite=True,
    ),
    # Should return empty or low results
    ValidationQuery(
        "quantum computing applications in molecular biology",
        "manual", "hard", "any",
    ),
    # Simple, should be fast
    ValidationQuery(
        "цена",
        "manual", "easy", "any",
    ),
]


def get_queries_for_collection(collection: str) -> list[ValidationQuery]:
    """Get queries applicable to a specific collection."""
    result: list[ValidationQuery] = []
    if collection == "legal_documents":
        result.extend(LEGAL_QUERIES)
    elif collection == "contextual_bulgaria_voyage":
        result.extend(PROPERTY_QUERIES)
    # Edge cases apply to any collection
    result.extend(EDGE_CASE_QUERIES)
    return result


def get_warmup_queries(collection: str, count: int = 3) -> list[ValidationQuery]:
    """Get warmup queries (subset of main queries)."""
    queries = get_queries_for_collection(collection)
    return queries[:count]


def get_cache_hit_queries(
    cold_queries: list[ValidationQuery], count: int = 5,
) -> list[ValidationQuery]:
    """Select queries to repeat for cache-hit testing."""
    # Pick a mix: some easy (likely cached) + some hard
    easy = [q for q in cold_queries if q.difficulty == "easy"][:2]
    hard = [q for q in cold_queries if q.difficulty == "hard"][:3]
    return (easy + hard)[:count]
```

**Step 2: Verify import works**

Run: `uv run python -c "from scripts.validate_queries import get_queries_for_collection; print(len(get_queries_for_collection('legal_documents')))"`

Expected: `13` (10 legal + 3 edge)

**Step 3: Commit**

```bash
git add scripts/validate_queries.py
git commit -m "feat(validation): add query definitions for trace validation (#110)"
```

---

### Task 2: Create the validation runner — service initialization

**Files:**
- Create: `scripts/validate_traces.py`

**Step 1: Write the service init and preflight checks**

```python
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
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
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

COLLECTIONS_TO_CHECK = ["legal_documents", "contextual_bulgaria_voyage"]


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


def get_git_sha() -> str:
    """Get current git commit SHA."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
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
    import os

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
                    "Skipping %s: collection exists but VOYAGE_API_KEY not set", name,
                )
                continue
            available.append(name)
    return available
```

**Critical additions for Task 2:**
- Add `check_langfuse_config()` preflight (host + keys) and fail-fast with explicit error.
- Add `detect_runner_mode(collection)`:
  - `legal_documents` -> `langgraph_bge`
  - `contextual_bulgaria_voyage` -> `voyage_compatible` (or explicit skip if unsupported in current env).
- Log skip reason explicitly (missing collection, missing provider creds, incompatible embedding path).

**Step 2: Verify syntax**

Run: `uv run python -c "import ast; ast.parse(open('scripts/validate_traces.py').read()); print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add scripts/validate_traces.py
git commit -m "feat(validation): add runner skeleton with preflight checks (#110)"
```

---

### Task 3: Add pipeline execution logic (with deterministic trace IDs)

**Files:**
- Modify: `scripts/validate_traces.py`

**Step 1: Add the run_query and run_validation functions**

Append after the `discover_collections` function:

```python
async def init_services(collection: str):
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
    from telegram_bot.graph.graph import build_graph
    from telegram_bot.graph.state import make_initial_state
    from telegram_bot.observability import get_client, observe, propagate_attributes
    from telegram_bot.bot import _write_langfuse_scores

    config = services["config"]
    session_id = f"validate-{run_meta['run_id'][:8]}"

    state = make_initial_state(
        user_id=0,  # validation user
        session_id=session_id,
        query=query.text,
    )
    state["max_rewrite_attempts"] = config.max_rewrite_attempts

    wall_start = time.perf_counter()
    lf = get_client()
    trace_id = lf.create_trace_id()

    with propagate_attributes(
        session_id=session_id,
        user_id="validation",
        tags=["validation", phase, run_meta["collection"]],
    ):
        @observe(name="validation-query")
        async def _run():
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
            # Write metadata/scores while still inside active observation context
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

        result = await _run(langfuse_observation_id=trace_id)

    wall_ms = (time.perf_counter() - wall_start) * 1000
    result["pipeline_wall_ms"] = wall_ms

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
                "cache_hit", "search_cache_hit", "embeddings_cache_hit",
                "rerank_applied", "search_results_count", "grade_confidence",
                "rewrite_count", "query_type", "skip_rerank",
                "latency_stages",
            ]
        },
    )


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
            "Collection %s requires Voyage-compatible runner; skip in current implementation",
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

    # Phase 1: Warmup (discard)
    warmup_queries = get_warmup_queries(collection, count=3)
    logger.info("Phase 1: Warmup (%d queries, discarded)", len(warmup_queries))
    for q in warmup_queries:
        await run_single_query(q, services, run_meta, phase="warmup")

    # Phase 2: Cold run
    cold_queries = get_queries_for_collection(collection)
    logger.info("Phase 2: Cold run (%d queries)", len(cold_queries))
    for q in cold_queries:
        result = await run_single_query(q, services, run_meta, phase="cold")
        results.append(result)

    # Phase 3: Cache-hit run (duplicates from cold)
    cache_queries = get_cache_hit_queries(cold_queries, count=5)
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
```

**Critical additions for Task 3:**
- `update_current_trace` and score writing must run inside active observation context, not after it.
- For `contextual_bulgaria_voyage`, use collection-compatible runner mode (or skip with explicit reason) instead of forcing BGE hybrid path.
- Include `validation_run_id` both in metadata and tags to simplify API filtering.

**Step 2: Verify syntax**

Run: `uv run python -c "import ast; ast.parse(open('scripts/validate_traces.py').read()); print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add scripts/validate_traces.py
git commit -m "feat(validation): add pipeline execution with cold/cache phases (#110)"
```

---

### Task 4: Add metrics aggregation and report generation

**Files:**
- Modify: `scripts/validate_traces.py`

**Step 1: Add Langfuse enrichment + compute_aggregates + generate_report functions**

Append after `run_collection_validation`:

```python
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
        def score_rate(score_name: str, state_fallback: str | None = None) -> float:
            vals: list[float] = []
            for r in phase_results:
                if score_name in r.scores:
                    vals.append(1.0 if r.scores[score_name] >= 0.5 else 0.0)
                elif state_fallback is not None:
                    vals.append(1.0 if r.state.get(state_fallback) else 0.0)
            return float(np.mean(vals)) if vals else 0.0

        agg["semantic_cache_hit_rate"] = score_rate("semantic_cache_hit", "cache_hit")
        agg["search_cache_hit_rate"] = score_rate("search_cache_hit", "search_cache_hit")
        agg["embeddings_cache_hit_rate"] = score_rate("embeddings_cache_hit", "embeddings_cache_hit")
        agg["rerank_applied_rate"] = score_rate("rerank_applied", "rerank_applied")
        agg["rewrite_rate"] = float(
            np.mean([1.0 if (r.state.get("rewrite_count", 0) or 0) > 0 else 0.0 for r in phase_results])
        )

        # Avg results count
        counts = [r.state.get("search_results_count", 0) for r in phase_results]
        agg["results_count_mean"] = float(np.mean(counts)) if counts else 0.0

        # Per-node latency p50/p95 (prefer Langfuse spans, fallback to state latency_stages)
        node_names = [
            "classify", "cache_check", "retrieve", "grade",
            "rerank", "generate", "rewrite", "cache_store", "respond",
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
    lines.append("- [ ] Latency issues from trace c2b95d86 are reproducible → proceed with #107/#108/#109")
    lines.append("- [ ] Issues NOT reproducible → close or narrow scope with evidence")
    lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    logger.info("Report saved to %s", output_path)
```

**Critical additions for Task 4:**
- Add `enrich_results_from_langfuse(run_id, results)` that fetches traces by `validation_run_id` and populates `TraceResult.scores` and `TraceResult.node_spans_ms`.
- Add `fetch_reference_trace_metrics(REFERENCE_TRACE_ID)` and include it in the report comparison table (`cold/cache` with explicit `n`).
- Add optional SDK evaluation bootstrap: `langfuse.create_dataset_item(...)` + `dataset.run_experiment(...)` for recurring regression checks on the same query set.

**Step 2: Verify syntax**

Run: `uv run python -c "import ast; ast.parse(open('scripts/validate_traces.py').read()); print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add scripts/validate_traces.py
git commit -m "feat(validation): add metrics aggregation and report generator (#110)"
```

---

### Task 5: Add main() CLI entrypoint

**Files:**
- Modify: `scripts/validate_traces.py`

**Step 1: Add main function and CLI**

Append at the end of the file:

```python
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
            phase, agg["n"], agg["latency_p50"], agg["latency_p95"], agg["latency_mean"],
        )

    # Generate report
    if args.report:
        report_path = Path(
            f"docs/reports/{run.started_at.strftime('%Y-%m-%d')}-validation-{run_id[:8]}.md"
        )
        generate_report(run, aggregates, report_path, reference_metrics=reference_metrics)

    # Also dump raw JSON for programmatic use
    raw_path = Path(f"docs/reports/{run.started_at.strftime('%Y-%m-%d')}-validation-{run_id[:8]}.json")
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


def main():
    parser = argparse.ArgumentParser(description="Trace validation runner")
    parser.add_argument(
        "--collection", type=str, default=None,
        help="Validate specific collection only",
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Generate markdown report",
    )
    args = parser.parse_args()
    asyncio.run(run_validation(args))


if __name__ == "__main__":
    main()
```

**Step 2: Verify CLI help works**

Run: `uv run python scripts/validate_traces.py --help`

Expected: Shows help with `--collection` and `--report` options

**Step 3: Commit**

```bash
git add scripts/validate_traces.py
git commit -m "feat(validation): add CLI entrypoint with collection discovery (#110)"
```

---

### Task 6: Add Makefile targets

**Files:**
- Modify: `Makefile`

**Step 1: Add validate-traces and validate-traces-fast targets**

Insert after the `qdrant-backup` section (before K3S section, around line 757):

```makefile
# =============================================================================
# TRACE VALIDATION (#110)
# =============================================================================

.PHONY: validate-traces validate-traces-fast

validate-traces: ## Full rebuild + trace validation + report
	@echo "$(BLUE)Full rebuild + validation...$(NC)"
	$(COMPOSE_CMD) build --no-cache telegram-bot litellm bge-m3
	$(COMPOSE_CMD) --profile core --profile bot --profile ml up -d --wait
	uv run python scripts/validate_traces.py --report
	@echo "$(GREEN)✓ Validation complete — see docs/reports/$(NC)"

validate-traces-fast: ## No rebuild, just start stack + trace validation + report
	@echo "$(BLUE)Fast validation (no rebuild)...$(NC)"
	$(COMPOSE_CMD) --profile core --profile bot --profile ml up -d --wait
	uv run python scripts/validate_traces.py --report
	@echo "$(GREEN)✓ Validation complete — see docs/reports/$(NC)"
```

**Step 2: Verify target shows in help**

Run: `make help | grep validate`

Expected: Both targets listed with descriptions

**Step 3: Commit**

```bash
git add Makefile
git commit -m "feat(validation): add make validate-traces and validate-traces-fast (#110)"
```

---

### Task 7: Add unit test for query module

**Files:**
- Create: `tests/unit/test_validate_queries.py`

**Step 1: Write the test**

```python
"""Tests for validation query definitions."""

import pytest

from scripts.validate_queries import (
    EDGE_CASE_QUERIES,
    LEGAL_QUERIES,
    PROPERTY_QUERIES,
    ValidationQuery,
    get_cache_hit_queries,
    get_queries_for_collection,
    get_warmup_queries,
)


class TestValidationQueries:
    """Test query set definitions."""

    def test_property_queries_count(self):
        assert len(PROPERTY_QUERIES) == 14  # 6 simple + 8 complex

    def test_legal_queries_count(self):
        assert len(LEGAL_QUERIES) == 10  # 5 hard + 5 medium/easy

    def test_edge_case_queries_count(self):
        assert len(EDGE_CASE_QUERIES) == 3

    def test_get_queries_for_legal(self):
        queries = get_queries_for_collection("legal_documents")
        # 10 legal + 3 edge cases
        assert len(queries) == 13
        assert all(isinstance(q, ValidationQuery) for q in queries)

    def test_get_queries_for_property(self):
        queries = get_queries_for_collection("contextual_bulgaria_voyage")
        # 14 property + 3 edge cases
        assert len(queries) == 17

    def test_get_queries_unknown_collection(self):
        queries = get_queries_for_collection("nonexistent")
        # Only edge cases
        assert len(queries) == 3

    def test_warmup_queries_subset(self):
        warmup = get_warmup_queries("legal_documents", count=3)
        assert len(warmup) == 3
        full = get_queries_for_collection("legal_documents")
        assert warmup == full[:3]

    def test_cache_hit_queries_mix(self):
        cold = get_queries_for_collection("legal_documents")
        cache = get_cache_hit_queries(cold, count=5)
        assert len(cache) <= 5
        # All cache queries should be from cold set
        for q in cache:
            assert q in cold

    def test_all_queries_have_required_fields(self):
        all_queries = PROPERTY_QUERIES + LEGAL_QUERIES + EDGE_CASE_QUERIES
        for q in all_queries:
            assert q.text, f"Empty text: {q}"
            assert q.source in ("smoke", "eval", "manual"), f"Bad source: {q.source}"
            assert q.difficulty in ("easy", "medium", "hard"), f"Bad difficulty: {q.difficulty}"
            assert q.collection, f"Empty collection: {q}"

    def test_edge_case_rewrite_query_flagged(self):
        rewrite_queries = [q for q in EDGE_CASE_QUERIES if q.expect_rewrite]
        assert len(rewrite_queries) >= 1
```

**Step 2: Run the test**

Run: `uv run pytest tests/unit/test_validate_queries.py -v`

Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/unit/test_validate_queries.py
git commit -m "test(validation): add unit tests for query definitions (#110)"
```

---

### Task 8: Add unit test for aggregation logic

**Files:**
- Create: `tests/unit/test_validate_aggregates.py`

**Step 1: Write the test**

```python
"""Tests for validation metrics aggregation."""

import pytest

from scripts.validate_traces import TraceResult, compute_aggregates


def _make_result(
    phase: str = "cold",
    latency: float = 100.0,
    cache_hit: bool = False,
    rerank: bool = True,
    results_count: int = 10,
    rewrite_count: int = 0,
    latency_stages: dict | None = None,
) -> TraceResult:
    return TraceResult(
        trace_id="test",
        query="test query",
        collection="test",
        phase=phase,
        source="test",
        difficulty="easy",
        latency_wall_ms=latency,
        state={
            "cache_hit": cache_hit,
            "search_cache_hit": False,
            "embeddings_cache_hit": False,
            "rerank_applied": rerank,
            "search_results_count": results_count,
            "rewrite_count": rewrite_count,
            "latency_stages": latency_stages or {},
        },
    )


class TestComputeAggregates:
    """Test metrics aggregation."""

    def test_cold_aggregates(self):
        results = [
            _make_result(latency=100),
            _make_result(latency=200),
            _make_result(latency=300),
            _make_result(latency=400),
            _make_result(latency=500),
        ]
        agg = compute_aggregates(results)

        assert "cold" in agg
        cold = agg["cold"]
        assert cold["n"] == 5
        assert cold["latency_p50"] == pytest.approx(300.0, abs=1)
        assert cold["latency_mean"] == pytest.approx(300.0, abs=1)
        assert cold["latency_max"] == pytest.approx(500.0, abs=1)

    def test_cache_hit_separate(self):
        results = [
            _make_result(phase="cold", latency=500),
            _make_result(phase="cache_hit", latency=50, cache_hit=True),
            _make_result(phase="cache_hit", latency=30, cache_hit=True),
        ]
        agg = compute_aggregates(results)

        assert agg["cold"]["n"] == 1
        assert agg["cache_hit"]["n"] == 2
        assert agg["cache_hit"]["semantic_cache_hit_rate"] == pytest.approx(1.0)

    def test_warmup_excluded(self):
        results = [
            _make_result(phase="warmup", latency=999),
            _make_result(phase="cold", latency=100),
        ]
        agg = compute_aggregates(results)

        assert "warmup" not in agg
        assert agg["cold"]["n"] == 1

    def test_rerank_rate(self):
        results = [
            _make_result(rerank=True),
            _make_result(rerank=True),
            _make_result(rerank=False),
        ]
        agg = compute_aggregates(results)
        assert agg["cold"]["rerank_applied_rate"] == pytest.approx(2 / 3)

    def test_node_latencies(self):
        results = [
            _make_result(latency_stages={"retrieve": 0.1, "generate": 0.2}),
            _make_result(latency_stages={"retrieve": 0.3, "generate": 0.4}),
        ]
        agg = compute_aggregates(results)
        # retrieve: [100ms, 300ms] → p50=200ms
        assert agg["cold"]["node_p50"]["retrieve"] == pytest.approx(200.0, abs=10)
        assert "generate" in agg["cold"]["node_p50"]

    def test_empty_results(self):
        agg = compute_aggregates([])
        assert agg == {}
```

**Step 2: Run the test**

Run: `uv run pytest tests/unit/test_validate_aggregates.py -v`

Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/unit/test_validate_aggregates.py
git commit -m "test(validation): add unit tests for metrics aggregation (#110)"
```

---

### Task 9: Add docs/reports/ to .gitignore and create directory

**Files:**
- Modify: `.gitignore`

**Step 1: Add reports directory exclusion**

Add to `.gitignore`:

```
# Validation reports (generated, not committed)
docs/reports/
```

**Step 2: Create the directory with .gitkeep**

Run:
```bash
mkdir -p docs/reports
touch docs/reports/.gitkeep
```

Note: Only `.gitkeep` gets committed, actual reports are gitignored.

**Step 3: Commit**

```bash
git add .gitignore docs/reports/.gitkeep
git commit -m "chore: add docs/reports/ for validation output (#110)"
```

---

### Task 10: Run linter and type checks, fix issues

**Files:**
- Modify: `scripts/validate_traces.py` (if needed)
- Modify: `scripts/validate_queries.py` (if needed)

**Step 1: Run ruff check**

Run: `uv run ruff check scripts/validate_traces.py scripts/validate_queries.py`

Fix any issues.

**Step 2: Run ruff format**

Run: `uv run ruff format scripts/validate_traces.py scripts/validate_queries.py`

**Step 3: Run type check (best-effort)**

Run: `uv run mypy scripts/validate_traces.py scripts/validate_queries.py --ignore-missing-imports`

Fix critical errors only (type: ignore for third-party stubs is fine).

**Step 4: Run all unit tests**

Run: `uv run pytest tests/unit/test_validate_queries.py tests/unit/test_validate_aggregates.py -v`

Expected: All tests PASS

**Step 5: Commit**

```bash
git add scripts/ tests/unit/test_validate_queries.py tests/unit/test_validate_aggregates.py
git commit -m "fix(validation): lint and type fixes (#110)"
```

---

### Task 11: Verify full integration (dry run)

**Files:** None (verification only)

**Step 1: Check make targets**

Run: `make help | grep validate`

Expected: Both targets visible.

**Step 2: Test CLI without Docker (expect connection error)**

Run: `uv run python scripts/validate_traces.py --help`

Expected: Help output with `--collection` and `--report` flags.

**Step 3: Verify query import chain**

Run: `uv run python -c "from scripts.validate_queries import get_queries_for_collection; qs = get_queries_for_collection('legal_documents'); print(f'{len(qs)} queries ready')"`

Expected: `13 queries ready`

**Step 4: Final commit (if any fixes)**

```bash
git add -A
git commit -m "chore(validation): final polish for trace validation script (#110)"
```

---

### References (SDK-first)

- Langfuse Evaluation Overview: `https://langfuse.com/docs/evaluation/overview`
- Langfuse Datasets: `https://langfuse.com/docs/evaluation/experiments/datasets`
- Langfuse Experiments via SDK: `https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk`
- Langfuse LLM-as-a-Judge: `https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge`
- Langfuse Query via SDK (trace/score retrieval): `https://langfuse.com/docs/api-and-data-platform/features/query-via-sdk`
