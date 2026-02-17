# Unified Chat History + Kommo Rollout Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate bot to unified supervisor-only runtime and implement Kommo CRM lifecycle tools with verifiable quality gate.

**Architecture:** Use current LangGraph supervisor as the only runtime path for text query. Chat history stays in Qdrant (`conversation_history` collection) / Redis, session summary generated via `responses.parse` with fallback, CRM operations executed by separate tools through `KommoClient` with fail-soft and idempotency guard. Observability fixed in a single Langfuse trace tree.

**Tech Stack:** Python 3.12, LangGraph, Langfuse SDK, httpx, Qdrant client, pytest + xdist (`-n auto --dist=worksteal`).

**Parent issue:** #324

---

Skill composition for execution: `@test-driven-development` + `@test-suite-optimizer` + `@verification-before-completion`.

### Task 1: Session Summary Compatibility Guard (`responses.parse`)

> Maps to: #324 Step 2, #315

**Files:**
- Modify: `telegram_bot/services/session_summary.py`
- Test: `tests/unit/services/test_session_summary.py`

**Step 1: Write the failing test**

```python
async def test_generate_summary_uses_responses_parse_when_available(fake_llm):
    turns = [{"query": "ищу квартиру", "response": "подберу варианты"}]
    result = await generate_summary(turns=turns, llm=fake_llm)
    assert result is not None
    assert fake_llm.responses.parse_called is True
```

**Step 2: Run test to verify it fails**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/services/test_session_summary.py::test_generate_summary_uses_responses_parse_when_available -v`
Expected: FAIL (no full check of primary path).

**Step 3: Write minimal implementation**

```python
if hasattr(llm, "responses") and hasattr(llm.responses, "parse"):
    response = await llm.responses.parse(...)
    return getattr(response, "output_parsed", None)
# fallback path below
```

**Step 4: Run test to verify it passes**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/services/test_session_summary.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add telegram_bot/services/session_summary.py tests/unit/services/test_session_summary.py
git commit -m "test(summary): lock responses.parse primary path with fallback guard"
```

### Task 2: Kommo Client Contract (TDD)

> Maps to: #324 Step 4, #312

**Files:**
- Create: `telegram_bot/services/kommo_client.py`
- Test: `tests/unit/services/test_kommo_client.py`

**Step 1: Write the failing test**

```python
async def test_create_deal_maps_kommo_error_to_controlled_exception(httpx_mock):
    client = KommoClient(base_url="https://x.kommo.com", token="t")
    httpx_mock.add_response(status_code=401, json={"title": "Unauthorized"})
    with pytest.raises(KommoAuthError):
        await client.create_deal(name="Lead", pipeline_id=1)
```

**Step 2: Run test to verify it fails**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/services/test_kommo_client.py::test_create_deal_maps_kommo_error_to_controlled_exception -v`
Expected: FAIL (`KommoClient` does not exist).

**Step 3: Write minimal implementation**

```python
class KommoClient:
    async def create_deal(self, *, name: str, pipeline_id: int) -> int:
        resp = await self._client.post("/api/v4/leads", json=[{"name": name, "pipeline_id": pipeline_id}])
        if resp.status_code == 401:
            raise KommoAuthError("Unauthorized")
        resp.raise_for_status()
        return int(resp.json()["_embedded"]["leads"][0]["id"])
```

**Step 4: Run test to verify it passes**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/services/test_kommo_client.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add telegram_bot/services/kommo_client.py tests/unit/services/test_kommo_client.py
git commit -m "feat(kommo): add async KommoClient with typed error mapping"
```

### Task 3: Deal Draft Model from Session Summary

> Maps to: #324 Step 5, #312

**Files:**
- Create: `telegram_bot/services/deal_draft.py`
- Test: `tests/unit/services/test_deal_draft_generation.py`

**Step 1: Write the failing test**

```python
def test_build_deal_draft_from_summary_extracts_name_and_note():
    summary = SessionSummary(...)
    draft = build_deal_draft(user_id=1, summary=summary)
    assert draft.title
    assert "AI Summary" in draft.note
```

**Step 2: Run test to verify it fails**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/services/test_deal_draft_generation.py -v`
Expected: FAIL (`build_deal_draft` does not exist).

**Step 3: Write minimal implementation**

```python
@dataclass
class DealDraft:
    title: str
    note: str

def build_deal_draft(*, user_id: int, summary: SessionSummary) -> DealDraft:
    title = summary.brief[:80] or f"Telegram lead {user_id}"
    note = format_summary_as_note(summary)
    return DealDraft(title=title, note=note)
```

**Step 4: Run test to verify it passes**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/services/test_deal_draft_generation.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add telegram_bot/services/deal_draft.py tests/unit/services/test_deal_draft_generation.py
git commit -m "feat(crm): add DealDraft builder from SessionSummary"
```

### Task 4: CRM Tools in Supervisor Layer

> Maps to: #324 Step 5, #312

**Files:**
- Modify: `telegram_bot/agents/tools.py`
- Test: `tests/unit/agents/test_kommo_tools.py`

**Step 1: Write the failing test**

```python
async def test_crm_finalize_deal_from_session_fail_soft_on_kommo_error(mocker):
    tool = create_crm_finalize_tool(...)
    result = await tool.ainvoke({"query": "сохрани сделку"}, config={"configurable": {"user_id": 1}})
    assert "ошибка" in result.lower() or "попробуйте позже" in result.lower()
```

**Step 2: Run test to verify it fails**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_kommo_tools.py -v`
Expected: FAIL (CRM tools do not exist).

**Step 3: Write minimal implementation**

```python
@tool
async def crm_finalize_deal_from_session(config: RunnableConfig) -> str:
    try:
        ...
        return f"Сделка создана: {deal_id}"
    except Exception:
        return "Не удалось обновить CRM. Попробуйте позже."
```

**Step 4: Run test to verify it passes**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_kommo_tools.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add telegram_bot/agents/tools.py tests/unit/agents/test_kommo_tools.py
git commit -m "feat(agent): add Kommo lifecycle tools with fail-soft behavior"
```

### Task 5: Wire CRM Tools Into Supervisor Bot Path

> Maps to: #324 Step 5, #312

**Files:**
- Modify: `telegram_bot/bot.py`
- Test: `tests/unit/agents/test_finalize_deal_from_session.py`

**Step 1: Write the failing test**

```python
async def test_supervisor_toolset_includes_crm_tools_when_kommo_enabled(bot_fixture):
    tools = bot_fixture._build_supervisor_tools()
    assert any(t.name == "crm_finalize_deal_from_session" for t in tools)
```

**Step 2: Run test to verify it fails**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_finalize_deal_from_session.py -v`
Expected: FAIL (tool not connected).

**Step 3: Write minimal implementation**

```python
if self.config.kommo_enabled and self._history_service is not None:
    tools.append(create_crm_finalize_tool(...))
```

**Step 4: Run test to verify it passes**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_finalize_deal_from_session.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add telegram_bot/bot.py tests/unit/agents/test_finalize_deal_from_session.py
git commit -m "feat(bot): include CRM tools in supervisor toolset"
```

### Task 6: Remove Legacy Monolith Runtime Path

> Maps to: #324 Step 6, #310

**Files:**
- Modify: `telegram_bot/config.py`
- Modify: `telegram_bot/bot.py`
- Test: `tests/unit/test_bot_handlers.py`

**Step 1: Write the failing test**

```python
async def test_handle_query_uses_supervisor_by_default(bot_fixture, message):
    await bot_fixture.handle_query(message)
    assert bot_fixture._handle_query_supervisor.await_count == 1
```

**Step 2: Run test to verify it fails**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/test_bot_handlers.py -k supervisor -v`
Expected: FAIL (legacy path still default).

**Step 3: Write minimal implementation**

```python
# config.py
use_supervisor: bool = Field(default=True, ...)

# bot.py
if not self.config.use_supervisor:
    return await self._handle_query_legacy(...)
```

**Step 4: Run test to verify it passes**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/test_bot_handlers.py -k supervisor -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add telegram_bot/config.py telegram_bot/bot.py tests/unit/test_bot_handlers.py
git commit -m "refactor(runtime): make supervisor default and isolate legacy fallback"
```

### Task 7: Unified Langfuse Scores for CRM Operations

> Maps to: #324 Step 7, #241

**Files:**
- Modify: `telegram_bot/bot.py`
- Test: `tests/unit/agents/test_supervisor_observability.py`

**Step 1: Write the failing test**

```python
async def test_crm_scores_written_to_current_trace(lf_mock, supervisor_result):
    _write_langfuse_scores(lf_mock, supervisor_result)
    lf_mock.score_current_trace.assert_any_call(name="crm_write_success", value=1, data_type="BOOLEAN")
```

**Step 2: Run test to verify it fails**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_supervisor_observability.py -v`
Expected: FAIL (CRM score signals missing).

**Step 3: Write minimal implementation**

```python
lf.score_current_trace(name="crm_write_success", value=1, data_type="BOOLEAN")
lf.score_current_trace(name="crm_deal_created", value=1, data_type="BOOLEAN")
lf.score_current_trace(name="crm_deal_create_latency_ms", value=float(latency_ms))
```

**Step 4: Run test to verify it passes**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_supervisor_observability.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add telegram_bot/bot.py tests/unit/agents/test_supervisor_observability.py
git commit -m "feat(observability): add CRM lifecycle scores in unified trace"
```

### Task 8: Evaluation Qdrant SDK Migration (#314)

> Maps to: #324 Step 8, #314

**Files:**
- Modify: `src/evaluation/search_engines.py`
- Test: `tests/unit/evaluation/test_search_engines.py`

**Step 1: Write the failing test**

```python
def test_qdrant_search_engine_uses_query_points_sdk(mocker):
    mock = mocker.patch("src.evaluation.search_engines.QdrantClient")
    engine = QdrantSearchEngine(...)
    engine.search("test")
    assert mock.return_value.query_points.called
```

**Step 2: Run test to verify it fails**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/evaluation/test_search_engines.py -k qdrant -v`
Expected: FAIL (raw REST calls still used).

**Step 3: Write minimal implementation**

```python
hits = self.client.query_points(
    collection_name=self.collection,
    query=query_vector,
    query_filter=query_filter,
    limit=top_k,
)
```

**Step 4: Run test to verify it passes**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/evaluation/test_search_engines.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/evaluation/search_engines.py tests/unit/evaluation/test_search_engines.py
git commit -m "refactor(eval): migrate Qdrant evaluation calls to SDK query_points"
```

### Task 9: Local Prod-like Runtime Validation (Docker Bot Profile)

> Maps to: #324 Step 9

**Files:**
- Modify: `docs/LOCAL-DEVELOPMENT.md`
- Modify: `docs/PIPELINE_OVERVIEW.md`

**Step 1: Write failing validation checklist test (doc lint or command check)**

```python
# pseudo: verify docs contain supervisor-first bot profile runbook commands
assert "USE_SUPERVISOR=true" in local_dev_doc
```

**Step 2: Run validation to verify missing/old instructions**

Run: `rg -n "USE_SUPERVISOR=true|test-smoke-routing|docker compose --compatibility -f docker-compose.dev.yml --profile bot" docs/LOCAL-DEVELOPMENT.md docs/PIPELINE_OVERVIEW.md`
Expected: FAIL/partial match before update.

**Step 3: Write minimal implementation**

```md
docker compose --compatibility -f docker-compose.dev.yml --profile bot build
USE_SUPERVISOR=true docker compose --compatibility -f docker-compose.dev.yml --profile bot up -d
make test-smoke-routing
```

**Step 4: Run validation to verify it passes**

Run: `rg -n "USE_SUPERVISOR=true|test-smoke-routing" docs/LOCAL-DEVELOPMENT.md docs/PIPELINE_OVERVIEW.md`
Expected: PASS.

**Step 5: Commit**

```bash
git add docs/LOCAL-DEVELOPMENT.md docs/PIPELINE_OVERVIEW.md
git commit -m "docs(runtime): add supervisor-first prod-like local validation runbook"
```

### Task 10: Final Gate and Closeout

> Maps to: #324 Step 10

**Files:**
- Modify: `docs/plans/2026-02-17-chat-history-summary-crm-impl.md`
- Modify: `docs/plans/2026-02-17-unified-chat-history-kommo-rollout.md`

**Step 1: Write closeout checklist in plan docs**

```md
- [ ] make check
- [ ] make test-unit
- [ ] tests/integration/test_graph_paths.py
- [ ] targeted CRM tests
```

**Step 2: Run full validation gate**

Run: `make check`
Expected: PASS.

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
Expected: PASS.

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/integration/test_graph_paths.py -v`
Expected: PASS.

**Step 3: Capture evidence in issue #324**

```bash
gh issue comment 324 --body "Validation gate passed: make check, test-unit, graph paths; CRM tools enabled in supervisor path."
```

**Step 4: Run final docs sanity check**

Run: `rg -n "#324|#312|#310|#313" docs/plans/2026-02-17-chat-history-summary-crm-impl.md docs/plans/2026-02-17-unified-chat-history-kommo-rollout.md`
Expected: PASS.

**Step 5: Commit**

```bash
git add docs/plans/2026-02-17-chat-history-summary-crm-impl.md docs/plans/2026-02-17-unified-chat-history-kommo-rollout.md
git commit -m "chore(plan): finalize rollout checklist and validation evidence workflow"
```

## Global Verification Commands

- `make check`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents -v`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/services -v`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/integration/test_graph_paths.py -v`
