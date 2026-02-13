# Langfuse Trace Coverage + SDK Alignment Plan

Date: 2026-02-13
Scope: `telegram_bot/**`, `src/api/**`, `src/voice/**`, `scripts/**`, `docker-compose*.yml`

## Goal
1) Verify whether trace coverage is complete for critical runtime flows.
2) Verify alignment with official Langfuse SDK integrations.
3) Produce prioritized remediation tasks.

## Current state (fact-based)

### Covered well
- Telegram bot runtime has root traces:
  - `telegram_bot/bot.py:538` (`telegram-rag-query`)
  - `telegram_bot/bot.py:602` (`telegram-rag-voice`)
- LangGraph node layer is fully decorated (including summarize branch):
  - `telegram_bot/graph/nodes/*.py`
  - `telegram_bot/graph/graph.py:138`
- Major services and cache layers are traced with `@observe`:
  - `telegram_bot/services/qdrant.py:147`
  - `telegram_bot/services/colbert_reranker.py:44`
  - `telegram_bot/integrations/cache.py:184`
  - `telegram_bot/integrations/embeddings.py:64`
- OpenAI integration is SDK-native in core graph config:
  - `telegram_bot/graph/config.py:106` (`from langfuse.openai import AsyncOpenAI`)

### Gaps / risks

1. API entrypoint lacks explicit root observation.
   - `src/api/main.py:103` has no `@observe` / `start_as_current_span`; only `propagate_attributes`.
   - Impact: trace hierarchy for API calls may be fragmented vs bot root-trace pattern.

2. Voice agent does not emit Langfuse SDK spans for agent/tool lifecycle.
   - `src/voice/agent.py` uses OTEL setup but no `@observe`/`get_client` trace updates on core call flow.
   - `search_knowledge_base` calls API without explicit `langfuse_trace_id` propagation:
     - `src/voice/agent.py:142`
     - `src/api/main.py:124`

3. E2E Langfuse validator checks obsolete span names (contract drift).
   - `scripts/e2e/langfuse_trace_validator.py:138` expects `telegram-message`, `query-router`.
   - These spans are absent in current runtime graph instrumentation.
   - Impact: `make e2e-test-traces` can report false negatives.

4. VPS stack has no Langfuse wiring.
   - `docker-compose.vps.yml` contains no `LANGFUSE_*` and no langfuse services.
   - Impact: no production trace coverage in VPS mode.

5. Langfuse preflight check is shallow.
   - `telegram_bot/preflight.py:253` only checks `get_langfuse_client() is not None`.
   - Does not verify reachability/auth against Langfuse API.

6. Observability helper code path exists but is runtime-unused.
   - `telegram_bot/integrations/langfuse.py` factory is only referenced in tests, not runtime flow.
   - Increases ambiguity around canonical integration path.

## Official SDK alignment (Context7)

Primary references:
- Langfuse Python SDK (`/langfuse/langfuse-python`)
- Langfuse docs (`/langfuse/langfuse-docs`)

Confirmed official patterns:
1) Use `@observe` for root and nested hierarchy.
2) Use `propagate_attributes(...)` for consistent trace attributes.
3) For cross-service propagation, use baggage (`as_baggage=True`) or explicit trace context passing.
4) Use `langfuse.openai` drop-in (`AsyncOpenAI`) for automatic generation tracing.

## Task plan

### P0
1. Fix E2E validator contract to current span names and branch logic.
   - File: `scripts/e2e/langfuse_trace_validator.py`
2. Add API root tracing (`@observe(name=\"api-rag-query\")` or equivalent explicit root span).
   - File: `src/api/main.py`

### P1
3. Add explicit trace linking from voice agent -> API request (`langfuse_trace_id` propagation).
   - Files:
     - `src/voice/agent.py`
     - `src/api/main.py`
     - `src/api/schemas.py` (already has field, likely no schema change needed)
4. Add trace coverage for voice-agent tool lifecycle (input, latency, fallback outcome).
   - File: `src/voice/agent.py`

### P2
5. Decide production observability policy for VPS stack:
   - enable Langfuse in `docker-compose.vps.yml`, or
   - explicitly document that VPS runs without tracing.
6. Strengthen Langfuse preflight health/auth check.
   - File: `telegram_bot/preflight.py`

## Acceptance criteria

1. E2E trace validation checks only real/current span names.
2. API requests produce one coherent root trace with nested node spans.
3. Voice -> API calls can be correlated by trace id/session context.
4. VPS tracing decision is explicit and documented.
5. Preflight detects broken Langfuse auth/connectivity, not only env presence.
