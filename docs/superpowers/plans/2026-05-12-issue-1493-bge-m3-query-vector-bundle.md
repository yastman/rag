# BGE-M3 Query Vector Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `tmux-swarm-orchestration` for visible OpenCode workers. If executing without tmux workers, use superpowers:executing-plans task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix issue #1493 by caching BGE-M3 dense, sparse, and ColBERT query vectors as one Redis bundle so repeated retrieval misses do not make a second BGE request for ColBERT.

**Architecture:** Add a small typed bundle contract for BGE-M3 query vectors, store it atomically in `CacheLayerManager`, and make the shared embedding core prefer that bundle before legacy dense/sparse caches. Keep semantic answer cache behavior separate: semantic hits still return early, while semantic misses hand Qdrant a complete dense+sparse+ColBERT bundle when the current embeddings adapter supports it.

**Tech Stack:** Python 3.14, Redis/RedisVL, BGE-M3 FlagEmbedding API, Qdrant Query API with dense+sparse prefetch/fusion and ColBERT multivector rerank, pytest/pytest-asyncio, Langfuse tracing.

---

## Current Issue Context

Tracked issue: https://github.com/yastman/rag/issues/1493

Related open issues reviewed:

- `#1472` verifies the Qdrant `v1.17.1` to `v1.18.0` and Redis `8.6.2` to `8.6.3` upgrade. This plan should not change collection schema, but final verification should include Qdrant retrieval tests because the bundle feeds the Qdrant hybrid/ColBERT path.
- `#1488` and `#1489` cover product-meaningful Telethon/Langfuse trace gates. After this change, those gates should be able to assert fewer BGE spans on repeat requests.
- `#1485` covers missing root output/scores in core traces. This plan includes a narrow scoring fix for cache-hit `results_count`/`no_results`, but should not take over the full trace-contract issue.

Trace findings from the issue:

- First real request `98e53b69b12579412f68048e226e39cf`, query `виды внж в болгарии?`: semantic cache miss, Qdrant `qdrant-hybrid-search-rrf-colbert`, LLM used. Dense/sparse were cached, but ColBERT was separately computed.
- Trace `4c214698-453a-4a2f-8610-5d4f2461d938` is a LiteLLM auto-trace for the same generation, not a second user request.
- Second real request `e4472fbf09aa5d8305442854a53aedb1`: semantic cache hit, no Qdrant/LLM, about `157ms`.

Current code problem:

- `telegram_bot/services/rag_core.py:243-264` reads only dense from `cache.get_embedding()` and returns `colbert=None`.
- `telegram_bot/graph/nodes/cache.py:158-177` and `telegram_bot/agents/rag_pipeline.py:269-293` then compute ColBERT after semantic miss, causing an extra BGE call when dense/sparse were cached without ColBERT.
- `services/bge-m3-api/app.py` and `telegram_bot/integrations/embeddings.py:123-142` already support one `/encode/hybrid` call returning dense+sparse+ColBERT.

Docs checked:

- Context7 `/flagopen/flagembedding`: `BGEM3FlagModel`/`M3Embedder` supports one `encode(..., return_dense=True, return_sparse=True, return_colbert_vecs=True)` call with output keys `dense_vecs`, `lexical_weights`, `colbert_vecs`.
- Context7 `/llmstxt/qdrant_tech_llms-full_txt`: current Qdrant Query API pattern is first-stage dense/sparse prefetch/fusion, then ColBERT/multivector rerank in the same query. For reranking-only multivectors, Qdrant recommends `hnsw_config=models.HnswConfigDiff(m=0)`.
- Exa search result from Qdrant docs confirms hybrid queries use `prefetch`, `rrf`/`dbsf`, and ColBERT multivectors for multi-stage reranking. Exa search result from BGE docs confirms BGE-M3 multi-functionality: dense, sparse, and multi-vector outputs from one model.

## File Structure

Create:

- `telegram_bot/services/bge_m3_query_bundle.py` - typed bundle contract, serialization, validation, and deterministic key material helpers.
- `tests/unit/services/test_bge_m3_query_bundle.py` - pure unit tests for bundle serialization, completeness checks, and cache-key stability.
- `tests/unit/integrations/test_cache_bge_m3_query_bundle.py` - Redis cache method tests with fake async Redis.

Modify:

- `telegram_bot/integrations/cache.py` - add a `bge_m3_query_bundle` exact-cache tier and async `get_bge_m3_query_bundle()` / `store_bge_m3_query_bundle()` methods.
- `telegram_bot/services/rag_core.py` - make `compute_query_embedding()` prefer full bundle cache, store full bundle after one hybrid+ColBERT encode, and keep legacy fallback for adapters without ColBERT.
- `telegram_bot/graph/nodes/cache.py` - remove the bundle-capable post-miss ColBERT recompute path; retain only a legacy `aembed_colbert_query()` fallback when no full bundle API exists.
- `telegram_bot/agents/rag_pipeline.py` - apply the same cache-check change as the graph node and use the bundle helper in rewrite/re-embed branches.
- `telegram_bot/graph/nodes/retrieve.py` - when a rewrite clears vectors, use the shared embedding core or bundle cache instead of dense/sparse-only logic.
- `telegram_bot/integrations/embeddings.py` - update docstrings to state `/encode/hybrid` returns dense+sparse+ColBERT when requested.
- `telegram_bot/services/bge_m3_client.py` - update `encode_hybrid()` docstring/metadata to reflect ColBERT output.
- `telegram_bot/scoring.py` - prevent semantic cache-hit responses from being scored as misleading `results_count=0` / `no_results=1`.
- `tests/unit/graph/test_cache_nodes.py` - replace old partial-cache expectations with bundle-hit/miss behavior.
- `tests/unit/agents/test_rag_pipeline.py` - update `_cache_check`, rewrite, and retrieval tests around ColBERT computation.
- `tests/unit/graph/test_retrieve_node.py` - add rewrite/re-embed coverage for bundle use.
- `tests/unit/test_bot_scores.py` - add scoring regression for cache-hit `results_count` / `no_results`.
- `docs/adr/0004-redisvl-semantic-cache.md` or `docs/indexes/observability-and-storage.md` - document semantic answer cache vs BGE-M3 vector bundle cache.

---

## Tmux Swarm Execution

**Classification:** `parallel_waves`.

**Base branch:** `dev`.

**Integration branch:** `issue/1493-bge-m3-query-vector-bundle`.

**Runner:** OpenCode via `${CODEX_HOME:-$HOME/.codex}/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh`.

**Docs lookup policy:** `forbidden` for all workers. The BGE-M3, Qdrant, RedisVL, Langfuse, and issue context needed for this task is already captured in this plan. Workers must not use OpenCode web search, webfetch, MCP Exa, or MCP Context7. If a worker believes external docs are required, it must return `blocked` with the missing artifact.

**Worker budget:** run at most 2 implementation workers concurrently for this issue. Runtime/local trace verification is exclusive and counts as 2 slots.

**Orchestrator responsibilities:**

- Create/update the integration branch from `dev`.
- Launch each worker in a dedicated worktree.
- Validate launch metadata, signal JSON, prompt SHA, branch/base, reserved files, commits, changed files, and command evidence.
- Merge/cherry-pick worker branches into the integration branch.
- Personally inspect bounded diffs after each wave.
- Run final focused checks and decide whether runtime trace verification is justified.
- Launch a fresh read-only PR review worker after the final PR head SHA exists.

**Worker rules:**

- Work only in the assigned worktree/branch.
- Edit only `RESERVED_FILES`; block if another file is required.
- Do not use the main checkout for code, commits, or PR work.
- Do not spawn subagents from worker panes.
- Run only assigned focused commands (`verification_budget: focused_only`) unless the orchestrator explicitly assigns another budget.
- Commit changes on the worker branch and write strict DONE/FAILED/BLOCKED JSON to the assigned signal path.
- Report new confirmed bugs in DONE JSON; fix them only if they block the current task and fit reserved files.

### Wave Graph

1. **Wave 1: Bundle/cache foundation** - one worker. This must finish before any other implementation wave because later code imports the bundle contract.
2. **Wave 2: Retrieval behavior** - two workers in parallel after Wave 1. One owns shared core + graph cache node; one owns agent pipeline + retrieve rewrite branch.
3. **Wave 3: Observability/docs** - two workers in parallel after Wave 2. One owns Langfuse scoring; one owns docs/docstrings.
4. **Wave 4: Integration owner** - one worker or orchestrator local merge. Resolve conflicts, run focused combined tests, push integration branch, and open/update one PR.
5. **Wave 5: Read-only PR review** - one `pr-review` worker on the current PR head SHA. Any fixes go to a separate `pr-review-fix` worker, followed by a fresh review worker.

### Reserved Files By Worker

| Wave | Worker | Agent/model | Required OpenCode skills | Branch | Signal path | Reserved files |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `w1-cache-contract` | `pr-worker` / `opencode-go/kimi-k2.6` | `swarm-pr-finish` | `worker/1493-cache-contract` | `.signals/issue-1493-bge-bundle/w1-cache-contract.done.json` | `telegram_bot/services/bge_m3_query_bundle.py`, `telegram_bot/integrations/cache.py`, `tests/unit/services/test_bge_m3_query_bundle.py`, `tests/unit/integrations/test_cache_bge_m3_query_bundle.py` |
| 2 | `w2-core-graph` | `pr-worker` / `opencode-go/kimi-k2.6` | `swarm-pr-finish` | `worker/1493-core-graph` | `.signals/issue-1493-bge-bundle/w2-core-graph.done.json` | `telegram_bot/services/rag_core.py`, `telegram_bot/graph/nodes/cache.py`, `tests/unit/services/test_rag_core_embedding_bundle.py`, `tests/unit/graph/test_cache_nodes.py` |
| 2 | `w2-pipeline-retrieve` | `pr-worker` / `opencode-go/kimi-k2.6` | `swarm-pr-finish` | `worker/1493-pipeline-retrieve` | `.signals/issue-1493-bge-bundle/w2-pipeline-retrieve.done.json` | `telegram_bot/agents/rag_pipeline.py`, `telegram_bot/graph/nodes/retrieve.py`, `tests/unit/agents/test_rag_pipeline.py`, `tests/unit/graph/test_retrieve_node.py` |
| 3 | `w3-scoring` | `pr-worker` / `opencode-go/kimi-k2.6` | `swarm-pr-finish` | `worker/1493-scoring` | `.signals/issue-1493-bge-bundle/w3-scoring.done.json` | `telegram_bot/scoring.py`, `tests/unit/test_bot_scores.py` |
| 3 | `w3-docs` | `pr-worker` / `opencode-go/kimi-k2.6` | `project-docs-maintenance`, `swarm-pr-finish` | `worker/1493-docs` | `.signals/issue-1493-bge-bundle/w3-docs.done.json` | `telegram_bot/integrations/embeddings.py`, `telegram_bot/services/bge_m3_client.py`, `docs/adr/0004-redisvl-semantic-cache.md`, `docs/indexes/observability-and-storage.md` |
| 4 | `w4-integration` | `pr-worker` / `opencode-go/kimi-k2.6` | `swarm-pr-finish` | `issue/1493-bge-m3-query-vector-bundle` | `.signals/issue-1493-bge-bundle/w4-integration.done.json` | All files changed by Waves 1-3, only for merge conflict fixes and final focused verification |
| 5 | `w5-pr-review` | `pr-review` / `opencode-go/deepseek-v4-pro` | `gh-pr-review`, `swarm-pr-finish` | read-only PR head worktree | `.signals/issue-1493-bge-bundle/w5-pr-review.done.json` | Read-only; no reserved write files |

### Worker Prompt Payloads

Every worker prompt must start with:

```text
## STEP 0 POLICY GATE
Before any tool call or command, acknowledge:
`POLICY_ACK docs_lookup=forbidden local_only=true`.
Use only the prompt file, assigned worktree, explicitly allowed repo files,
launch metadata, signal files, listed local logs/artifacts, and required
OpenCode skills. Do not use OpenCode webfetch, websearch, MCP Exa, MCP
Context7, official docs, or broad external research. If missing information
requires external lookup, return status:"blocked" with the missing artifact or
policy escalation needed.
```

Common payload fields:

```text
Issue: #1493 Cache BGE-M3 dense/sparse/ColBERT query vectors as one Redis bundle
Base branch: dev
Integration branch: issue/1493-bge-m3-query-vector-bundle
Docs lookup policy: forbidden
Verification budget: focused_only
Finish contract: commit changes, push worker branch if remote is available,
write strict DONE/FAILED/BLOCKED JSON to SIGNAL_PATH with changed_files,
commit_sha, branch, checks_run, command evidence, blockers_found, and new_bugs.
```

Wave-specific briefs:

- `w1-cache-contract`: implement Tasks 1-2 only. Do not touch pipeline behavior. Focused checks:
  `pytest tests/unit/services/test_bge_m3_query_bundle.py tests/unit/integrations/test_cache_bge_m3_query_bundle.py -q`.
- `w2-core-graph`: implement Tasks 3-4 for `rag_core.py` and `graph/nodes/cache.py` only. Do not edit `rag_pipeline.py` or `retrieve.py`. Focused checks:
  `pytest tests/unit/services/test_rag_core_embedding_bundle.py tests/unit/graph/test_cache_nodes.py -q`.
- `w2-pipeline-retrieve`: implement Task 5 for agent pipeline/retrieve node only. Do not edit `rag_core.py` or `graph/nodes/cache.py`. Focused checks:
  `pytest tests/unit/agents/test_rag_pipeline.py -k "cache_check or colbert or rewrite or reembed or hybrid_retrieve" tests/unit/graph/test_retrieve_node.py -q`.
- `w3-scoring`: implement Task 6 only. Focused check:
  `pytest tests/unit/test_bot_scores.py -q`.
- `w3-docs`: implement Task 7 docs/docstring changes only. Focused checks:
  `pytest tests/unit/services/test_bge_m3_client.py -q` and `ruff check telegram_bot/integrations/embeddings.py telegram_bot/services/bge_m3_client.py` if `ruff` is available.
- `w4-integration`: merge Waves 1-3, resolve conflicts without redesigning behavior, run the combined focused checks listed in Task 7 Step 3 and Step 4, then open/update one PR linked to `#1493`.
- `w5-pr-review`: read-only review of the final PR head SHA. Prioritize behavioral regressions, cache semantics, Qdrant vector inputs, misleading Langfuse scores, missing tests, and unsafe broad changes.

### Launch Checklist

- [ ] Orchestrator confirms live pane:

```bash
ORCH_PANE=$(tmux display-message -p '#{pane_id}')
tmux display-message -p -t "$ORCH_PANE" '#{pane_dead}'
```

Expected: `0`.

- [ ] Orchestrator creates integration branch/worktree from `dev`.
- [ ] Launch Wave 1 through the OpenCode launcher with `OPENCODE_AGENT=pr-worker`, `OPENCODE_MODEL=opencode-go/kimi-k2.6`, `OPENCODE_REQUIRED_SKILLS=swarm-pr-finish`, and `SWARM_LOCAL_ONLY=1`.
- [ ] Validate Wave 1 DONE JSON and merge it before launching Wave 2.
- [ ] Launch Wave 2 workers in parallel only after Wave 1 is integrated.
- [ ] Validate Wave 2 DONE JSON artifacts and bounded diffs before Wave 3.
- [ ] Launch Wave 3 workers in parallel.
- [ ] Integrate all branches into `issue/1493-bge-m3-query-vector-bundle`.
- [ ] Run final focused checks.
- [ ] Open/update PR, then launch `w5-pr-review` read-only on the current head SHA.
- [ ] If review finds blockers, launch `pr-review-fix` with only named blocker files reserved, then launch a fresh read-only review worker.

---

### Task 1: Bundle Contract

**Files:**
- Create: `telegram_bot/services/bge_m3_query_bundle.py`
- Create: `tests/unit/services/test_bge_m3_query_bundle.py`

- [ ] **Step 1: Write failing serialization tests**

```python
from telegram_bot.services.bge_m3_query_bundle import (
    BGE_M3_QUERY_BUNDLE_VERSION,
    BgeM3QueryVectorBundle,
    make_bge_m3_query_bundle_key_material,
)


def test_bundle_round_trips_json_dict() -> None:
    bundle = BgeM3QueryVectorBundle(
        dense=[0.1, 0.2],
        sparse={"indices": [1, 2], "values": [0.3, 0.4]},
        colbert=[[0.5, 0.6], [0.7, 0.8]],
        model="BAAI/bge-m3",
        max_length=512,
        version=BGE_M3_QUERY_BUNDLE_VERSION,
    )

    parsed = BgeM3QueryVectorBundle.from_json_dict(bundle.to_json_dict())

    assert parsed == bundle
    assert parsed.is_complete()


def test_bundle_rejects_missing_colbert() -> None:
    payload = {
        "dense": [0.1],
        "sparse": {"indices": [1], "values": [0.2]},
        "colbert": [],
        "model": "BAAI/bge-m3",
        "max_length": 512,
        "version": BGE_M3_QUERY_BUNDLE_VERSION,
    }

    parsed = BgeM3QueryVectorBundle.from_json_dict(payload)

    assert parsed is None


def test_key_material_normalizes_query_and_includes_model_contract() -> None:
    a = make_bge_m3_query_bundle_key_material("ВНЖ?", model="BAAI/bge-m3", max_length=512)
    b = make_bge_m3_query_bundle_key_material("  внж  ", model="BAAI/bge-m3", max_length=512)
    c = make_bge_m3_query_bundle_key_material("внж", model="other", max_length=512)

    assert a == b
    assert a != c
    assert "BAAI/bge-m3" in a
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/services/test_bge_m3_query_bundle.py -q`

Expected: FAIL with `ModuleNotFoundError` or missing symbol errors.

- [ ] **Step 3: Implement the bundle module**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


BGE_M3_QUERY_BUNDLE_MODEL = "BAAI/bge-m3"
BGE_M3_QUERY_BUNDLE_MAX_LENGTH = 512
BGE_M3_QUERY_BUNDLE_VERSION = "v1"


def _normalize_query_for_bundle(text: str) -> str:
    import re

    return re.sub(r"[^\w\s]+$", "", text.strip().lower()).strip()


def make_bge_m3_query_bundle_key_material(
    query: str,
    *,
    model: str = BGE_M3_QUERY_BUNDLE_MODEL,
    max_length: int = BGE_M3_QUERY_BUNDLE_MAX_LENGTH,
    version: str = BGE_M3_QUERY_BUNDLE_VERSION,
) -> str:
    normalized = _normalize_query_for_bundle(query)
    return f"{version}:{model}:{max_length}:{normalized}"


@dataclass(frozen=True)
class BgeM3QueryVectorBundle:
    dense: list[float]
    sparse: dict[str, Any]
    colbert: list[list[float]]
    model: str = BGE_M3_QUERY_BUNDLE_MODEL
    max_length: int = BGE_M3_QUERY_BUNDLE_MAX_LENGTH
    version: str = BGE_M3_QUERY_BUNDLE_VERSION

    def is_complete(self) -> bool:
        return bool(
            self.dense
            and self.sparse.get("indices") is not None
            and self.sparse.get("values") is not None
            and self.colbert
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "dense": self.dense,
            "sparse": self.sparse,
            "colbert": self.colbert,
            "model": self.model,
            "max_length": self.max_length,
            "version": self.version,
        }

    @classmethod
    def from_json_dict(cls, payload: Any) -> "BgeM3QueryVectorBundle | None":
        if not isinstance(payload, dict):
            return None
        dense = payload.get("dense")
        sparse = payload.get("sparse")
        colbert = payload.get("colbert")
        if not isinstance(dense, list) or not isinstance(sparse, dict) or not isinstance(colbert, list):
            return None
        bundle = cls(
            dense=list(dense),
            sparse=dict(sparse),
            colbert=[list(row) for row in colbert],
            model=str(payload.get("model") or BGE_M3_QUERY_BUNDLE_MODEL),
            max_length=int(payload.get("max_length") or BGE_M3_QUERY_BUNDLE_MAX_LENGTH),
            version=str(payload.get("version") or BGE_M3_QUERY_BUNDLE_VERSION),
        )
        return bundle if bundle.is_complete() else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/services/test_bge_m3_query_bundle.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add telegram_bot/services/bge_m3_query_bundle.py tests/unit/services/test_bge_m3_query_bundle.py
git commit -m "feat: add bge m3 query vector bundle contract"
```

---

### Task 2: Redis Bundle Cache Tier

**Files:**
- Modify: `telegram_bot/integrations/cache.py:1-653`
- Create: `tests/unit/integrations/test_cache_bge_m3_query_bundle.py`

- [ ] **Step 1: Write failing cache tests**

```python
from telegram_bot.integrations.cache import CacheLayerManager
from telegram_bot.services.bge_m3_query_bundle import BgeM3QueryVectorBundle


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl


async def test_store_and_get_bge_m3_query_bundle_round_trips() -> None:
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    fake = FakeRedis()
    cache.redis = fake
    bundle = BgeM3QueryVectorBundle(
        dense=[0.1],
        sparse={"indices": [1], "values": [0.2]},
        colbert=[[0.3, 0.4]],
    )

    await cache.store_bge_m3_query_bundle("ВНЖ?", bundle)
    hit = await cache.get_bge_m3_query_bundle(" внж ")

    assert hit == bundle
    assert list(fake.ttls.values()) == [7 * 86400]


async def test_get_bge_m3_query_bundle_returns_none_for_incomplete_payload() -> None:
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    fake = FakeRedis()
    cache.redis = fake
    await cache.store_exact("bge_m3_query_bundle", "bad-key", {"dense": [0.1]})

    hit = await cache.get_bge_m3_query_bundle("bad-key")

    assert hit is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/integrations/test_cache_bge_m3_query_bundle.py -q`

Expected: FAIL because cache methods/tier do not exist.

- [ ] **Step 3: Add cache tier and methods**

Implementation notes:

- Add `"bge_m3_query_bundle": 7 * 86400` to `DEFAULT_TTLS`.
- Add `"bge_m3_query_bundle"` to `_METRIC_TIERS`.
- Import the bundle helpers near existing imports:

```python
from telegram_bot.services.bge_m3_query_bundle import (
    BGE_M3_QUERY_BUNDLE_MAX_LENGTH,
    BGE_M3_QUERY_BUNDLE_MODEL,
    BgeM3QueryVectorBundle,
    make_bge_m3_query_bundle_key_material,
)
```

- Add methods near the embedding/sparse convenience methods:

```python
    async def get_bge_m3_query_bundle(
        self,
        text: str,
        *,
        model: str = BGE_M3_QUERY_BUNDLE_MODEL,
        max_length: int = BGE_M3_QUERY_BUNDLE_MAX_LENGTH,
    ) -> BgeM3QueryVectorBundle | None:
        key_material = make_bge_m3_query_bundle_key_material(
            text, model=model, max_length=max_length
        )
        payload = await self.get_exact("bge_m3_query_bundle", _hash(key_material))
        bundle = BgeM3QueryVectorBundle.from_json_dict(payload)
        return bundle

    async def store_bge_m3_query_bundle(
        self,
        text: str,
        bundle: BgeM3QueryVectorBundle,
    ) -> None:
        if not bundle.is_complete():
            return
        key_material = make_bge_m3_query_bundle_key_material(
            text, model=bundle.model, max_length=bundle.max_length, version=bundle.version
        )
        await self.store_exact(
            "bge_m3_query_bundle",
            _hash(key_material),
            bundle.to_json_dict(),
        )
```

- Keep existing `get_embedding()` / `store_embedding()` and sparse cache methods for legacy callers and SemanticCache vector compatibility.

- [ ] **Step 4: Run cache tests**

Run: `pytest tests/unit/integrations/test_cache_bge_m3_query_bundle.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add telegram_bot/integrations/cache.py tests/unit/integrations/test_cache_bge_m3_query_bundle.py
git commit -m "feat: cache bge m3 query vector bundles in redis"
```

---

### Task 3: Shared Embedding Core Uses Bundle First

**Files:**
- Modify: `telegram_bot/services/rag_core.py:204-264`
- Test: `tests/unit/services/test_rag_core_embedding_bundle.py`

- [ ] **Step 1: Write failing core tests**

```python
from unittest.mock import AsyncMock, MagicMock

from telegram_bot.services.bge_m3_query_bundle import BgeM3QueryVectorBundle
from telegram_bot.services.rag_core import compute_query_embedding


async def test_compute_query_embedding_uses_bundle_cache_before_dense_cache() -> None:
    bundle = BgeM3QueryVectorBundle(
        dense=[0.1],
        sparse={"indices": [1], "values": [0.2]},
        colbert=[[0.3]],
    )
    cache = AsyncMock()
    cache.get_bge_m3_query_bundle = AsyncMock(return_value=bundle)
    cache.get_embedding = AsyncMock()
    embeddings = MagicMock()

    dense, sparse, colbert, from_cache = await compute_query_embedding(
        "внж", cache=cache, embeddings=embeddings
    )

    assert dense == bundle.dense
    assert sparse == bundle.sparse
    assert colbert == bundle.colbert
    assert from_cache is True
    cache.get_embedding.assert_not_awaited()


async def test_compute_query_embedding_bundle_miss_calls_hybrid_colbert_once_and_stores_bundle() -> None:
    cache = AsyncMock()
    cache.get_bge_m3_query_bundle = AsyncMock(return_value=None)
    cache.store_bge_m3_query_bundle = AsyncMock()
    cache.store_embedding = AsyncMock()
    cache.store_sparse_embedding = AsyncMock()
    embeddings = MagicMock()
    embeddings.aembed_hybrid_with_colbert = AsyncMock(
        return_value=([0.1], {"indices": [1], "values": [0.2]}, [[0.3]])
    )

    dense, sparse, colbert, from_cache = await compute_query_embedding(
        "внж", cache=cache, embeddings=embeddings
    )

    assert (dense, sparse, colbert, from_cache) == (
        [0.1],
        {"indices": [1], "values": [0.2]},
        [[0.3]],
        False,
    )
    embeddings.aembed_hybrid_with_colbert.assert_awaited_once_with("внж")
    cache.store_bge_m3_query_bundle.assert_awaited_once()
    cache.store_embedding.assert_awaited_once_with("внж", [0.1])
    cache.store_sparse_embedding.assert_awaited_once_with("внж", {"indices": [1], "values": [0.2]})


async def test_compute_query_embedding_legacy_dense_cache_still_works_without_bundle_api() -> None:
    cache = AsyncMock()
    del cache.get_bge_m3_query_bundle
    cache.get_embedding = AsyncMock(return_value=[0.1])
    embeddings = MagicMock()

    dense, sparse, colbert, from_cache = await compute_query_embedding(
        "legacy", cache=cache, embeddings=embeddings
    )

    assert dense == [0.1]
    assert sparse is None
    assert colbert is None
    assert from_cache is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/services/test_rag_core_embedding_bundle.py -q`

Expected: FAIL because bundle lookup/store is not wired.

- [ ] **Step 3: Implement bundle-first core logic**

Implementation outline:

```python
    if pre_computed is not None:
        return (pre_computed, pre_computed_sparse, pre_computed_colbert, False)

    get_bundle = getattr(cache, "get_bge_m3_query_bundle", None)
    has_bundle_cache = callable(get_bundle) and asyncio.iscoroutinefunction(get_bundle)
    if has_bundle_cache:
        bundle = await get_bundle(query)
        if bundle is not None:
            return (bundle.dense, bundle.sparse, bundle.colbert, True)

    has_hybrid_colbert = callable(getattr(embeddings, "aembed_hybrid_with_colbert", None)) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid_with_colbert)
    if has_hybrid_colbert and has_bundle_cache:
        dense, sparse, colbert = await embeddings.aembed_hybrid_with_colbert(query)
        bundle = BgeM3QueryVectorBundle(dense=dense, sparse=sparse, colbert=colbert)
        store_bundle = getattr(cache, "store_bge_m3_query_bundle", None)
        if callable(store_bundle) and asyncio.iscoroutinefunction(store_bundle):
            await store_bundle(query, bundle)
        await cache.store_embedding(query, dense)
        await cache.store_sparse_embedding(query, sparse)
        return (dense, sparse, colbert, False)
```

Then keep the existing legacy `get_embedding()` / `aembed_hybrid()` / `aembed_query()` fallback below it.

Important behavior:

- Do not call `aembed_hybrid_with_colbert()` when `pre_computed` is passed.
- Do not require the bundle API for old tests/mocks; legacy dense cache must still pass.
- `embeddings_cache_hit=True` should mean "query vector came from Redis", whether from legacy dense cache or full bundle cache.

- [ ] **Step 4: Run focused core tests**

Run: `pytest tests/unit/services/test_rag_core_embedding_bundle.py tests/unit/graph/test_cache_nodes.py::TestCacheCheckNode::test_hit_path_returns_cached -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add telegram_bot/services/rag_core.py tests/unit/services/test_rag_core_embedding_bundle.py
git commit -m "feat: prefer full bge m3 vector bundle in rag core"
```

---

### Task 4: Remove Extra ColBERT Encode In Cache Check Paths

**Files:**
- Modify: `telegram_bot/graph/nodes/cache.py:84-198`
- Modify: `telegram_bot/agents/rag_pipeline.py:187-315`
- Modify: `tests/unit/graph/test_cache_nodes.py:233-306`
- Modify: `tests/unit/agents/test_rag_pipeline.py:1380-1500`

- [ ] **Step 1: Update failing graph-node test**

Replace `test_cache_check_computes_colbert_when_embedding_cached` with a bundle-hit test:

```python
async def test_cache_check_uses_bundle_hit_without_extra_colbert_encode(self):
    bundle = BgeM3QueryVectorBundle(
        dense=[0.1] * 1024,
        sparse={"indices": [1], "values": [0.5]},
        colbert=[[0.2] * 1024] * 4,
    )
    mock_cache = AsyncMock()
    mock_cache.get_bge_m3_query_bundle = AsyncMock(return_value=bundle)
    mock_cache.check_semantic = AsyncMock(return_value=None)
    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid_with_colbert = AsyncMock()
    mock_embeddings.aembed_colbert_query = AsyncMock()

    state = {
        "messages": [{"role": "user", "content": "test query"}],
        "query_type": "GENERAL",
        "latency_stages": {},
    }

    result = await cache_check_node(state, _make_runtime(cache=mock_cache, embeddings=mock_embeddings))

    assert result["query_embedding"] == bundle.dense
    assert result["colbert_query"] == bundle.colbert
    mock_embeddings.aembed_hybrid_with_colbert.assert_not_awaited()
    mock_embeddings.aembed_colbert_query.assert_not_awaited()
```

- [ ] **Step 2: Update failing agent-pipeline tests**

Add or replace `_cache_check` tests:

```python
async def test_cache_check_bundle_hit_returns_colbert_without_bge(mock_cache):
    from telegram_bot.agents.rag_pipeline import _cache_check
    from telegram_bot.services.bge_m3_query_bundle import BgeM3QueryVectorBundle

    bundle = BgeM3QueryVectorBundle(
        dense=[0.1] * 1024,
        sparse={"indices": [1], "values": [0.5]},
        colbert=[[0.2] * 1024] * 4,
    )
    mock_cache.get_bge_m3_query_bundle = AsyncMock(return_value=bundle)
    mock_cache.check_semantic = AsyncMock(return_value=None)
    embeddings = MagicMock()
    embeddings.aembed_hybrid_with_colbert = AsyncMock()
    embeddings.aembed_colbert_query = AsyncMock()

    result = await _cache_check(
        "test query",
        "GENERAL",
        1,
        cache=mock_cache,
        embeddings=embeddings,
        latency_stages={},
    )

    assert result["colbert_query"] == bundle.colbert
    embeddings.aembed_hybrid_with_colbert.assert_not_awaited()
    embeddings.aembed_colbert_query.assert_not_awaited()
```

- [ ] **Step 3: Run tests to verify old behavior fails**

Run: `pytest tests/unit/graph/test_cache_nodes.py::TestCacheCheckNode tests/unit/agents/test_rag_pipeline.py -k "cache_check and colbert" -q`

Expected: FAIL on current code because it still performs post-miss ColBERT encoding in some partial-cache paths.

- [ ] **Step 4: Simplify cache-check post-miss logic**

Change both cache-check implementations:

- If `compute_query_embedding()` returns `colbert_query`, use it.
- If it returns `None`, allow only the legacy `aembed_colbert_query()` fallback when there is no bundle cache method available. Do not call `aembed_hybrid_with_colbert()` from `cache_check_node()` / `_cache_check()`; the shared core owns that one-call path.

Pseudo-code:

```python
    if colbert_query is None:
        has_bundle_cache = callable(getattr(cache, "get_bge_m3_query_bundle", None))
        _has_colbert_only = callable(getattr(embeddings, "aembed_colbert_query", None)) and asyncio.iscoroutinefunction(embeddings.aembed_colbert_query)
        if not has_bundle_cache and _has_colbert_only:
            try:
                colbert_query = await embeddings.aembed_colbert_query(query)
            except Exception:
                logger.debug("ColBERT query encode failed (non-critical), skipping")
```

Rationale:

- Bundle-capable deployments get dense+sparse+ColBERT from `compute_query_embedding()`.
- Legacy deployments can still use the explicit ColBERT-only method.
- The known bad path, dense/sparse cache hit followed by `aembed_hybrid_with_colbert()`, disappears.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/unit/graph/test_cache_nodes.py tests/unit/agents/test_rag_pipeline.py -k "cache_check or colbert" -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add telegram_bot/graph/nodes/cache.py telegram_bot/agents/rag_pipeline.py tests/unit/graph/test_cache_nodes.py tests/unit/agents/test_rag_pipeline.py
git commit -m "fix: avoid extra colbert encode after vector cache hit"
```

---

### Task 5: Rewrite/Re-Embed Branches Use Bundle

**Files:**
- Modify: `telegram_bot/agents/rag_pipeline.py:358-395`
- Modify: `telegram_bot/graph/nodes/retrieve.py:122-204`
- Modify: `tests/unit/agents/test_rag_pipeline.py`
- Modify: `tests/unit/graph/test_retrieve_node.py`

- [ ] **Step 1: Write failing tests for rewrite/re-embed**

Agent pipeline test:

```python
async def test_hybrid_retrieve_reembed_uses_bundle_cache(mock_cache, mock_sparse, mock_qdrant):
    from telegram_bot.agents.rag_pipeline import _hybrid_retrieve
    from telegram_bot.services.bge_m3_query_bundle import BgeM3QueryVectorBundle

    bundle = BgeM3QueryVectorBundle(
        dense=[0.1] * 1024,
        sparse={"indices": [1], "values": [0.2]},
        colbert=[[0.3] * 1024],
    )
    mock_cache.get_bge_m3_query_bundle = AsyncMock(return_value=bundle)
    embeddings = MagicMock()
    embeddings.aembed_hybrid_with_colbert = AsyncMock()

    result = await _hybrid_retrieve(
        "rewritten query",
        None,
        cache=mock_cache,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        embeddings=embeddings,
        latency_stages={},
    )

    assert result["sparse_embedding"] == bundle.sparse
    embeddings.aembed_hybrid_with_colbert.assert_not_awaited()
```

Graph retrieve test should mirror this with `retrieve_node()` and `state["query_embedding"] = None`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/agents/test_rag_pipeline.py -k "reembed_uses_bundle" tests/unit/graph/test_retrieve_node.py -k "reembed_uses_bundle" -q`

Expected: FAIL because current rewrite/re-embed branches inspect dense/sparse separately.

- [ ] **Step 3: Replace ad hoc re-embed logic with shared core**

In both rewrite/re-embed branches, call:

```python
from telegram_bot.services.rag_core import compute_query_embedding

dense_vector, sparse_vector, colbert_query, embeddings_cache_hit = await compute_query_embedding(
    query,
    cache=cache,
    embeddings=embeddings,
)
```

Notes:

- Preserve existing `sparse_embeddings` fallback only if `embeddings` is absent or shared core raises and the old fallback behavior is intentionally retained.
- Preserve search-cache key behavior.
- If `colbert_query` is populated, Qdrant should use `hybrid_search_rrf_colbert()`.

- [ ] **Step 4: Run rewrite/retrieval tests**

Run: `pytest tests/unit/agents/test_rag_pipeline.py -k "rewrite or reembed or hybrid_retrieve" tests/unit/graph/test_retrieve_node.py -k "retrieve" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add telegram_bot/agents/rag_pipeline.py telegram_bot/graph/nodes/retrieve.py tests/unit/agents/test_rag_pipeline.py tests/unit/graph/test_retrieve_node.py
git commit -m "fix: use bge vector bundle when re-embedding rewritten queries"
```

---

### Task 6: Langfuse Cache-Hit Scoring Regression

**Files:**
- Modify: `telegram_bot/scoring.py:68-82`
- Modify: `tests/unit/test_bot_scores.py`

- [ ] **Step 1: Write failing scoring test**

```python
def test_cache_hit_does_not_emit_no_results_score(mock_lf):
    from telegram_bot.scoring import write_langfuse_scores

    result = {
        "query_type": "GENERAL",
        "cache_hit": True,
        "response": "Cached answer",
        "latency_stages": {"cache_check": 0.1},
        "pipeline_wall_ms": 100,
    }

    write_langfuse_scores(mock_lf, result, trace_id="trace-cache-hit")

    scores = {call.kwargs["name"]: call.kwargs["value"] for call in mock_lf.create_score.call_args_list}
    assert "results_count" not in scores
    assert "no_results" not in scores
    assert scores["semantic_cache_hit"] == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_bot_scores.py -k "cache_hit_does_not_emit_no_results_score" -q`

Expected: FAIL because `results_count=0` and `no_results=1` are currently emitted for semantic cache hits.

- [ ] **Step 3: Make result-count scores conditional**

In `write_langfuse_scores()`:

- Keep `semantic_cache_hit`, `embeddings_cache_hit`, `search_cache_hit`, and latency scores always written.
- Only emit `results_count` and `no_results` when `result.get("cache_hit")` is false or `search_results_count` is explicitly present from retrieved cached context.

Implementation outline:

```python
    scores = {
        ...
        "rerank_cache_hit": 1.0 if result.get("rerank_cache_hit") else 0.0,
        "llm_used": 1.0 if "generate" in latency_stages else 0.0,
        ...
    }
    if not result.get("cache_hit") or "search_results_count" in result:
        results_count = float(result.get("search_results_count", 0))
        scores["results_count"] = results_count
        scores["no_results"] = 1.0 if results_count == 0 else 0.0
```

- [ ] **Step 4: Run scoring tests**

Run: `pytest tests/unit/test_bot_scores.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add telegram_bot/scoring.py tests/unit/test_bot_scores.py
git commit -m "fix: avoid misleading no-results scores on semantic cache hits"
```

---

### Task 7: Docs And Verification

**Files:**
- Modify: `telegram_bot/integrations/embeddings.py:96-142`
- Modify: `telegram_bot/services/bge_m3_client.py:192-235`
- Modify: `docs/adr/0004-redisvl-semantic-cache.md`
- Modify: `docs/indexes/observability-and-storage.md`

- [ ] **Step 1: Update BGE docstrings**

Clarify:

- `/encode/hybrid` returns dense+sparse+ColBERT when the BGE service is configured to call FlagEmbedding with all `return_*` flags.
- `aembed_hybrid_with_colbert()` is the canonical one-call query-vector path.
- `aembed_colbert_query()` exists only as a compatibility fallback.

- [ ] **Step 2: Update cache docs**

Add a short section:

```markdown
### BGE-M3 Query Vector Bundle Cache

Semantic cache stores final answers and is checked first for cacheable RAG queries.
The BGE-M3 query vector bundle cache stores exact query vectors needed by retrieval:
dense, sparse lexical weights, and ColBERT multivectors. Bundle keys include normalized
query text, model, max length, and bundle version.

Runtime policy:

- semantic answer hit: return cached answer, skip Qdrant/LLM;
- bundle hit after semantic miss: skip BGE and call Qdrant with dense+sparse+ColBERT;
- bundle miss: call `/encode/hybrid` once and store the full bundle.
```

- [ ] **Step 3: Run focused unit tests**

Run:

```bash
pytest \
  tests/unit/services/test_bge_m3_query_bundle.py \
  tests/unit/integrations/test_cache_bge_m3_query_bundle.py \
  tests/unit/services/test_rag_core_embedding_bundle.py \
  tests/unit/graph/test_cache_nodes.py \
  tests/unit/graph/test_retrieve_node.py \
  tests/unit/agents/test_rag_pipeline.py \
  tests/unit/test_bot_scores.py \
  -q
```

Expected: PASS.

- [ ] **Step 4: Run Qdrant/BGE focused regression checks**

Run:

```bash
pytest tests/unit/test_qdrant_service.py tests/unit/services/test_bge_m3_client.py -q
```

Expected: PASS.

- [ ] **Step 5: Run lint/type checks if available locally**

Run:

```bash
ruff check telegram_bot tests/unit/services/test_bge_m3_query_bundle.py tests/unit/integrations/test_cache_bge_m3_query_bundle.py
```

Expected: PASS, or document skipped command if `ruff` is unavailable.

- [ ] **Step 6: Optional local trace verification**

If local Langfuse/Qdrant/BGE stack is up:

```bash
make validate-traces-fast
```

Expected trace shape for repeated `виды внж в болгарии?`:

- cold vector bundle miss: at most one BGE `/encode/hybrid` query-vector call;
- vector bundle hit + semantic miss: no BGE query-vector encode span, Qdrant receives ColBERT;
- semantic answer hit: no BGE/Qdrant/LLM spans.

- [ ] **Step 7: Commit docs**

```bash
git add telegram_bot/integrations/embeddings.py telegram_bot/services/bge_m3_client.py docs/adr/0004-redisvl-semantic-cache.md docs/indexes/observability-and-storage.md
git commit -m "docs: document bge m3 vector bundle cache policy"
```

---

## Acceptance Mapping

- Semantic cache hit avoids Qdrant/LLM and avoids BGE when the query vector is already cached as a bundle or dense vector.
- Semantic cache miss plus bundle hit avoids BGE and passes dense+sparse+ColBERT to Qdrant.
- Bundle miss calls `aembed_hybrid_with_colbert()` once, which maps to one `/encode/hybrid` call in `BGEM3HybridEmbeddings`.
- `hybrid_search_rrf_colbert` no longer depends on a dense/sparse cache hit followed by separate `/encode/colbert`.
- Tests cover semantic hit, bundle hit, bundle miss, legacy fallback, rewrite/re-embed, and cache-hit scoring.
- Langfuse no longer marks answer-cache hits as `no_results=1` unless retrieved context data is actually present and empty.
