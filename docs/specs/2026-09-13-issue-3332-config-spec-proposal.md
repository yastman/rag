# Config spec proposal for #3332 — one typed settings model

> **PROPOSAL — AWAITING OWNER DECISION.** This document is a design proposal for the OPEN
> issue [#3332](https://github.com/yastman/rag/issues/3332) (parent
> [#3338](https://github.com/yastman/rag/issues/3338)). Nothing in it is accepted scope until
> the owner approves the decision points in Section 4. It is not a restored archive:
> `docs/specs/` was emptied by `f7cc65514` (#3454, closed-task spec deletion) and this file is
> new work.

- **Owning work item:** [#3332](https://github.com/yastman/rag/issues/3332) — SPEC(config): replace dual nested/flat GraphConfig with one typed settings model. All live GraphConfig changes belong to #3332 (ownership reconciliation in [#3331](https://github.com/yastman/rag/issues/3331) and the #3336 closing clarification).
- **Evidence base:** every claim below was verified in this worktree at commit `0f774b3b6` (= `origin/dev`, 2026-09-12). File/line references are valid at that SHA; re-validate at the implementation SHA before deleting anything.
- **Scope/non-goals, acceptance, stop limits:** Sections 2, 6, 7. The issue's own target contract and non-goals are restated only where this proposal commits to a concrete option.

## 1. Summary

#3332 asks for one typed settings API with one environment-loading path, replacing the nested
sub-config composition plus the generated flat compatibility surface that #2482/#2577 left
behind. Since the issue's 2026-09-05 re-audit at `7a0b10fdd`, predecessor issues removed parts
of the surface (streaming, BotConfig knobs, legacy Settings, Redis modes) — so the residue is
smaller than the issue text describes, and two fields the issue flags are already gone. This
proposal inventories what actually remains at `0f774b3b6`, proposes how to collapse the
dual API, and splits execution into bounded waves with owner decision points.

## 2. Scope and non-goals

**In scope:** `src/runtime/config.py` (GraphConfig and everything only it uses), the
GraphConfig-adjacent slices of `telegram_bot/config.py`, `telegram_bot/lifecycle/services.py`,
`scripts/e2e/config.py`, direct config tests, and the `.env.example` lines whose only owner is
a deleted field.

**Out of goals (mirroring the issue, plus current residue decisions):**

- No new configuration framework; no deprecation shims; no "support both APIs indefinitely".
- No environment-variable renames and no `RUNTIME_*`/`BOT_*` prefix redesign — that is
  [#3437](https://github.com/yastman/rag/issues/3437) (OPEN, "replace the 475 LOC env AST
  allowlist with typed and Compose-native ownership"), including its A12 removed-environment
  addendum on issue #3332.
- No provider/retrieval behavior changes; Redis semantics stay as delivered by #3362 (decision
  [#3354](https://github.com/yastman/rag/issues/3354)).
- No relocation of the `src/config/` content catalog (Section 4, DP8).

## 3. Current-state inventory (evidence at `0f774b3b6`)

### 3.1 What predecessor issues already resolved — no remaining work

| Issue | Delivered | Current residue in config surface |
| --- | --- | --- |
| [#3350](https://github.com/yastman/rag/issues/3350) | `ae87d6f79` removed 39 ignored BotConfig knobs | BotConfig is 307 lines; guard test `tests/unit/config/test_bot_config_removed_knobs_3350.py` pins the removal |
| [#3354](https://github.com/yastman/rag/issues/3354) / [#3362](https://github.com/yastman/rag/issues/3362) | `2256e7224` added `redis_mode` to **both** BotConfig and `RetrievalConfig`, single parse point `parse_redis_mode` | `redis_url`/`redis_mode` are intentionally duplicated in both models (different defaults: core `redis://redis:6379` vs bot `redis://localhost:6379`) |
| [#3365](https://github.com/yastman/rag/issues/3365) | Redis clients moved to an explicit optional extra | None in config files |
| [#3372](https://github.com/yastman/rag/issues/3372) | `7a24451bd` (PR #3534) deleted the legacy Settings/constants stack | `src/config/` retained 3 files: `qdrant_policy.py` (17 lines), `services.yaml` (166 lines), 1-line `__init__.py` (Section 4, DP8) |
| [#3481](https://github.com/yastman/rag/issues/3481) | `89cd986bb` removed the test-only streaming surface | `ResponseConfig.streaming_enabled` and its env alias are **already gone**; the issue's verification command still names `test_graph_config_streaming_flags.py`, which no longer exists (see Section 9) |
| [#3441](https://github.com/yastman/rag/issues/3441) | small-to-big neighbor-budget fix; knobs live | `small_to_big_window_before/after`, `max_expanded_chunks` are live fields read by the retrieval pipeline |
| [#3486](https://github.com/yastman/rag/issues/3486) | Runtime configuration passed into the canonical generation path | `src/runtime/generation/service.py` receives `config`; but pipeline modules still self-load (Section 3.5) |
| [#3331](https://github.com/yastman/rag/issues/3331) | PR #3560 removed no-op observability | Leftover no-op parameter `auto_trace` on `GraphConfig.create_llm` (`src/runtime/config.py:601-603`, body discards it: `_ = auto_trace`) |
| [#3429](https://github.com/yastman/rag/issues/3429) | PR #3525 deleted the HyDE island | Ownership note preserved at `src/runtime/services/query_preprocessor.py:10`; the settings-ownership statement "Pydantic Settings remains the single settings owner" lives in the design-target doc `docs/architecture/RAG_VPS_V2_PROPOSED.md` — this proposal treats pydantic-settings as the retained loading mechanism (DP2) |
| [#3336](https://github.com/yastman/rag/issues/3336) | Closed; zero-call residue deleted | Its "zero-call GraphConfig methods" candidates were ceded to #3332 — handled here as DP6 |

### 3.2 The dual nested/flat GraphConfig as it exists now

`src/runtime/config.py` is 651 lines and contains four parallel representations of the same
field set:

1. **Seven Pydantic sub-config classes** (issue confirmed): `LlmConfig`, `RetrievalConfig`,
   `CacheConfig`, `DomainConfig`, `ResponseConfig`, `VoiceConfig`, `SecurityConfig`
   (`src/runtime/config.py:37-160`).
2. **`_GraphEnvSettings`** (`src/runtime/config.py:167-346`): a flat pydantic-settings loader
   with 39 fields, each declaring `AliasChoices(field, UPPER_FIELD)` — except `domain` →
   `BOT_DOMAIN`, `domain_language` → `BOT_LANGUAGE`, `llm_api_key` → `+ OPENAI_API_KEY`.
   `CacheConfig` has **no** env path (thresholds/TTLs are not env-loadable today).
3. **`_FLAT_KWARGS`** (`src/runtime/config.py:354-404`): 42-entry legacy-kwarg →
   `(sub_attr, sub_field)` map, plus `_make_flat_property` (lines 407-416) and the
   `setattr` loop (lines 636-637) that injects 42 runtime-generated getter/setter properties.
4. **`TYPE_CHECKING` stubs** (`src/runtime/config.py:446-497`): 43 hand-maintained flat
   attribute declarations so MyPy sees the injected properties.

The nested model is not even a clean domain boundary: `RetrievalConfig` owns `redis_url` /
`redis_mode` (cache/transport concern), exactly as the issue states.

### 3.3 Field liveness — who actually reads what

Production readers of a `GraphConfig` instance (`src/runtime/pipeline/rag.py`,
`_grade_rerank.py`, `_rewrite_cache.py`, `src/runtime/services/rag_core.py`,
`src/runtime/generation/service.py`, `telegram_bot/lifecycle/services.py`):

- **Every static read is flat** (`config.llm_model`, `config.rewrite_model`,
  `config.rerank_top_k`, `config.skip_rerank_threshold`, `graph_config.bge_m3_timeout`, …).
  A receiver-qualified grep over the production runtime files finds **zero** nested reads
  (`config.retrieval.X`, `config.llm.X`, …). The flat surface *is* the production API; the
  nested classes are plumbing under it.
- **Several fields are read only via dynamic `getattr` with defaults** — a static-only audit
  would misclassify them as dead:
  - `guard_mode` — `src/runtime/pipeline/assistant_pipeline.py:113`
  - `response_style_enabled` / `response_style_shadow_mode` — `src/runtime/generation/prompts.py:148,197-198`
  - `show_transcription`, `stt_model`, `voice_language` — read from **BotConfig** (not GraphConfig) at
    `telegram_bot/dialogs/catalog/dialog.py:72`, `telegram_bot/dialogs/demo.py:141`,
    `telegram_bot/services/voice_transcription.py:64-65`
- **Zero-production-reader fields at this SHA** (each exists in the model, env map, `_FLAT_KWARGS`
  and stubs; some are documented in `.env.example`):
  - `llm_base_url` — deprecated in both models; the LiteLLM router
    (`src/runtime/llm/router.py`) has no `base_url`/`api_base` usage at all; `.env.example:174`
    already labels it "Legacy proxy compatibility only; unused by the SDK router". Thread:
    `scripts/e2e/config.py` → BotConfig → `build_services` (`telegram_bot/lifecycle/services.py:64`) → `LlmConfig` → read by nobody.
  - `llm_max_tokens` — only `src/runtime/config.py` + its env roundtrip test.
  - `ttft_drift_warn_ms` — only `src/runtime/config.py` + env test; but `.env.example:218`
    still ships `TTFT_DRIFT_WARN_MS=500` as if active (the #675 drift-warning consumer no longer exists).
  - `CacheConfig.cache_thresholds` / `cache_ttl` — constructed, never wired:
    `CacheLayerManager` owns identical defaults (`src/runtime/integrations/cache.py:196-225`)
    and no caller passes GraphConfig's dicts into it.
  - GraphConfig's `VoiceConfig` block (`show_transcription`, `voice_language`, `stt_model`) —
    no `src/` reader; the bot reads the same env names via BotConfig.
- **Live via method, not attribute:** reasoning knobs (`reasoning_effort`, `reasoning_format`,
  `disable_reasoning`) are consumed through `get_reasoning_kwargs()`
  (`src/runtime/generation/service.py:169`) — currently duplicated as `LlmConfig.get_reasoning_kwargs`
  (lines 56-70) plus a delegating `GraphConfig.get_reasoning_kwargs` (lines 529-537).

### 3.4 Remaining config surfaces

- **`BotConfig`** (`telegram_bot/config.py`, 307 lines): transport/session concerns (token,
  admin/manager IDs, handoff, business hours, quotas) plus 17 fields duplicated from
  GraphConfig (`bge_m3_url`, `redis_password`, `redis_url`, `redis_mode`, `qdrant_url`,
  `qdrant_api_key`, `qdrant_collection`, `llm_api_key`, `llm_base_url`, `llm_model`,
  `search_top_k`, `rerank_provider`, `domain`, `domain_language`, `show_transcription`,
  `voice_language`, `stt_model`, `guard_mode`, `content_filter_enabled`).
  `build_services` passes 11 of them into GraphConfig by explicit flat kwargs
  (`telegram_bot/lifecycle/services.py:63-75`) — the post-#3486 handoff.
- **`GraphConfig`** (651 lines, Section 3.2): the runtime/core settings owner, constructed two
  ways — `GraphConfig.from_env()` (4 call sites: `rag.py:67`, `_grade_rerank.py:26`,
  `_rewrite_cache.py:27`, `rag_core.py:88`) and direct construction with flat kwargs
  (bot lifecycle + tests).
- **`src/core/contracts.py`**: `CoreDependencies.config: object | None = None` (line 132) —
  the core boundary deliberately keeps the config seam untyped; a flattened GraphConfig slots
  behind it without contract changes. The only constants are request-language codes (#3491),
  not knobs.
- **`src/config/`** (post-#3372): `qdrant_policy.py` (live — imported by
  `telegram_bot/config.py:19` for `resolve_collection_name`), `services.yaml` (bot content
  catalog: services/promotions/welcome copy — not runtime knobs), 1-line `__init__.py`.

### 3.5 Leftovers that interact with this spec

1. **`auto_trace` no-op parameter** (#3331 leftover) on `GraphConfig.create_llm`
   (`src/runtime/config.py:601`); callers still pass it
   (`src/runtime/generation/service.py:162`, `tests/unit/e2e_core/test_live_harness.py:167,188`,
   `tests/e2e_core/live_harness.py`).
2. **Per-call config self-loading**: `rag.py`, `_grade_rerank.py`, `_rewrite_cache.py` and
   `rag_core.py:88` each call `GraphConfig.from_env()` at request time, so the one GraphConfig
   the bot lifecycle built is not the one the pipeline reads (relevant to the issue's
   acceptance item "Lifecycle constructs services from one config object").
3. **`.env.example` drift**: `LLM_BASE_URL` legacy line (174) and active-looking
   `TTFT_DRIFT_WARN_MS` (218) own no live code; the env-completeness contract
   (`tests/contract/test_env_example_completeness_contract.py`, referenced at
   `.env.example:9-11`) constrains how these lines may be removed.
4. **Issue verification drift**: the #3332 verification command names
   `tests/unit/runtime/test_graph_config_streaming_flags.py`, deleted with the #3481 surface.
   The live equivalents are `tests/characterization/test_nonstreaming_generation_surface.py`
   and `tests/unit/runtime/test_redis_mode.py`.
5. **Test-time patches of a method with no production caller**:
   `tests/unit/test_bot_initialization.py:24,48` patch `GraphConfig.create_supervisor_llm`;
   a repo-wide grep finds no production caller (the bot calls `create_llm` directly,
   `telegram_bot/lifecycle/services.py:107`).
6. **Zero-call factories**: `create_embeddings` and `create_sparse_embeddings`
   (`src/runtime/config.py:615-631`) have zero callers repo-wide; production lifecycle
   constructs BGE adapters directly (`BGEM3HybridEmbeddings`/`BGEM3SparseEmbeddings`,
   `telegram_bot/lifecycle/services.py:79-86`).

## 4. Decision points for the owner

Each decision lists options, a recommendation, and the evidence it rests on.

### DP1 — Target model shape (flatten vs nested-only cleanup)

- **Option A (recommended): one flat typed model.** `GraphConfig` becomes a single
  pydantic-settings class owning only live runtime fields (env aliases declared once, in
  place); the seven sub-config classes, `_FLAT_KWARGS`, `_make_flat_property`, the property
  injection loop and the `TYPE_CHECKING` stubs are deleted; `_GraphEnvSettings` merges into
  the model; `from_env()` stays as a thin entry point; direct kwarg construction stays stable.
- **Option B: keep nesting, delete only the flat machinery.** Rejected on evidence:
  production reads are 100% flat (Section 3.3), so Option B rewrites every caller onto a
  nested API nobody uses, to preserve modularity the issue itself calls accidental
  (`RetrievalConfig` owning `redis_url`).
- Evidence: Sections 3.2-3.3; issue target contract "one typed settings/config model owns only
  live runtime fields".

### DP2 — Env-name/alias policy after #3362/#3481

- **Option A (recommended): byte-for-byte freeze.** All current env names, aliases
  (`BOT_DOMAIN`, `BOT_LANGUAGE`, `OPENAI_API_KEY` fallback) and defaults survive the flatten
  unchanged; a rewritten `test_graph_config_from_env.py` pins the complete name/default table
  as a contract.
- **Option B: redesign names/prefixes now.** Rejected: the issue bans renames without
  migration evidence, and [#3437](https://github.com/yastman/rag/issues/3437) owns the env
  file / Compose-native ownership redesign; doing both at once would make the cutover
  unreviewable.
- Evidence: `_GraphEnvSettings` alias table (Section 3.2.2); `.env.example` documents the
  same names; the env roundtrip test (`tests/unit/runtime/test_graph_config_from_env.py`)
  is the existing safety net to be strengthened, not weakened.

### DP3 — `llm_base_url` disposition

- **Option A (recommended): delete everywhere** — `LlmConfig` field + `_FLAT_KWARGS` entry +
  stub, `BotConfig.llm_base_url`, the `build_services` pass-through, `scripts/e2e/config.py`
  field, the `.env.example:174` line, and the test fixtures that set it.
- **Option B: keep until an external consumer is proven.** The issue allows retention only if
  a named current external consumer is proven; none is known at `0f774b3b6` (router never
  reads a base URL).
- Evidence: Section 3.3 (`llm_base_url`), `src/runtime/llm/router.py` grep (no `base_url`).

### DP4 — Zero-production-reader fields and the never-wired CacheConfig

- **Option A (recommended): delete in Wave 1** — `llm_max_tokens`, `ttft_drift_warn_ms`,
  the whole `CacheConfig` (thresholds/TTLs stay owned by `CacheLayerManager` defaults), and
  GraphConfig's `VoiceConfig` block (bot keeps reading the same env names via BotConfig).
  Keep `SecurityConfig` content: `guard_mode` is live via `assistant_pipeline.py:113`.
  Coordinate the two `.env.example` line removals with #3437's A12 addendum mechanics
  (delete only variables whose owner disappears).
- **Option B: keep them as documented operator contracts.** Rejected for these five: a
  documented variable with no reader is residue, not a contract; the issue's acceptance
  requires a live caller or a *real* operator contract.
- Evidence: Section 3.3 zero-reader list, including the dynamic-`getattr` sweep that clears
  `guard_mode` / `response_style_*` / `show_transcription`-via-BotConfig.

### DP5 — BotConfig ↔ GraphConfig boundary

- **Option A (recommended): keep two per-context typed models.** BotConfig keeps
  transport/session/validation concerns (token shape, handoff invariants, Redis-mode
  validation); GraphConfig keeps runtime/core knobs; the boundary stays the explicit
  field-by-field pass in `build_services` (post-#3486). Remove only the proven-dead
  duplicates (DP4 voice block, DP3 `llm_base_url`).
- **Option B: one merged settings object.** Rejected: it would drag Telegram validation and
  secrets into the core import graph and re-create the layering #1948/#2045/#2049 removed.
- Evidence: `telegram_bot/config.py` validators (`validate_telegram_token_format`,
  `validate_handoff_contract`, Redis-mode invariants) are transport-specific;
  `src/core/contracts.py` keeps the core seam transport-free.

### DP6 — Zero-call methods and the `auto_trace` leftover

- **Option A (recommended): delete `create_embeddings`, `create_sparse_embeddings`,
  `create_supervisor_llm`, and the `auto_trace` parameter** in the same atomic packet that
  updates the patching tests (`tests/unit/test_bot_initialization.py`) and the
  `auto_trace=False` call sites (`src/runtime/generation/service.py:162`, live-harness tests).
  `create_llm` and `get_reasoning_kwargs` stay (live callers). #3336's closing clarification
  assigns all live GraphConfig changes to #3332, so no coordination gap remains.
- **Option B: retain as API surface.** Rejected: the issue requires factory methods to have
  live production callers.
- Evidence: Sections 3.5(5)(6).

### DP7 — "Lifecycle constructs services from one config object"

- **Option A (recommended, owner-gated Wave 3): inject one GraphConfig** from the entrypoints
  (bot lifecycle / core harness) into the pipeline modules, deleting the four per-call
  `GraphConfig.from_env()` sites; `from_env()` remains only at process entry.
- **Option B: accept per-call `from_env()` permanently.** Cheaper, but leaves the bot-built
  config and the pipeline-read config as different objects (the divergence #3486 partially
  fixed), and leaves the acceptance item unsatisfied.
- Risk to approve: behavior parity — today a per-call reload picks up env changes mid-process;
  injection freezes config at construction. Tests that rely on reload (the env roundtrip test
  calls `importlib.reload`) must be updated, not weakened.

### DP8 — Retention policy for `src/config/` residue

- **Option A (recommended): retain as-is.** `qdrant_policy.py` is live
  (`telegram_bot/config.py:19`); `services.yaml` is bot content copy, not runtime config —
  harmless where it is, and moving it is churn outside #3332's outcome. The 1-line
  `__init__.py` docstring already states the two owners.
- **Option B: relocate `services.yaml` to `telegram_bot/` resources now.** Possible follow-up
  issue; not required by #3332's acceptance and not recommended inside this change.
- Evidence: Section 3.4; #3372 deliberately retained these files.

## 5. Proposed execution plan

One branch per wave, each wave independently revertable, `origin/dev` refreshed before each
start. LOC estimates are against the `0f774b3b6` baseline and must be replaced by measured
numbers in the delivery PR (issue acceptance: before/after inventory and LOC delta attached).

| Wave | Content | Files | Est. LOC (repo net) | Depends on |
| --- | --- | --- | --- | --- |
| 0 | Re-run the field×caller inventory at the implementation SHA; attach the table to the issue/PR | docs/evidence in PR description only | 0 | approval of DPs |
| 1 | Dead-surface deletions with env contract intact (DP3, DP4, DP6): `llm_base_url`, `llm_max_tokens`, `ttft_drift_warn_ms`, `CacheConfig`, GraphConfig `VoiceConfig`, 3 factory methods, `auto_trace` param; update `build_services`, `scripts/e2e/config.py`, patching tests, `.env.example` (2 lines) | `src/runtime/config.py`, `telegram_bot/config.py`, `telegram_bot/lifecycle/services.py`, `scripts/e2e/config.py`, `.env.example`, `tests/unit/test_bot_initialization.py`, `tests/unit/e2e_core/test_live_harness.py`, `tests/e2e_core/live_harness.py`, `src/runtime/generation/service.py`, `tests/unit/config/*`, `tests/unit/runtime/test_graph_config_from_env.py`, smoke/integration fixtures referencing `llm_base_url` | −120 to −180 | DP3/4/6 approved |
| 2 | The flatten (DP1+DP2): single typed model with per-field aliases; delete 7 sub-configs, `_FLAT_KWARGS`, `_make_flat_property`, injection loop, `TYPE_CHECKING` stubs, `_GraphEnvSettings` (merged); keep `from_env()` + direct construction stable; rewrite the env roundtrip test into a full name/default contract table | `src/runtime/config.py`, `tests/unit/runtime/test_graph_config_from_env.py`, characterization fakes implementing nested attrs (`tests/characterization/test_grounded_qa_acceptance.py:130`, `test_nonstreaming_generation_surface.py:50,71`) | −300 to −420 | Wave 1 merged |
| 3 | Single config object through lifecycle (DP7): thread one GraphConfig from entrypoints; delete 4 per-call `from_env()` sites | `src/runtime/pipeline/rag.py`, `_grade_rerank.py`, `_rewrite_cache.py`, `src/runtime/services/rag_core.py`, `telegram_bot/lifecycle/services.py`, entrypoint tests | ±40 | Wave 2 merged; owner sign-off on reload-parity risk |

Cumulative estimate: roughly **−380 to −560 lines net**, taking `src/runtime/config.py` from
651 lines to roughly 230-280. Every wave keeps `make type`, import-linter, and the focused
config tests green; the delivery gate is `make candidate-check`.

## 6. Acceptance criteria

Mapped from the issue, with the evidence that will satisfy each:

- [ ] No runtime-generated config properties or `**flat_kwargs` compatibility map remain — `_FLAT_KWARGS`, `_make_flat_property`, injection loop, `TYPE_CHECKING` stubs deleted (Wave 2).
- [ ] Every retained field has a live caller or documented operator contract — Wave 0 inventory table, including the dynamic `getattr` readers (Section 3.3).
- [ ] No deprecated `llm_base_url` remains (DP3; no external consumer found at `0f774b3b6`).
- [ ] `streaming_enabled` — **already satisfied**: the field and its env alias were removed by #3481 (`89cd986bb`); nothing to retain.
- [ ] Current environment/default tests pass — rewritten name/default contract table (DP2).
- [ ] Lifecycle constructs services from one config object — Wave 3 (DP7) or an explicit owner waiver.
- [ ] MyPy and import-linter remain green — per wave.
- [ ] Before/after field inventory and LOC delta attached — Wave 0 + delivery PR.

## 7. Stop limits

- Any deletion candidate shows a live production/dynamic/external consumer at the
  implementation SHA: keep it, record it in the inventory, continue with the rest of the wave.
- If byte-for-byte env preservation cannot be proven by the contract table, stop Wave 2 and
  escalate; never rename to make a test pass.
- If type/lint/import-linter fixes would require a new compatibility shim, wrapper layer, or
  configuration framework, stop — the issue forbids exactly that.
- Scope guard: `.env.example` edits are limited to lines whose owning field was deleted in the
  same wave; broader env-file restructure belongs to #3437. Encountering A12-listed variables
  (`MINIO_*`, `NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY`, `CLICKHOUSE_PASSWORD`,
  `MLFLOW_TRACKING_URI`, …) is out of scope — leave them.
- If a wave's measured diff exceeds roughly 2× its estimate, or anything outside the listed
  files must change, stop and get owner re-approval.
- Rollback is one atomic revert per wave; no partial wave is delivered.

## 8. Blocked elsewhere vs executable now

- **Executable immediately on approval:** Waves 0-2 (all evidence gathered at `0f774b3b6`;
  no open dependency blocks dead-field deletion or the flatten).
- **Blocked elsewhere:** any env renaming/prefixing or env-file restructure
  ([#3437](https://github.com/yastman/rag/issues/3437), OPEN, incl. the A12 addendum);
  Wave 3 additionally waits on the owner's reload-parity sign-off (DP7).
- **No longer relevant:** `streaming_enabled` disposition (#3481 delivered), Redis placement
  beyond documentation (#3362 delivered; `redis_url`/`redis_mode` stay duplicated
  intentionally per DP5), BotConfig knob purge (#3350 delivered), legacy Settings deletion
  (#3372 delivered).

## 9. Verification

The issue's verification command references `tests/unit/runtime/test_graph_config_streaming_flags.py`,
which #3481 deleted. Current-equivalent verification per wave:

```bash
uv run pytest -q tests/unit/runtime/test_graph_config_from_env.py tests/unit/runtime/test_redis_mode.py tests/unit/config tests/characterization/test_nonstreaming_generation_surface.py tests/unit/test_litellm_sdk_router.py
make type
make test-contract
```

Before deleting any symbol, re-run the field×caller inventory at the implementation SHA
(Wave 0); the existing config unit tests alone do not prove field liveness.
