# Issue Optimization Recheck Audit

Date: 2026-06-11
Branch: `audit/post-dead-code-issue-recheck-20260611`
Repository: `yastman/rag`
Default branch checked: `dev`
Scope: all open issue audit, issue hygiene, de-duplication, re-scoping, priority corrections, and recommended issue-body/comment updates.
Runtime code changes in this branch: none.

---

## 1. Why this file exists

The issue queue is now useful but too noisy. Several issues are correct, several are overlapping, and a few contain claims that should be rechecked before code changes.

This file answers:

```text
What should be optimized, added, changed, merged, re-scoped, or deprioritized in the issues themselves?
```

This audit intentionally does not modify code. It is meant to guide the next PRs and prevent agents from deleting or refactoring the wrong things.

---

## 2. Main conclusion

The issue backlog should be reorganized around one dependency chain:

```text
Docs truth
  -> generation circular dependency
  -> runtime->telegram coupling
  -> prompt/style ownership
  -> typed dependencies
  -> API/core adapter
  -> LLM/embeddings/retrieval consolidation
  -> dependency diet
  -> dead-code cleanup
```

The queue currently mixes these categories:

```text
architecture ownership
SDK consolidation
dead-code deletion
complexity refactor
dependency cleanup
optional surface archive
observability cleanup
```

Those should not be implemented in the same PRs.

---

## 3. Critical correction: #2492 is too aggressive as written

Issue #2492 was created after the previous dead-code/dedup audit. It claims 12 functions are verified dead. Static recheck suggests several entries are **not safe delete candidates** as written.

### 3.1 Candidates that look incorrectly marked dead

| Candidate in #2492 | Current code observation | Recommendation |
|---|---|---|
| `src/runtime/generation/policy.py::_build_fallback_response` | `src/runtime/generation/service.py` imports and uses `_build_fallback_response` through fallback paths and `extra.get(..., _build_fallback_response)` | Remove from verified-dead list. Not dead. |
| `src/runtime/generation/service.py::_ensure_history_instruction` | Used in the same file as fallback/default for `ensure_history_instruction` before building `system_prompt` | Remove from verified-dead list. Not dead. |
| `src/adapters/embeddings/local_bge_m3.py::LocalBgeM3Provider._encode` | Current file has a nested local function `_encode` inside `embed_texts`, not a class method. It is passed to `asyncio.to_thread(_encode)` | Remove or reword. Candidate name is stale/incorrect. |
| `src/observability.py::_real_observe` | Fallback function assigned to public `observe` when Langfuse import fails | Do not delete without a dedicated optional-observability test. Likely false positive. |
| `src/observability_sentry.py::before_send` | Nested function returned by `_make_before_send()` and passed to Sentry init as `before_send` | Do not delete. Static tool likely missed nested callback return. |
| `DoclingClient.convert_file` | Public method on Docling client. May be unused internally but still part of client API | Reclassify as public API candidate, not verified dead. Remove only in ingestion API reduction PR. |

### 3.2 Candidates that may still be valid but need isolation

| Candidate | Recommendation |
|---|---|
| `trace_search_with_spans` | Tie to #2452 observability optionalization. Do not delete as part of generic dead-code PR. |
| `_detect_filter_sensitive_query`, `_expand_short_query` | Check whether they are exported/assigned or used indirectly in `rag.py` before deletion. They are part of runtime coupling cleanup area, so deleting them should not be mixed with #2478 migration. |
| `GraphConfig.create_hybrid_embeddings` | Likely removable later, but config is already a god-object and should be split under #2482. Do not delete independently if callers may be dynamic. |
| `UnifiedStateManager.mark_processing_sync` | Ingestion-only cleanup candidate. Verify CLI/state-manager tests first. |
| Sentry breadcrumb helpers | Only delete after searching all startup/error boundary call sites and tests. Keep if they are public convenience API. |

### 3.3 Recommended change to #2492

Change #2492 from:

```text
Remove 12 verified dead functions
```

to:

```text
Verify and remove safe dead-code candidates after false-positive pruning
```

Suggested updated scope:

```text
- Remove only candidates with line-level confirmation and no callback/public API role.
- Split into module groups.
- Do not delete runtime generation fallback/history helpers.
- Do not delete nested callbacks returned to SDKs.
- Do not delete public client methods unless the API is intentionally reduced.
```

Suggested labels:

```text
needs-recheck
refactoring
simplification
P2
```

---

## 4. Relationship between #2488 and #2492

#2488 is the broad dead-code verification queue.

#2492 is a narrower removal ticket based on later MCP verification.

But #2492 currently contradicts code evidence for several functions. So the issue relationship should be:

```text
#2488 = umbrella / audit queue
#2492 = narrow deletion PR candidate, only after false positives are removed
```

Recommended update:

```text
#2492 should reference #2488 as parent.
#2488 should link #2492 as a child/slice.
#2492 should not claim all 12 are safe until false positives are removed.
```

---

## 5. Issue-by-issue optimization table

| Issue | Current status | What to change in issue | Priority |
|---:|---|---|---|
| #2411 | Epic is valid | Add links to the newer audit docs and issue dependency chain. Mark #2479/#2486/#2478/#2489 as first sequence. | P0 |
| #2479 | Valid docs-only blocker | Keep as P0. Add explicit “blocks agent/code work until resolved.” | P0 |
| #2486 | Valid and confirmed | Keep P0. Add note that it must land before #2487 complexity refactor and before most #2492 runtime deletion. | P0 |
| #2478 | Valid architecture blocker | Keep P0. Add dependency chain: #2486 first, then #2489, then rag.py, then graph builder. | P0 |
| #2489 | Valid and confirmed | Keep P0/P1. Add dependency on #2486 and parent #2478. | P0/P1 |
| #2480 | Valid | Keep P1. Add explicit `crm` optional field and Protocol list to acceptance criteria. | P1 |
| #2483 | Valid | Keep P1. Add dependency on #2480 or AssistantApp builder if API should not construct deps itself. | P1 |
| #2481 | Valid split-brain issue | Link to #2454/#2429. Make `src/runtime/llm/router.py` canonical in issue body. | P1 |
| #2454 | Partially stale | Re-scope from “migrate to SDK” to “verify SDK migration completed + clean stale proxy docs/env/k8s.” | P1 |
| #2429 | Valid but broad | Make it dependent on #2481 and #2454. Do not remove SDKs before canonical path is chosen. | P1/P2 |
| #2477 | Valid | Add migration nuance: during transition Telegram may import shims, final target forbids src->telegram. | P1 |
| #2485 | Valid | Keep as optional infra. Add dependency on #2479 docs truth and maybe #2484 dependency split. | P1/P2 |
| #2484 | Valid | Add dependency on #2478/#2489 because dependency diet is hard while runtime imports Telegram-owned modules. | P2 |
| #2476 | Valid | Add “QdrantService is canonical runtime gateway; search_engines benchmark/strategy only” to issue body. | P2 |
| #2475 | Valid | Add “BGEM3Client low-level client, adapters provider layer, runtime embeddings shim/wrapper” boundary. | P2 |
| #2482 | Valid | Defer until #2480 and #2483. Split config after dependencies are typed. | P2 |
| #2487 | Valid but sequencing-sensitive | Add blocker: do after #2486/#2489 to avoid refactoring moving target code twice. | P2/P3 |
| #2488 | Valid as umbrella | Update candidate list. Mark false positives and stale candidates. Link #2492 as child after cleanup. | P2 |
| #2492 | Needs recheck | Re-scope; remove false positives from verified-dead list. Do not delete runtime generation fallback/history helpers. | P2 |
| #2490 | Needs repro | Add exact line/path evidence or re-scope as indirect dependency. Direct code search did not confirm. | P3/needs-repro |
| #2491 | Needs repro | Add exact production->tests import evidence or re-scope as reverse dependency noise. | P3/needs-repro |
| #2452 | Needs re-scope | Change from “after removal” to “optionalization cleanup + stale observability assets.” | P2 |
| #2431 | Valid | Keep as dependency diet subtask. Depend on #2484 / runtime cleanup. | P2 |
| #2430 | Product decision | Re-scope to optionalize first, archive later. Do not delete Mini App functions first. | P3 |
| #2426 | Valid later | Keep after core/voice adapter decision. Do not block core text path. | P3 |
| #2427 | Valid later | Keep after #2405/#2483/voice status. | P3 |
| #2428 | Valid last | Dependency removal only after call sites are gone. | P3 |
| #2404 | Valid | Depend on #2480. Builder should consume typed dependencies. | P2 |
| #2405 | Valid | Link ADR-0019. Should follow #2486/#2478. | P2 |
| #2451 | Likely valid cleanup | Search shows `boto3` mainly docs/tests. Verify lock/transitive source before deletion. | P2 |
| #2319 | Valid guardrail issue | Add contract-test CI lane after docs/core contracts stabilize. | P2 |
| #2300 | Valid but independent | Keep out of core migration sprint. | P3 |
| #11 | Renovate dashboard | Background only | Background |

---

## 6. Optimized issue dependency graph

Recommended order:

```text
#2479
  -> #2486
    -> #2489
      -> #2478
        -> #2480
          -> #2483
            -> #2481/#2454/#2429
              -> #2477
                -> #2476/#2475
                  -> #2484/#2431
                    -> #2488/#2492
```

Secondary/later:

```text
#2487 after #2486/#2489
#2482 after #2480/#2483
#2426/#2427/#2428 after core + optional surfaces
#2430 after Mini App decision
#2452 after observability optionalization scope is clear
```

Needs repro before work:

```text
#2490
#2491
```

---

## 7. Suggested issue comments / body updates

### 7.1 #2492 comment

```markdown
Fresh recheck: this ticket should not be treated as a ready-to-delete list yet. Several entries look like false positives or unsafe deletes:

- `_build_fallback_response` is imported/used by `src/runtime/generation/service.py` fallback paths.
- `_ensure_history_instruction` is used in `generate_answer()` before constructing the system prompt.
- `LocalBgeM3Provider._encode` appears stale/incorrect: current code has a nested `_encode` local function passed to `asyncio.to_thread`, not a class method.
- `_real_observe` is the fallback no-op observe implementation assigned to public `observe` when Langfuse import fails.
- Sentry `before_send` is a nested SDK callback returned by `_make_before_send()` and passed to `sentry_sdk.init`.
- `DoclingClient.convert_file` is a public client method; remove only if intentionally reducing the client API.

Recommendation: re-scope this issue to false-positive pruning first, then delete only line-confirmed candidates in small module-specific PRs.
```

### 7.2 #2488 comment

```markdown
Fresh recheck: keep this as the umbrella dead-code verification issue, but do not use it as a delete list. Link #2492 as a child/slice after #2492 removes false positives. React lifecycle methods, dataclass `__post_init__`, callback functions passed inside scripts, and public client methods should not be treated as dead based only on static zero-caller analysis.
```

### 7.3 #2476 comment

```markdown
Issue body update suggestion: make `src/runtime/services/qdrant.py` the canonical runtime SDK gateway. `src/retrieval/search_engines.py` should be explicitly benchmark/eval/strategy-only, or moved under runtime/retrieval as pure strategy wrappers. Avoid maintaining two production hybrid-search implementations.
```

### 7.4 #2475 comment

```markdown
Issue body update suggestion: keep `src/services/bge_m3_client.py` as the low-level HTTP client; make `src/adapters/embeddings` the provider abstraction; treat `src/runtime/integrations/embeddings.py` as a compatibility/runtime wrapper until callers migrate.
```

### 7.5 #2454 comment/body update

```markdown
Re-scope suggestion: Python SDK Router already exists in `src/runtime/llm/router.py`; code search did not show active `AsyncOpenAI(base_url="http://litellm:4000")` usage. Remaining scope should be stale Docker/env/k8s/docs cleanup and consolidation with #2481/#2429.
```

---

## 8. Suggested labels / metadata changes

### Add `P0` or equivalent

```text
#2479
#2486
#2478
#2489
```

### Add `needs-repro`

```text
#2490
#2491
```

### Add `needs-rescope`

```text
#2492
#2452
#2454
#2488
```

### Add `umbrella`

```text
#2411
#2488
```

### Add `blocked-by-core`

```text
#2487
#2482
#2484
#2431
#2426
#2427
#2428
#2430
```

---

## 9. What to optimize in the issue queue

### 9.1 Reduce duplicate planning docs

Several issues reference old docs and newer audits. The repo now has multiple audit files:

```text
docs/audits/2026-06-10-project-issue-audit.md
docs/audits/2026-06-10-custom-vs-sdk-audit.md
docs/audits/2026-06-11-fresh-issue-code-audit.md
docs/audits/2026-06-11-dead-code-dedup-reuse-audit.md
```

Recommendation:

```text
Use this file as the latest issue-queue optimization reference.
Older files remain historical context.
```

### 9.2 Add “write scope” to every implementation issue

Each issue should have:

```text
Allowed files:
Forbidden files:
Acceptance criteria:
Validation:
Dependencies/blockers:
Rollback/shim policy:
```

### 9.3 Split “delete” issues from “verify” issues

Do not create “remove X” issues until verification has no false positives.

Better pattern:

```text
Audit / verify candidate list
  -> Confirm safe candidates
  -> Create narrow deletion issue
  -> Delete by module group
```

### 9.4 Avoid MCP/static graph claims without line-level evidence

For issues based on MCP/codeindexer output, add:

```text
Exact file
Exact line or symbol
Whether edge is forward, reverse, dynamic, callback, nested function, public API, or generated/test-only
```

This prevents false positives like nested callbacks and dataclass lifecycle methods.

---

## 10. Final recommendation

The next best action is not to delete dead code. The next best action is to fix the issue queue so agents do not execute unsafe tasks.

Recommended immediate sequence:

```text
1. Comment/update #2492 to remove false positives.
2. Comment/update #2488 to become umbrella verification only.
3. Fix #2479 docs contradiction.
4. Fix #2486 circular generation dependency.
5. Continue #2478 allowlist shrink.
```

The safest measurable success condition remains:

```text
known_runtime_telegram_bot_couplings.json == {}
```

Only after that should dependency diet and broad dead-code deletion become high-confidence work.
