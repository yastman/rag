# Codebase Concerns

**Analysis Date:** 2026-02-19

## Tech Debt

**APScheduler v3 → v4 migration pending (#390):**
- Issue: APScheduler v3 is deprecated; v4 is in alpha (4.0.0a6)
- Files: `telegram_bot/services/nurturing_scheduler.py` (lines 8-11 TODO comment)
- Impact: Future stability risk; v3 will lose support; v4 API incompatible (AsyncScheduler, AnyIO, add_schedule changes)
- Fix approach:
  1. Wait for v4 stable release or evaluate timing
  2. Update scheduler instantiation to use `AsyncScheduler` (AnyIO-based)
  3. Replace `add_job("interval", minutes=X)` with `add_schedule(IntervalTrigger(minutes=X))`
  4. Replace `CronTrigger.from_crontab()` call (no changes needed)
  5. Update `CoalescePolicy` enum usage
  6. Test funnel rollup and nurturing batch scheduling
- Cost: Medium (isolated module, test coverage exists)

**MLflow integration stubs (#181, #212 in src/evaluation/mlflow_experiments.py):**
- Issue: `_run_variant()` calls `_simulate_evaluation()` which returns hardcoded metrics, not actual RAG pipeline results
- Files: `src/evaluation/mlflow_experiments.py` (lines 181-182, 212)
- Impact: MLflow experiment results are synthetic, not comparable to real pipeline; A/B tests are invalid
- Fix approach:
  1. Replace `_simulate_evaluation()` with real pipeline invocation
  2. Integrate with `RAGExperimentRunner` to call `build_graph().ainvoke()` for each test query
  3. Compute actual recall@1, ndcg@10, latency_p95 from retrieved documents
  4. Log real metrics to MLflow
- Cost: High (requires integration with LangGraph pipeline, ~2-3 days)

**Database pool configuration missing timeout (#3 in lead_scoring_store.py comment):**
- Issue: Comment warns "Pool callers should configure command_timeout=30" but no enforcement exists
- Files: `telegram_bot/services/lead_scoring_store.py` (line 3)
- Impact: Runaway queries can hang the entire lead scoring pipeline; no protection against slow Postgres
- Fix approach:
  1. Audit all `pool.execute()` calls in lead scoring, nurturing, funnel modules
  2. Wrap pool setup in bot.py with explicit `command_timeout=30` in asyncpg pool config
  3. Add unit tests verifying timeout is enforced
  4. Consider circuit breaker for repeated timeouts
- Cost: Low (config change + tests)

**Response style detection disabled by default (#129 in generate_node):**
- Issue: `response_style_enabled` defaults to False; feature was added but not rolled out
- Files: `telegram_bot/graph/nodes/generate.py` (lines 293-312, shadow mode check)
- Impact: Response length control (C+ scoring) is available but inactive; token budgeting not enforced
- Fix approach:
  1. Add `RESPONSE_STYLE_ENABLED=true` to GraphConfig.from_env()
  2. Gradually increase rollout via shadow mode + metrics validation
  3. Monitor p95 token usage and user feedback quality scores
- Cost: Low (flag flip + monitoring)

## Known Bugs

**Security: Text path bypasses guard node (#439) — CRITICAL**
- Issue: Guard node only runs in voice path (via route_start) for transcribed text; direct text messages skip guard entirely
- Files: `telegram_bot/bot.py` (_handle_query_supervisor, no guard for text queries), `telegram_bot/graph/edges.py` (route_start only applies to voice), `telegram_bot/graph/nodes/guard.py` (guard_node logic exists but unreachable)
- Symptoms: Malicious prompts, injection attacks, toxicity bypass supervisor agent without detection
- Trigger: User sends text message with injection/prompt attack → skips guard → agent executes malicious tool
- Impact: **CRITICAL** — CRM tools can be exploited; user data at risk
- Workaround: None (architectural issue)
- Fix approach:
  1. Add guard check in `_handle_query_supervisor()` BEFORE agent creation
  2. Alternatively: wire guard as first middleware in agent tools (crm_tools, rag_tool)
  3. Add integration tests verifying text + voice both trigger guard
- Cost: High (requires redesign of text/voice flow, security testing)

**Streaming coordination broken (#428):**
- Issue: `response_sent=True` flag set by generate_node is ignored by respond_node; duplicate responses sent
- Files: `telegram_bot/graph/nodes/generate.py` (line 378, sets response_sent), `telegram_bot/graph/nodes/respond.py` (line 126, doesn't check flag)
- Symptoms: User sees response sent twice (once during streaming finalization, once via respond_node)
- Trigger: Any message with `STREAMING_ENABLED=true` (default)
- Impact: High (user-facing; annoying UX; double send costs)
- Workaround: Set `STREAMING_ENABLED=false` to disable streaming
- Fix approach:
  1. In respond_node, check `state.get("response_sent", False)` before sending
  2. Skip respond if True
  3. Add test covering streaming path → double-send prevention
- Cost: Low (single condition add + test)

**Agent semantic cache ineffective (#430):**
- Issue: Agent reformulates queries before calling rag_search tool; semantic cache is computed on reformulated query, not original user input
- Files: `telegram_bot/agents/rag_tool.py` (rag_search tool receives agent-modified query), `telegram_bot/graph/nodes/cache.py` (cache_check uses that query)
- Symptoms: Cache hits are rare; same semantic queries reformulated differently → different embeddings → cache miss
- Trigger: Agent rewrites user query for clarity before rag_search
- Impact: Medium (cache effectiveness degraded; ~30% hit rate instead of 80%)
- Workaround: Lower semantic cache threshold or disable semantic cache
- Fix approach:
  1. Pass original user query to rag_search as separate field (`original_query`)
  2. Use original_query for semantic cache key, not reformulated query
  3. Use reformulated query for dense/sparse search
  4. Update rag_tool.py to extract both from agent state
- Cost: Medium (cache key refactor, agent state changes)

**Online LLM-as-a-Judge removed in #413 migration (#427):**
- Issue: Real-time faithfulness/relevance scoring via LLM judge was removed during agent SDK migration; only offline Langfuse managed evaluators remain
- Files: No online judge code exists; offline-only in `docs/eval/managed-evaluator-templates.json`
- Symptoms: No real-time feedback on answer quality; issues detected only after traces uploaded to Langfuse (~5-10s delay)
- Impact: Medium (delayed feedback; debugging harder; no runtime quality gating)
- Workaround: Rely on managed evaluators (async, 5-10s latency)
- Fix approach:
  1. Restore LLM judge as async optional span in generate_node
  2. Use lightweight judge (gpt-3.5-turbo) for speed
  3. Add judge score to Langfuse span
  4. Optionally: gate response on judge confidence threshold
  5. Tests: add judge score validation tests
- Cost: Medium-High (LLM integration, latency implications)

**CRM tools untested, no error paths (#441):**
- Issue: 5 of 8 CRM tools have no test coverage; error handling paths untested
- Files: `telegram_bot/agents/crm_tools.py` (8 @tool functions), `tests/unit/agents/test_crm_tools.py` (partial coverage)
- Symptoms: Silent failures in production (e.g., Kommo API rate limit → no retry); agent returns vague error to user
- Impact: High (CRM integration unreliable; lead scoring pipeline may fail silently)
- Workaround: None
- Fix approach:
  1. Add unit tests for all 8 tools (success + error paths)
  2. Test Kommo API failures: 429 (rate limit), 401 (expired token), 5xx
  3. Test payload validation (missing fields, invalid IDs)
  4. Add integration tests with mocked Kommo
  5. Add Langfuse score for tool error rates
- Cost: Medium (comprehensive test suite, ~200 LOC)

**Metrics command dead (#436):**
- Issue: `/metrics` command handler calls `PipelineMetrics` but metrics are never instrumented
- Files: `telegram_bot/services/metrics.py` (initialized but empty), `telegram_bot/bot.py` (cmd_metrics handler exists)
- Symptoms: User runs `/metrics`, gets empty/stale output
- Impact: Low (diagnostics only; production not affected)
- Workaround: Use Langfuse dashboard instead
- Fix approach:
  1. Wire PipelineMetrics into LangGraph pipeline spans
  2. Track p50/p95/p99 latency per node
  3. Accumulate metrics in bot context
  4. Return formatted output in cmd_metrics
- Cost: Medium (instrumentation work)

**Tool calls total score never written (#437):**
- Issue: Agent state doesn't preserve tool_calls_total; only returned messages not SupervisorState
- Files: `telegram_bot/agents/agent.py` (agent returns tool response messages, not state dict), `telegram_bot/scoring.py` (no tool_calls_total written)
- Symptoms: Langfuse score `tool_calls_total` is always 0
- Impact: Low (observability only; agent works correctly)
- Workaround: None
- Fix approach:
  1. Extract tool_calls from agent invocation result
  2. Count tool uses (rag_search, history_search, 8 CRM tools)
  3. Write to Langfuse score in bot.py
- Cost: Low (~30 LOC)

**Feedback buttons missing for history_search (#434):**
- Issue: history_search tool returns response to user but doesn't attach feedback keyboard
- Files: `telegram_bot/agents/history_tool.py` (returns text), `telegram_bot/agents/agent.py` (tool return not decorated with feedback), `telegram_bot/bot.py` (feedback handler only for rag_search responses)
- Symptoms: User can't rate history_search quality; metrics missing
- Impact: Medium (incomplete feedback loop for agent tool evaluation)
- Workaround: None
- Fix approach:
  1. In agent response handler, detect history_search responses
  2. Attach feedback keyboard (same as rag_search)
  3. Write feedback scores to Langfuse
- Cost: Low (UI pattern reuse)

## Security Considerations

**PII masking incomplete (#5 in security/pii_redaction.py):**
- Risk: Only basic PII patterns redacted (phone, email); structured data (Lead, Contact models) may contain unredacted PII
- Files: `src/security/pii_redaction.py` (regex-based only), `telegram_bot/observability.py` (applies masking to traces)
- Current mitigation: Langfuse PII masking rules in prod; local dev may leak PII in logs
- Recommendations:
  1. Extend PII redaction to Pydantic model fields (LeadScoreRecord.reason_codes may contain names)
  2. Add Kommo Contact fields to redaction (first_name, last_name, phone)
  3. Audit all logged state dicts for PII
  4. Consider field-level redaction decorators on models
- Cost: Medium (field-level masking, validation tests)

**Kommo OAuth2 token refresh race condition:**
- Risk: Multiple concurrent requests may trigger simultaneous refresh; token_store not atomic
- Files: `telegram_bot/services/kommo_token_store.py` (no lock), `telegram_bot/services/kommo_client.py` (retries on 401)
- Current mitigation: Redis single-threaded; low concurrency in practice
- Recommendations:
  1. Add Redis-backed distributed lock for token refresh
  2. Use Lua script for atomic get+refresh
  3. Test with concurrent kommo_client calls
- Cost: Medium (redis-lock integration, test suite)

**API response parsing not defensive (#98-101 in kommo_client.py):**
- Risk: `response.json()` can fail silently; non-dict responses raise RuntimeError
- Files: `telegram_bot/services/kommo_client.py` (lines 97-101)
- Current mitigation: Exception caught and logged
- Recommendations:
  1. Add try/except around response.json() with detailed logging
  2. Return empty dict on parse failure (fail-soft)
  3. Test malformed Kommo responses
- Cost: Low (error handling improvement)

## Performance Bottlenecks

**Generate node latency dominated by LLM (~97% of total trace):**
- Problem: LLM generation is 2-4s on average; pipeline p95 latency = 5.5s
- Files: `telegram_bot/graph/nodes/generate.py` (streaming adds 300ms edit throttle overhead)
- Cause: Cerebras/Groq API latency + prompt size (1500+ tokens context)
- Improvement path:
  1. Implement token budget per response style (already in code, disabled)
  2. Enable response_style_enabled flag to reduce average context tokens by 30%
  3. Consider prompt caching for repeated system prompts (OpenAI feature)
  4. Evaluate faster LLM providers for fallback chain
  5. Monitor TTFT (time-to-first-token) to optimize streaming UX
- Cost: Low-Medium (enablement + monitoring)

**Cache key computation uses SHA256 hashing:**
- Problem: Every query embeds → hash for cache key; hashing overhead ~1-2ms per query
- Files: `telegram_bot/integrations/cache.py` (line 56, _hash function), `telegram_bot/graph/nodes/cache.py` (cache key construction)
- Cause: Security (prevent cache key enumeration); no perf-critical path
- Improvement path:
  1. Benchmark actual impact (likely <0.5% latency)
  2. If bottleneck detected, use faster hash (xxHash, CRC32)
  3. Cache computed hash in state dict if reused
- Cost: Low (optimization premature without profiling)

**Semantic cache unavailable on embedding cache miss:**
- Problem: If embedding is uncached, semantic cache check is skipped (requires precomputed vector)
- Files: `telegram_bot/graph/nodes/cache.py` (cache_check_node, computes embedding first, then semantic check)
- Cause: Dependency on embedding cache hit
- Improvement path:
  1. Compute embedding once, reuse in both exact + semantic cache paths
  2. Profile if semantic cache hit rate improves
- Cost: Low (state dict refactor)

**Qdrant batch_search_rrf round-trip overhead:**
- Problem: Each hybrid search is 200-300ms; batch operations possible but not used
- Files: `telegram_bot/services/qdrant.py` (batch_search_rrf method exists), `telegram_bot/graph/nodes/retrieve.py` (calls single search per node invocation)
- Cause: LangGraph nodes are single queries; batch search not applicable
- Improvement path:
  1. Future: if multi-query retrieval needed (e.g., HyDE with 3 variants), batch them
  2. Current: single-query is optimal
- Cost: N/A (not a bottleneck)

## Fragile Areas

**LangGraph state management — mutable dict passed around:**
- Files: `telegram_bot/graph/state.py` (RAGState TypedDict), all node implementations
- Why fragile: TypedDict enforces structure at type check time, not runtime; nodes return partial dicts; easy to introduce missing fields
- Safe modification:
  1. Always return complete partial state dict with explicit keys
  2. Test state transitions with `pytest` coverage of all route branches
  3. Use type hints for state dict keys in each node
  4. Add runtime validation in sensitive nodes (e.g., respond_node checks for response_sent)
- Test coverage: Good (test_graph_paths.py covers all 6 route_grade branches)

**Guard node regex patterns — regex injection risk:**
- Files: `telegram_bot/graph/nodes/guard.py` (uses regex patterns from config)
- Why fragile: User input (via GUARD_MODE config) could be malicious regex
- Safe modification:
  1. Validate GUARD_MODE enum (hard/soft/log) — already done
  2. Do NOT accept regex patterns from untrusted sources
  3. Precompile regex patterns in __init__, not at guard invocation
  4. Add tests for ReDoS vulnerability
- Test coverage: Partial (no ReDoS tests)

**Streaming delivery with partial message recovery (#379-414 in generate_node):**
- Files: `telegram_bot/graph/nodes/generate.py` (StreamingPartialDeliveryError handling)
- Why fragile: Streaming fails after partial send; fallback edit_text may also fail; multiple exception handlers
- Safe modification:
  1. Test all failure scenarios: stream timeout, edit_text timeout, delete_message timeout
  2. Add timeout wrapper around entire streaming block
  3. Ensure respond_node gracefully handles response_sent=True (currently broken #428)
  4. Log all recovery attempts for debugging
- Test coverage: Partial (no chaos tests for streaming failures)

**Kommo API response shape assumptions:**
- Files: `telegram_bot/services/kommo_client.py` (lines 111-112, 118, 141-142 assume specific nested structure)
- Why fragile: Kommo API can change response schema; no schema validation
- Safe modification:
  1. Add Pydantic schema validation on all responses
  2. Version kommo_models.py alongside API docs
  3. Add integration tests with Kommo API sandbox
  4. Catch parsing errors and convert to meaningful domain exceptions
- Test coverage: None (no live Kommo tests)

**APScheduler job execution ordering — no implicit ordering:**
- Files: `telegram_bot/services/nurturing_scheduler.py` (runs nurturing_batch and funnel_rollup independently)
- Why fragile: Both jobs may run simultaneously; no coordination on database locks
- Safe modification:
  1. Use distributed lock (scheduler_leases table) for both jobs
  2. Ensure nurturing batch completes before funnel rollup
  3. Add job dependency if needed (APScheduler v3 doesn't support; v4 does)
- Test coverage: None (no concurrent job tests)

## Test Coverage Gaps

**Untested: Streaming failure paths in generate_node:**
- What's not tested: StreamingPartialDeliveryError, stream timeout, edit_text failure, recovery fallback
- Files: `telegram_bot/graph/nodes/generate.py` (lines 363-431)
- Risk: Streaming errors not caught before production; user sees broken UX
- Priority: High (feature-critical)

**Untested: CRM tool error paths (#441):**
- What's not tested: Kommo API 429/5xx, token refresh on 401, payload validation errors
- Files: `telegram_bot/agents/crm_tools.py` (all 8 tools)
- Risk: Silent failures in production; users don't know why leads weren't created
- Priority: High (production reliability)

**Untested: Guard node bypass via text path (#439):**
- What's not tested: Injection/toxicity detection for text messages in supervisor path
- Files: `telegram_bot/bot.py` (_handle_query_supervisor)
- Risk: Security vulnerability; allows unfiltered agent execution
- Priority: Critical (security)

**Untested: Semantic cache effectiveness:**
- What's not tested: Cache hit rates with reformulated queries, threshold sensitivity
- Files: `telegram_bot/integrations/cache.py`, `telegram_bot/graph/nodes/cache.py`
- Risk: Cache misconfiguration leads to degraded performance
- Priority: Medium (optimization validation)

**Untested: Database pool timeout enforcement:**
- What's not tested: Runaway queries trigger timeout correctly
- Files: `telegram_bot/services/lead_scoring_store.py`, all asyncpg operations
- Risk: Hung connections; no protection against slow Postgres
- Priority: High (reliability)

**Untested: Concurrent Kommo token refresh (#sec-kommo-race):**
- What's not tested: Multiple simultaneous kommo_client calls triggering concurrent token refresh
- Files: `telegram_bot/services/kommo_token_store.py`
- Risk: Invalid/stale tokens; race condition in production
- Priority: Medium (concurrency)

## Scaling Limits

**Semantic cache with BGE-M3 local embeddings:**
- Current capacity: ~10k unique queries per 24h (memory-bound in Redis + network I/O)
- Limit: Redis memory grows with cache size; no eviction on overflow
- Scaling path:
  1. Monitor Redis memory (currently <500MB, threshold 1GB)
  2. Implement LRU eviction policy on semantic cache
  3. Consider cache tier splitting (hot queries → memory, cold → disk)
  4. Evaluate Redis cluster if cache > 10GB
- Current bottleneck: None observed; monitor trending

**Qdrant collection size with Kommo lead scoring:**
- Current capacity: 192 properties (Bulgaria) + 1,294 criminal code articles
- Limit: Qdrant scales to 10M+ documents with reranking
- Scaling path:
  1. Add collection sharding if > 100M documents needed
  2. Profile group_by performance on large collections
  3. Current: no scaling concern
- Future risk: If adding image/multimodal docs (1M+ documents), may need optimization

**APScheduler job queue capacity:**
- Current capacity: 2 jobs (nurturing_batch, funnel_rollup)
- Limit: Single AsyncIOScheduler instance can handle 100+ jobs
- Scaling path:
  1. If > 50 scheduled jobs needed, migrate to APScheduler v4 with proper job distribution
  2. Current: no scaling concern
- Future: If background workers expand, consider job queue abstraction (Celery, RQ)

## Dependencies at Risk

**APScheduler v3 end-of-life:**
- Risk: Deprecated; v4 not stable; maintenance burden
- Impact: Future Python 3.13+ may not support v3; security patches may stop
- Migration plan: Wait for v4 stable, then execute upgrade (see Tech Debt section)
- Timeline: Recommend planning for v4 migration by Q3 2026

**Kommo API v4 compatibility:**
- Risk: Kommo may deprecate endpoints; SDK not version-locked
- Impact: Breaking changes to lead_scoring_models.py, kommo_client.py
- Mitigation: Pin kommo API version in kommo_token_store.py initialization; monitor Kommo changelog
- Timeline: Check quarterly; version lock required

**langfuse v3 Managed Evaluators (beta):**
- Risk: Managed evaluators API may change; templates may not be stable
- Impact: Judge quality scoring pipeline may break
- Mitigation: Version templates in `docs/eval/managed-evaluator-templates.json`; test on staging before production
- Timeline: Monitor Langfuse release notes

**OpenAI SDK deprecation for GPT-3.5:**
- Risk: OpenAI may remove gpt-3.5-turbo fallback model
- Impact: rewrite_node uses gpt-4o-mini but fallback queries may use gpt-3.5
- Mitigation: Track OpenAI model lifecycle; update REWRITE_MODEL env var if needed
- Timeline: Plan update every 6 months

## Missing Critical Features

**Guard node disabled in text path — security gap:**
- Problem: Text messages skip toxicity/injection filtering; only voice is protected
- Blocks: Safe text input handling; security audit passing
- Impact: Production vulnerability (see #439)
- Fix: Wire guard_node into _handle_query_supervisor before agent creation (see Security section)

**Real-time LLM-as-a-Judge scoring:**
- Problem: Quality scoring is offline only (Langfuse managed evaluators, 5-10s latency)
- Blocks: Real-time quality gating; immediate user feedback
- Impact: Cannot detect bad answers before user sees them
- Fix: Restore online judge (see Known Bugs section #427)

**Kommo CRM API comprehensive error handling:**
- Problem: Tool errors not handled; silent failures in production
- Blocks: Reliable CRM integration; user feedback on lead creation status
- Impact: Leads may not sync; users unaware
- Fix: Add error handling tests + user feedback on tool execution (see Known Bugs section #441)

---

*Concerns audit: 2026-02-19*
