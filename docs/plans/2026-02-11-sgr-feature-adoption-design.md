# SGR Feature Adoption Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Adopt the highest-value ideas from `vamplabAI/sgr-agent-core` into the current LangGraph RAG stack with minimal regression risk.

**Architecture:** Keep the existing retrieval/generation pipeline intact and add agentic behavior as narrow, testable extensions. Start with an in-graph clarification loop (lowest risk, direct UX gain), then add profile-driven behavior flags, and finally optional MCP tool bridge behind feature flags. Every phase is independently shippable and guarded by tests.

**Tech Stack:** Python 3.12, LangGraph, aiogram, AsyncOpenAI-compatible client, pytest, existing observability (Langfuse + logs).

---

## Scope And Priorities

### In Scope
- Clarification-first branch for ambiguous/underspecified queries.
- Profile/config layer to switch behavior without code edits.
- Optional MCP integration point as a separate graph node path.
- New telemetry fields to quantify impact of clarification and tool usage.

### Out of Scope
- Full migration to `sgr-agent-core` runtime.
- Replacing retrieval/rerank stack (Qdrant/RRF/DBSF/ColBERT).
- Introducing multi-agent orchestration in this iteration.

### Why These Features
- Clarification loop directly reduces low-confidence answers from vague queries.
- Profile-driven behavior mirrors SGR definitions model but fits current architecture.
- MCP bridge provides extensibility while preserving existing graph ownership.

---

### Task 1: Clarification Loop (Phase 1, Must-Have)

**Files:**
- Modify: `telegram_bot/graph/nodes/classify.py`
- Modify: `telegram_bot/graph/edges.py`
- Modify: `telegram_bot/graph/state.py`
- Modify: `telegram_bot/bot.py`
- Test: `tests/unit/graph/test_classify_node.py`
- Test: `tests/unit/graph/test_edges.py`
- Test: `tests/integration/test_graph_paths.py`

**Step 1: Write failing tests (classification + routing + integration)**
```python
# classify: vague queries -> CLARIFICATION
assert classify_query("квартира") == "CLARIFICATION"

# edge: CLARIFICATION -> respond
assert route_by_query_type({"query_type": "CLARIFICATION"}) == "respond"

# integration: graph short-circuits to respond without retrieve/generate
```

**Step 2: Run tests to verify RED**
Run: `uv run pytest -q tests/unit/graph/test_classify_node.py tests/unit/graph/test_edges.py tests/integration/test_graph_paths.py`
Expected: FAIL on missing `CLARIFICATION` behavior.

**Step 3: Minimal implementation**
- Add `CLARIFICATION` query type constant.
- Add deterministic ambiguity heuristics (too short, generic query, no entity/filter intent).
- Produce structured clarification response (2-4 targeted follow-up prompts).
- Route `CLARIFICATION` directly to `respond`.
- Add state field(s): `clarification_requested`, `clarification_prompt`.

**Step 4: Verify GREEN**
Run same test command and ensure all pass.

**Step 5: Commit**
```bash
git add telegram_bot/graph/nodes/classify.py telegram_bot/graph/edges.py telegram_bot/graph/state.py telegram_bot/bot.py tests/unit/graph/test_classify_node.py tests/unit/graph/test_edges.py tests/integration/test_graph_paths.py
git commit -m "feat(graph): add clarification-first path for ambiguous queries"
```

---

### Task 2: Profile-Driven Behavior (Phase 2, High-Value)

**Files:**
- Modify: `telegram_bot/graph/config.py`
- Modify: `telegram_bot/config.py`
- Create: `telegram_bot/graph/profiles.py`
- Modify: `telegram_bot/bot.py`
- Test: `tests/unit/graph/test_config.py`
- Test: `tests/unit/test_bot_handlers.py`

**Step 1: Write failing tests**
- Env/profile selection resolves to expected thresholds and toggles.
- Default profile preserves existing behavior (backward compatibility).

**Step 2: Verify RED**
Run: `uv run pytest -q tests/unit/graph/test_config.py tests/unit/test_bot_handlers.py -k 'profile or config'`
Expected: FAIL due to missing profile layer.

**Step 3: Minimal implementation**
- Introduce `agent_profile` (`baseline`, `clarify_first`, `agentic_light`).
- Add profile overlay logic for rewrite attempts, clarification strictness, optional MCP use.
- Keep env overrides highest-priority.

**Step 4: Verify GREEN**
Run same targeted tests.

**Step 5: Commit**
```bash
git add telegram_bot/graph/config.py telegram_bot/config.py telegram_bot/graph/profiles.py telegram_bot/bot.py tests/unit/graph/test_config.py tests/unit/test_bot_handlers.py
git commit -m "feat(config): add profile-driven graph behavior"
```

---

### Task 3: MCP Bridge Node (Phase 3, Optional Behind Flag)

**Files:**
- Create: `telegram_bot/graph/nodes/mcp_tools.py`
- Modify: `telegram_bot/graph/graph.py`
- Modify: `telegram_bot/graph/state.py`
- Modify: `telegram_bot/graph/config.py`
- Create: `telegram_bot/integrations/mcp_client.py`
- Test: `tests/unit/graph/test_agentic_nodes.py`
- Test: `tests/integration/test_graph_paths.py`

**Step 1: Write failing tests**
- MCP disabled: graph path unchanged.
- MCP enabled + eligible query: MCP node invoked once.
- MCP timeout/error: graceful fallback to existing retrieve/generate path.

**Step 2: Verify RED**
Run: `uv run pytest -q tests/unit/graph/test_agentic_nodes.py tests/integration/test_graph_paths.py -k 'mcp'`
Expected: FAIL (node/integration absent).

**Step 3: Minimal implementation**
- Add feature flag `MCP_TOOLS_ENABLED`.
- Add node that calls MCP client with strict timeout budget.
- Normalize MCP results into state context (no schema leakage to user output).
- Route only for query types that benefit (e.g., `FAQ`, `GENERAL`), skip for structured search-heavy requests.

**Step 4: Verify GREEN**
Run same tests.

**Step 5: Commit**
```bash
git add telegram_bot/graph/nodes/mcp_tools.py telegram_bot/graph/graph.py telegram_bot/graph/state.py telegram_bot/graph/config.py telegram_bot/integrations/mcp_client.py tests/unit/graph/test_agentic_nodes.py tests/integration/test_graph_paths.py
git commit -m "feat(graph): add optional mcp tools bridge node"
```

---

### Task 4: Observability And Rollout Guards (Phase 4, Required)

**Files:**
- Modify: `telegram_bot/bot.py`
- Modify: `tests/unit/test_bot_scores.py`
- Modify: `tests/unit/test_validate_aggregates.py`
- Optional docs: `docs/PIPELINE_OVERVIEW.md`

**Step 1: Write failing tests**
- Add score assertions for clarification-related metrics and MCP invocation metrics.
- Verify no metric regressions in existing paths.

**Step 2: Verify RED**
Run: `uv run pytest -q tests/unit/test_bot_scores.py tests/unit/test_validate_aggregates.py`
Expected: FAIL for missing new metrics.

**Step 3: Minimal implementation**
- Add fields/scores: `clarification_requested`, `clarification_resolved`, `mcp_used`, `mcp_fallback`.
- Ensure all paths emit stable defaults.

**Step 4: Verify GREEN**
Run same tests.

**Step 5: Commit**
```bash
git add telegram_bot/bot.py tests/unit/test_bot_scores.py tests/unit/test_validate_aggregates.py docs/PIPELINE_OVERVIEW.md
git commit -m "feat(observability): add clarification and mcp path metrics"
```

---

## Verification Matrix (Before Merge)

Run in order:
1. `uv run pytest -q tests/unit/graph`
2. `uv run pytest -q tests/integration/test_graph_paths.py`
3. `uv run pytest -q tests/smoke/test_langgraph_smoke.py`
4. `uv run ruff check telegram_bot tests`

Expected:
- All tests green.
- No changes in baseline path latency > agreed threshold unless feature flags enabled.

---

## Risks And Mitigations

- False-positive clarification prompts on valid short queries.
  - Mitigation: conservative heuristics + allowlist entities + telemetry review window.
- MCP latency spike.
  - Mitigation: hard timeout + fallback path + feature flag off by default.
- Config complexity drift.
  - Mitigation: profile overlays with explicit precedence and unit tests.

---

## Definition Of Done

- Clarification branch shipped and covered by unit+integration tests.
- Profile-driven behavior available and backward-compatible by default.
- MCP bridge merged behind flag and resilient fallback verified.
- Observability includes new metrics and is validated in tests.
