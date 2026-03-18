# Grounded RAG Trace Retrieval Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the grounded RAG target state for `client_direct` and legal/relocation queries by fixing the runtime state contract, Langfuse trace contract, retrieval stage visibility, strict grounding behavior, and supporting Qdrant knowledge schema.

**Architecture:** Keep `pre_agent` as a first-class business stage, but make it emit a single downstream contract so `retrieval` and `generation` stop re-deriving known state. Make `retrieval.initial` and `retrieval.relax` explicit business stages on top of the existing Qdrant hybrid/ColBERT pipeline, and treat `strict grounded mode` plus `safe fallback` as valid runtime outcomes for high-risk legal and relocation questions. Extend ingestion metadata and payload indexes so runtime policy is supported by the corpus instead of fighting it.

**Tech Stack:** Python 3.12, aiogram, Langfuse Python SDK, Qdrant, BGE-M3, LiteLLM, pytest, Ruff, Redis

---

## Preflight

Run this plan in a dedicated worktree.

References to read before Task 1:

- `docs/plans/2026-03-18-grounded-rag-trace-retrieval-design.md`
- `telegram_bot/AGENTS.override.md`
- `docs/PIPELINE_OVERVIEW.md`

Suggested setup:

```bash
git worktree add ../rag-fresh-grounded-rag dev
cd ../rag-fresh-grounded-rag
uv sync
```

Baseline commands:

```bash
uv run pytest tests/unit/agents/test_rag_pipeline.py -q
uv run pytest tests/unit/pipelines/test_client_pipeline.py -q
uv run pytest tests/unit/services/test_generate_response.py -q
uv run pytest tests/unit/retrieval/test_topic_classifier.py -q
uv run pytest tests/unit/ingestion/test_payload_contract.py -q
uv run pytest tests/unit/test_qdrant_service.py -q
```

Expected: current baseline passes or any pre-existing failure is noted before edits start.

## Task 1: Root Trace And Propagation Contract

**Files:**
- Modify: `telegram_bot/observability.py:437-452`
- Modify: `telegram_bot/bot.py:2780-3075`
- Modify: `telegram_bot/pipelines/client.py:158-400`
- Test: `tests/unit/observability/test_trace_contracts.py:309-380`
- Test: `tests/unit/test_bot_scores.py:532-720`
- Test: `tests/unit/pipelines/test_client_pipeline.py`

**Step 1: Write the failing tests**

Add trace-contract tests that require root propagation metadata and route tags to exist early:

```python
def test_traced_pipeline_propagates_metadata_and_tags() -> None:
    with patch("telegram_bot.observability.propagate_attributes") as propagate:
        traced_pipeline(
            session_id="chat-1",
            user_id="42",
            tags=["telegram", "rag", "client_direct"],
            metadata={"route": "client_direct", "grounding_mode": "strict"},
        )
    propagate.assert_called_once_with(
        session_id="chat-1",
        user_id="42",
        tags=["telegram", "rag", "client_direct"],
        metadata={"route": "client_direct", "grounding_mode": "strict"},
    )
```

Add a client-pipeline test that asserts trace metadata includes `route`, `pipeline_mode`, `topic_hint`, and `grounding_mode`.

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/unit/observability/test_trace_contracts.py -q -k traced_pipeline
uv run pytest tests/unit/pipelines/test_client_pipeline.py -q -k grounding_mode
```

Expected: FAIL because `traced_pipeline()` does not yet accept propagated metadata and the pipeline does not write the new root metadata fields.

**Step 3: Write minimal implementation**

Extend `traced_pipeline()` to accept propagated metadata:

```python
def traced_pipeline(*, session_id: str, user_id: str, tags: list[str] | None = None, metadata: dict[str, str] | None = None):
    return propagate_attributes(
        session_id=session_id,
        user_id=user_id,
        tags=tags or [],
        metadata=metadata or {},
    )
```

In `bot.py` and `client.py`, make the root trace write stable top-level metadata:

```python
lf.update_current_trace(
    metadata={
        "route": "client_direct",
        "pipeline_mode": "client_direct",
        "query_type": query_type,
        "topic_hint": topic_hint or "",
        "grounding_mode": grounding_mode,
        "collection": config.get_collection_name(),
        "environment": config.langfuse_env,
    }
)
```

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/unit/observability/test_trace_contracts.py -q -k traced_pipeline
uv run pytest tests/unit/pipelines/test_client_pipeline.py -q -k 'grounding_mode or route'
```

Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/observability.py telegram_bot/bot.py telegram_bot/pipelines/client.py tests/unit/observability/test_trace_contracts.py tests/unit/test_bot_scores.py tests/unit/pipelines/test_client_pipeline.py
git commit -m "feat: add root trace propagation contract"
```

## Task 2: Pre-Agent Miss State Contract

**Files:**
- Create: `telegram_bot/pipelines/state_contract.py`
- Modify: `telegram_bot/bot.py:2879-3054`
- Modify: `telegram_bot/pipelines/client.py:241-273`
- Modify: `telegram_bot/agents/rag_pipeline.py:51-200`
- Test: `tests/unit/test_bot_handlers.py`
- Test: `tests/unit/pipelines/test_client_pipeline.py`
- Test: `tests/unit/agents/test_rag_pipeline.py`

**Step 1: Write the failing tests**

Add tests for a typed `pre_agent` miss contract:

```python
def test_build_pre_agent_miss_contract_sets_required_fields() -> None:
    contract = build_pre_agent_miss_contract(
        query_type="FAQ",
        topic_hint="legal",
        dense_vector=[0.1, 0.2],
        sparse_vector={"indices": [1], "values": [0.5]},
        colbert_query=[[0.2] * 4],
        grounding_mode="strict",
    )
    assert contract["cache_checked"] is True
    assert contract["cache_hit"] is False
    assert contract["embedding_bundle_ready"] is True
    assert contract["embedding_bundle_version"] == "bge_m3_hybrid_colbert"
    assert contract["retrieval_policy"] == "topic_then_relax"
```

Add a client-pipeline test that asserts `run_client_pipeline()` passes the contract object downstream instead of a loose set of ad hoc keys.

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/unit/test_bot_handlers.py -q -k pre_agent_miss_contract
uv run pytest tests/unit/pipelines/test_client_pipeline.py -q -k state_contract
uv run pytest tests/unit/agents/test_rag_pipeline.py -q -k semantic_cache_already_checked
```

Expected: FAIL because no shared contract object exists yet.

**Step 3: Write minimal implementation**

Create a `TypedDict` plus builders:

```python
class PreAgentStateContract(TypedDict, total=False):
    cache_checked: bool
    cache_hit: bool
    cache_scope: str
    embedding_bundle_ready: bool
    embedding_bundle_version: str
    dense_vector: list[float] | None
    sparse_vector: dict[str, Any] | None
    colbert_query: list[list[float]] | None
    query_type: str
    topic_hint: str | None
    retrieval_policy: str
    grounding_mode: str
```

Store it in `rag_result_store["state_contract"]`, pass it through `run_client_pipeline()`, and teach `rag_pipeline()` to consume that contract instead of rediscovering `cache_checked`, `topic_hint`, and embedding bundle pieces from scattered keys.

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/unit/test_bot_handlers.py -q -k pre_agent_miss_contract
uv run pytest tests/unit/pipelines/test_client_pipeline.py -q -k state_contract
uv run pytest tests/unit/agents/test_rag_pipeline.py -q -k 'semantic_cache_already_checked or pre_computed'
```

Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/pipelines/state_contract.py telegram_bot/bot.py telegram_bot/pipelines/client.py telegram_bot/agents/rag_pipeline.py tests/unit/test_bot_handlers.py tests/unit/pipelines/test_client_pipeline.py tests/unit/agents/test_rag_pipeline.py
git commit -m "feat: add pre-agent state contract"
```

## Task 3: Retrieval Initial And Relax Business Spans

**Files:**
- Modify: `telegram_bot/agents/rag_pipeline.py:209-470`
- Modify: `tests/contract/test_span_coverage_contract.py`
- Modify: `tests/contract/test_trace_families_contract.py`
- Modify: `tests/observability/trace_contract.yaml`
- Test: `tests/unit/agents/test_rag_pipeline.py:203-369`

**Step 1: Write the failing tests**

Add span-contract tests that require `retrieval.initial` and `retrieval.relax` to exist as business spans:

```python
def test_required_retrieval_stage_spans_present() -> None:
    spans = scan_observe_names("telegram_bot/agents/rag_pipeline.py")
    assert "retrieval.initial" in spans
    assert "retrieval.relax" in spans
```

Add a retrieval behavior test:

```python
async def test_relaxed_retrieval_emits_second_stage_only_when_needed():
    result = await _hybrid_retrieve(...)
    assert result["retrieval_relaxed_from_topic_filter"] is True
    assert result["qdrant_search_attempts"] == 2
```

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/contract/test_span_coverage_contract.py -q
uv run pytest tests/contract/test_trace_families_contract.py -q
uv run pytest tests/unit/agents/test_rag_pipeline.py -q -k 'topic_relax or retrieval_relax'
```

Expected: FAIL because only `hybrid-retrieve` exists today.

**Step 3: Write minimal implementation**

Split the current retrieval flow into small helpers:

```python
@observe(name="retrieval.initial", capture_input=False, capture_output=False)
async def _run_initial_retrieval(...): ...

@observe(name="retrieval.relax", capture_input=False, capture_output=False)
async def _run_relaxed_retrieval(...): ...
```

Keep `hybrid-retrieve` as the parent orchestration span, but move Qdrant calls into the new business children. Preserve the existing `initial_filters`, `final_filters`, and `qdrant_search_attempts` metadata.

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/contract/test_span_coverage_contract.py -q
uv run pytest tests/contract/test_trace_families_contract.py -q
uv run pytest tests/unit/agents/test_rag_pipeline.py -q -k 'topic_relax or retrieval_relax or uses_colbert_search'
```

Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/agents/rag_pipeline.py tests/contract/test_span_coverage_contract.py tests/contract/test_trace_families_contract.py tests/observability/trace_contract.yaml tests/unit/agents/test_rag_pipeline.py
git commit -m "feat: add retrieval initial and relax spans"
```

## Task 4: Strict Grounded Mode And Safe Fallback

**Files:**
- Create: `telegram_bot/services/grounding_policy.py`
- Modify: `src/retrieval/topic_classifier.py:104-115`
- Modify: `telegram_bot/pipelines/client.py:256-400`
- Modify: `telegram_bot/services/generate_response.py:365-520`
- Modify: `telegram_bot/config.py`
- Test: `tests/unit/retrieval/test_topic_classifier.py`
- Test: `tests/unit/services/test_generate_response.py`
- Test: `tests/unit/pipelines/test_client_pipeline.py`

**Step 1: Write the failing tests**

Add policy tests:

```python
def test_grounding_mode_is_strict_for_legal_query() -> None:
    assert get_grounding_mode(query_type="FAQ", topic_hint="legal") == "strict"

def test_grounding_mode_is_normal_for_generic_property_query() -> None:
    assert get_grounding_mode(query_type="GENERAL", topic_hint=None) == "normal"
```

Add a generation test:

```python
async def test_generate_response_returns_safe_fallback_when_strict_mode_has_weak_context():
    result = await generate_response(
        query="виды внж в болгарии",
        documents=[],
        grounding_mode="strict",
        ...
    )
    assert result["safe_fallback_used"] is True
    assert result["grounded"] is False
```

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/unit/retrieval/test_topic_classifier.py -q -k grounding
uv run pytest tests/unit/services/test_generate_response.py -q -k safe_fallback
uv run pytest tests/unit/pipelines/test_client_pipeline.py -q -k strict_grounded
```

Expected: FAIL because no grounding-policy module or strict fallback logic exists.

**Step 3: Write minimal implementation**

Create a policy helper:

```python
STRICT_TOPICS = {"legal", "relocation", "immigration"}

def get_grounding_mode(*, query_type: str, topic_hint: str | None) -> str:
    return "strict" if topic_hint in STRICT_TOPICS else "normal"

def should_safe_fallback(*, grounding_mode: str, documents: list[dict[str, Any]], sources_enabled: bool) -> bool:
    if grounding_mode != "strict":
        return False
    return len(documents) == 0 or not sources_enabled
```

Then integrate:

```python
if should_safe_fallback(...):
    return {
        "response": build_safe_fallback_response(documents),
        "safe_fallback_used": True,
        "grounded": False,
        "legal_answer_safe": False,
    }
```

Add config toggles only if a hard-coded default would make testing or rollout unsafe.

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/unit/retrieval/test_topic_classifier.py -q -k grounding
uv run pytest tests/unit/services/test_generate_response.py -q -k safe_fallback
uv run pytest tests/unit/pipelines/test_client_pipeline.py -q -k strict_grounded
```

Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/grounding_policy.py src/retrieval/topic_classifier.py telegram_bot/pipelines/client.py telegram_bot/services/generate_response.py telegram_bot/config.py tests/unit/retrieval/test_topic_classifier.py tests/unit/services/test_generate_response.py tests/unit/pipelines/test_client_pipeline.py
git commit -m "feat: add strict grounded mode with safe fallback"
```

## Task 5: Langfuse Score Contract For Grounding And Safety

**Files:**
- Modify: `telegram_bot/scoring.py:46-266`
- Modify: `tests/unit/observability/test_trace_contracts.py:21-210`
- Modify: `tests/unit/observability/test_score_coverage.py`
- Modify: `tests/unit/test_bot_scores.py:520-720`

**Step 1: Write the failing tests**

Add score contract tests:

```python
def test_grounding_scores_written_for_strict_legal_result():
    scores = _written_scores({
        **_MINIMAL_RESULT,
        "grounded": False,
        "sources_count": 0,
        "safe_fallback_used": True,
        "legal_answer_safe": False,
        "semantic_cache_safe_reuse": False,
    })
    assert "grounded" in scores
    assert "legal_answer_safe" in scores
    assert "semantic_cache_safe_reuse" in scores
    assert "safe_fallback_used" in scores
```

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/unit/observability/test_trace_contracts.py -q -k grounded
uv run pytest tests/unit/observability/test_score_coverage.py -q -k grounded
uv run pytest tests/unit/test_bot_scores.py -q -k legal_answer_safe
```

Expected: FAIL because the new scores are not written.

**Step 3: Write minimal implementation**

Extend `write_langfuse_scores()`:

```python
score(lf, trace_id, name="grounded", value=1 if result.get("grounded") else 0, data_type="BOOLEAN")
score(lf, trace_id, name="legal_answer_safe", value=1 if result.get("legal_answer_safe") else 0, data_type="BOOLEAN")
score(lf, trace_id, name="semantic_cache_safe_reuse", value=1 if result.get("semantic_cache_safe_reuse") else 0, data_type="BOOLEAN")
score(lf, trace_id, name="safe_fallback_used", value=1 if result.get("safe_fallback_used") else 0, data_type="BOOLEAN")
```

Do not overload metadata with these judgments.

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/unit/observability/test_trace_contracts.py -q -k grounded
uv run pytest tests/unit/observability/test_score_coverage.py -q -k grounded
uv run pytest tests/unit/test_bot_scores.py -q -k 'legal_answer_safe or safe_fallback'
```

Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/scoring.py tests/unit/observability/test_trace_contracts.py tests/unit/observability/test_score_coverage.py tests/unit/test_bot_scores.py
git commit -m "feat: add grounding and safety score contract"
```

## Task 6: Knowledge Schema And Payload Indexes

**Files:**
- Modify: `src/retrieval/topic_classifier.py:1-140`
- Modify: `src/ingestion/unified/qdrant_writer.py:211-240`
- Modify: `src/ingestion/indexer.py:161-224`
- Modify: `src/ingestion/unified/cli.py:363-392`
- Modify: `telegram_bot/setup_qdrant_indexes.py:31-88`
- Modify: `telegram_bot/services/qdrant.py:1106-1146`
- Test: `tests/unit/retrieval/test_topic_classifier.py`
- Test: `tests/unit/ingestion/test_payload_contract.py`
- Test: `tests/unit/test_qdrant_service.py:72-86`
- Test: `tests/unit/test_collection_verify.py`

**Step 1: Write the failing tests**

Add ingestion-schema tests:

```python
def test_payload_has_grounding_metadata_fields():
    payload = writer.build_payload(...)
    assert payload["metadata"]["jurisdiction"] == "bg"
    assert payload["metadata"]["language"] == "ru"
    assert payload["metadata"]["source_type"] in {"pdf", "docx", "gdrive"}
```

Add Qdrant filter tests:

```python
async def test_build_filter_maps_jurisdiction_and_audience():
    await service.hybrid_search_rrf(dense_vector=[0.1] * 1024, filters={"jurisdiction": "bg", "audience": "client"})
    must_keys = [c.key for c in service._client.query_points.call_args.kwargs["query_filter"].must]
    assert "metadata.jurisdiction" in must_keys
    assert "metadata.audience" in must_keys
```

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/unit/retrieval/test_topic_classifier.py -q
uv run pytest tests/unit/ingestion/test_payload_contract.py -q -k grounding_metadata
uv run pytest tests/unit/test_qdrant_service.py -q -k jurisdiction
uv run pytest tests/unit/test_collection_verify.py -q
```

Expected: FAIL because the new payload fields and indexes do not exist.

**Step 3: Write minimal implementation**

Extend payload creation with low-risk schema additions only:

```python
metadata["jurisdiction"] = "bg"
metadata["language"] = infer_language(source_path, file_metadata)
metadata["source_type"] = metadata.get("source_type") or infer_source_type(source_path)
metadata["audience"] = infer_audience(source_path, chunk.text)
```

Create payload indexes for the new restrictive fields:

```python
for field in ["metadata.topic", "metadata.doc_type", "metadata.jurisdiction", "metadata.audience", "metadata.language"]:
    client.create_payload_index(..., field_schema=PayloadSchemaType.KEYWORD)
```

Keep the schema additive. Do not redesign the full ingestion payload in one shot.

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/unit/retrieval/test_topic_classifier.py -q
uv run pytest tests/unit/ingestion/test_payload_contract.py -q
uv run pytest tests/unit/test_qdrant_service.py -q -k 'topic_and_doc_type_filters or jurisdiction'
uv run pytest tests/unit/test_collection_verify.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/retrieval/topic_classifier.py src/ingestion/unified/qdrant_writer.py src/ingestion/indexer.py src/ingestion/unified/cli.py telegram_bot/setup_qdrant_indexes.py telegram_bot/services/qdrant.py tests/unit/retrieval/test_topic_classifier.py tests/unit/ingestion/test_payload_contract.py tests/unit/test_qdrant_service.py tests/unit/test_collection_verify.py
git commit -m "feat: extend knowledge schema for grounded retrieval"
```

## Task 7: Legal Grounding Audit Harness

**Files:**
- Create: `tests/fixtures/retrieval/legal_grounding_cases.yaml`
- Create: `scripts/run_legal_grounding_audit.py`
- Modify: `tests/unit/test_validate_queries.py`
- Modify: `docs/plans/2026-03-18-grounded-rag-trace-retrieval-design.md`

**Step 1: Write the failing tests**

Create a fixture-shape test:

```python
def test_legal_grounding_fixture_has_required_keys():
    cases = yaml.safe_load(Path("tests/fixtures/retrieval/legal_grounding_cases.yaml").read_text())
    assert all({"query", "expected_topic", "expected_grounding_mode"} <= set(case) for case in cases)
```

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/unit/test_validate_queries.py -q -k legal_grounding
```

Expected: FAIL because the new fixture and audit command do not exist.

**Step 3: Write minimal implementation**

Create a compact legal audit fixture:

```yaml
- query: "виды внж в болгарии"
  expected_topic: "legal"
  expected_grounding_mode: "strict"
- query: "основания для внж в болгарии"
  expected_topic: "legal"
  expected_grounding_mode: "strict"
- query: "bulgaria residence permit categories"
  expected_topic: "legal"
  expected_grounding_mode: "strict"
```

Create a small audit runner that prints:

- `topic_hint`
- constrained result count
- relaxed result count
- top documents
- whether `safe_fallback` fired

Example skeleton:

```python
for case in cases:
    result = await run_case(case["query"])
    print(json.dumps({
        "query": case["query"],
        "topic_hint": result["topic_hint"],
        "initial_results_count": result["initial_results_count"],
        "results_count": result["search_results_count"],
        "safe_fallback_used": result.get("safe_fallback_used", False),
    }, ensure_ascii=False))
```

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/unit/test_validate_queries.py -q -k legal_grounding
uv run python scripts/run_legal_grounding_audit.py --limit 3
```

Expected: fixture test PASS and the script prints JSON lines for the sampled cases.

**Step 5: Commit**

```bash
git add tests/fixtures/retrieval/legal_grounding_cases.yaml scripts/run_legal_grounding_audit.py tests/unit/test_validate_queries.py docs/plans/2026-03-18-grounded-rag-trace-retrieval-design.md
git commit -m "feat: add legal grounding audit harness"
```

## Task 8: Full Verification And Rollout Notes

**Files:**
- Modify: `docs/plans/2026-03-18-grounded-rag-trace-retrieval-design.md`
- Modify: `docs/plans/2026-03-18-grounded-rag-trace-retrieval-implementation-plan.md`

**Step 1: Run targeted test suites**

Run:

```bash
uv run pytest tests/unit/agents/test_rag_pipeline.py -q
uv run pytest tests/unit/pipelines/test_client_pipeline.py -q
uv run pytest tests/unit/services/test_generate_response.py -q
uv run pytest tests/unit/retrieval/test_topic_classifier.py -q
uv run pytest tests/unit/ingestion/test_payload_contract.py -q
uv run pytest tests/unit/test_qdrant_service.py -q
uv run pytest tests/unit/observability/test_trace_contracts.py -q
uv run pytest tests/unit/observability/test_score_coverage.py -q
```

Expected: PASS

**Step 2: Run repository-wide fast checks**

Run:

```bash
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
uv run pytest tests/integration/test_graph_paths.py -n auto --dist=worksteal -q
```

Expected: PASS

**Step 3: Capture a real validation trace**

Run the local stack and send at least:

- `виды внж в болгарии?`
- `какие документы нужны для внж в болгарии?`
- `подбери квартиру у моря`

Expected trace behavior:

- `pre_agent` visible
- `retrieval.initial` visible
- `retrieval.relax` only when constrained retrieval is weak
- `strict grounded mode` visible on legal cases
- `safe_fallback` visible when evidence is insufficient

**Step 4: Update plan docs with outcomes**

Write a short execution note into the design doc summarizing:

- final trace contract
- final score names
- final payload schema fields
- whether legal audit showed corpus gaps

**Step 5: Final commit**

```bash
git add docs/plans/2026-03-18-grounded-rag-trace-retrieval-design.md docs/plans/2026-03-18-grounded-rag-trace-retrieval-implementation-plan.md
git commit -m "docs: record grounded RAG rollout verification"
```

## Execution Outcome

Status on 2026-03-18: implemented in dedicated worktree branch `wt/issue-1002-grounded-rag`.

Completed runtime changes:

- root trace metadata propagation now carries `route`, `pipeline_mode`, `query_type`, `topic_hint`, `grounding_mode`, `collection`, and `environment`
- `pre_agent` miss now emits `rag_result_store["state_contract"]` with typed cache and embedding bundle fields
- retrieval now exposes explicit `retrieval.initial` and `retrieval.relax` business spans
- strict grounding mode and safe fallback are active for legal, relocation, and immigration-style queries
- Langfuse score writing now includes `grounded`, `legal_answer_safe`, `semantic_cache_safe_reuse`, and `safe_fallback_used`
- ingestion payloads now add `metadata.jurisdiction`, `metadata.language`, `metadata.source_type`, and `metadata.audience`, with matching payload indexes where applicable
- legal grounding audit fixture and runner were added under `tests/fixtures/retrieval/` and `scripts/run_legal_grounding_audit.py`

Verification notes:

- targeted suites for agents, pipelines, generation, topic classification, ingestion payloads, Qdrant filters, observability, and score coverage passed during execution
- integration check `tests/integration/test_graph_paths.py -n auto --dist=worksteal -q` passed
- audit runner currently reports `audit_mode="offline_fixture_only"`; it validates fixture behavior but does not replace a live-stack trace capture
- if rollout requires production-readiness evidence for corpus sufficiency, capture live traces for the legal fixture set after deployment or against a local running stack
