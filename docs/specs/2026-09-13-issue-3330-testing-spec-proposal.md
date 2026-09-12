# SPEC(testing) proposal — replacing the remaining migration-only contracts and false ratchets

> **PROPOSAL — AWAITING OWNER DECISION.**
> This document is a design proposal for open issue
> [#3330](https://github.com/yastman/rag/issues/3330) (parent epic
> [#3338](https://github.com/yastman/rag/issues/3338)). Nothing in it is accepted
> scope yet. It does not authorize any implementation. The owner must resolve the
> five decision points in [section 4](#4-decision-points-owner-must-approve) before
> any wave below starts. Until then this file is a proposal, not a contract.

| Field | Value |
| --- | --- |
| Owning work item | [#3330](https://github.com/yastman/rag/issues/3330) — SPEC(testing): replace migration-only contracts and false ratchets with behavior coverage |
| Program epic | [#3338](https://github.com/yastman/rag/issues/3338) (role: test-portfolio coordinator; no implementation PR belongs to #3330 itself) |
| Proposal date | 2026-09-13 |
| Evidence base | Git `0f774b3b6` (= `origin/dev` at proposal time, worktree branch `codex/spec-3330-proposal`) |
| Original audit target | `fb64892bc7ea432d8249df5f2b0670b765b72a61`; re-audit snapshot `7a0b10fdd` (2026-09-06) |
| Status of #3330 | OPEN; 15 child issues still open, 31 delivered and closed (section 3) |
| Corpus scale at evidence SHA | `tests/` 91,415 LOC tracked; `tests/contract/` 10,986 LOC; `scripts/` 8,925 LOC |

## 1. Purpose and outcome

Issue #3330 requires that every retained test owns live observable behavior or a
stable architecture boundary, and that migration history, deleted-surface
tombstones, duplicate wrappers, source snapshots, fake E2E, and tests-of-tests are
removed by non-overlapping children. Most of that program has already been
delivered (section 3). This proposal:

1. inventories the **current residue** — the migration-only contracts and false
   ratchets that still exist at `0f774b3b6`, with verified LOC (section 2);
2. records what is **already gone**, with the merged delivery refs (section 3);
3. frames the **decision points** the owner must approve (section 4);
4. proposes a **bounded execution plan** with per-wave file lists, dependencies,
   and estimated LOC deltas (section 5);
5. states acceptance criteria, stop limits, and the blocked/executable split
   (sections 6–7).

Proposal scope: the remaining execution families of #3330 only. It creates no new
process, no second tracker, and no archive. Per the #3454 no-archive rule this is
a **new** proposal document for an open issue, not a restored deleted archive.

## 2. Current-state residue inventory (verified at `0f774b3b6`)

All LOC below were recounted from the tracked files at the evidence SHA (whole
physical lines, blank lines included). Where a number differs from the audit
snapshot quoted in the child issue, current Git wins and the drift is noted.

### 2.1 Tombstone/absence suites (migration-only contracts)

| Packet | File | LOC | Why it is residue |
| --- | --- | ---: | --- |
| #3410 | `tests/unit/services/test_draft_streamer_removed.py` | 196 | Asserts ImportError/absence of a removed streaming surface |
| #3410 | `tests/unit/services/test_draft_streamer_scanner_bound.py` | 105 | Tests the recursive absence scanner itself |
| #3410 | `tests/unit/services/test_services_public_api.py` | 42 | Public-API list built from historical absences |
| #3432 | `tests/contract/test_bot_lifecycle_extraction_contract.py` | 138 | Pins wrapper shape/extraction of lifecycle code |
| #3432 | `tests/contract/test_bot_postgres_bootstrap_extraction_contract.py` | 198 | Pins wrapper shape/extraction of bootstrap code |
| #3434 | `tests/contract/test_bot_observability_extraction_contract.py` | 112 | Extraction-shape ratchet (observability) |
| #3434 | `tests/contract/test_bot_state_helpers_extraction_contract.py` | 126 | Extraction-shape ratchet (state helpers) |
| #3434 | `tests/contract/test_bot_streaming_extraction_contract.py` | 167 | Extraction-shape ratchet (streaming) |

Subtotal: 8 files, 1,084 LOC. All three #3410 files still match the audited LOC
exactly — #3410 has not been started, and it unblocks #3434 and #3386.

### 2.2 Bespoke AST/source/architecture scanners (false ratchets)

| Packet | File | LOC | Why it is residue |
| --- | --- | ---: | --- |
| #3431 | `tests/contract/test_admin_metrics_uses_prometheus_contract.py` | 77 | Bespoke source scanner; direct `/metrics` handler test exists |
| #3431 | `tests/contract/test_error_contract.py` | 170 | Scans for a span helper with zero production calls (−3 vs audit) |
| #3431 | `tests/contract/test_hybrid_retrieve_complexity_contract.py` | 76 | Complexity ratchet; Radon gate owns it natively |
| #3431 | `tests/contract/test_ingestion_threadhop_contract.py` | 207 | Scans for a thread-hop pattern that no longer exists |
| #3457 | `tests/contract/test_architecture_layer_law_contract.py` | 49 | ADR-text architecture scanner |
| #3457 | `tests/contract/test_bot_no_private_runtime_internals_contract.py` | 61 | Private-symbol scanner |
| #3457 | `tests/contract/test_canonical_structure_contract.py` | 145 | Structure ratchet (+11 vs audit) |
| #3457 | `tests/contract/test_core_contracts_gap_contract.py` | 81 | Gap-list scanner |
| #3457 | `tests/contract/test_core_text_path_procedural_contract.py` | 46 | Procedural text-path scanner |
| #3457 | `tests/contract/test_entrypoint_contract.py` | 147 | Entrypoint list ratchet |
| #3457 | `tests/contract/test_layering_contract.py` | 82 | Duplicate layering scanner |
| #3457 | `tests/contract/test_layering_no_telegram_bot_imports_contract.py` | 140 | Hosted-gate layering scanner; replaced by import-linter |
| #3457 | `tests/data/known_layering_violations.json` | 1 | Empty violation allowlist |
| #3437 | `tests/contract/test_env_example_completeness_contract.py` | 465 | Repo-wide AST env allowlist with retired-surface exceptions and unused `_parse_env_file` (at line 368); −10 vs audit |

Subtotal: 14 files, 1,772 LOC. The #3457 hosted-gate retarget is still live:
`.github/workflows/ci.yml:155` and
`tests/contract/test_local_gate_policy_contract.py:66,424` select
`test_layering_no_telegram_bot_imports_contract.py` by name.

### 2.3 Stale contracts and scanner false negatives (A10)

| Packet | File | LOC | Disposition |
| --- | --- | ---: | --- |
| #3456 | `tests/contract/test_no_orphan_bot_bridge.py` | 76 | delete |
| #3456 | `tests/contract/test_no_redundant_get_client_patches_contract.py` | 82 | delete |
| #3456 | `tests/contract/test_observation_type_taxonomy_contract.py` | 105 | delete |
| #3456 | `tests/contract/test_tooling_enhancement_contract.py` | 198 | delete |
| #3456 | `tests/contract/test_vps_noncore_list_single_source_contract.py` | 176 | delete |
| #3456 (fix) | `tests/contract/test_no_dynamic_import_in_runtime_hotpath_contract.py` | 62 | keep, fix alias false negatives |
| #3456 (fix) | `tests/contract/test_no_get_event_loop.py` | 151 | keep, fix alias false negatives |
| #3456 (fix) | `tests/contract/test_no_global_random_seed_contract.py` | 69 | keep, require scoped save/restore pairing |
| #3456 (fix) | `tests/contract/test_qdrant_sdk_native_usage_contract.py` | 284 | keep, discover live modules instead of fixed list |

Subtotal: 5 delete files, 637 LOC; 4 retained scanners (566 LOC) get correctness
fixes, not deletion.

### 2.4 Recipe parsers and governance prose ratchets

| Packet | File | LOC | Disposition |
| --- | --- | ---: | --- |
| #3433 | `tests/contract/test_core_gate_optional_surfaces_contract.py` | 156 | delete after executable gate coverage |
| #3433 | `tests/contract/test_makefile_fast_lane_alignment_contract.py` | 162 | delete after executable gate coverage |
| #3433 | `tests/contract/test_makefile_lint_scope_contract.py` | 110 | delete after executable gate coverage |
| #3433 | `tests/contract/test_makefile_monolith_cleanup_contract.py` | 224 | delete after executable gate coverage (+104 vs audit — file grew) |
| #3433 | `tests/contract/test_makefile_parallel_args_override_contract.py` | 156 | delete after executable gate coverage |
| #3433 | `tests/contract/test_makefile_python_version_contract.py` | 142 | delete; `.python-version` + `requires-python` own the runtime |
| #3433 | `tests/contract/test_makefile_review_gate_no_autosync_contract.py` | 144 | delete after no-sync behavior proof |
| #3427 | `tests/unit/test_codeowners_contract.py` | 99 | delete whole file; GitHub owns CODEOWNERS matching |
| #3427 | `tests/unit/test_agents_contract.py` | 37 | partial: delete only the hook-policy prose assertion; keep the two native `git check-ignore` behavior tests |
| #3427 | `tests/unit/test_hygiene_governance_docs_contract.py` | 59 | partial: remove only the historical deletion tombstone |

Subtotal: #3433 = 7 files, 1,094 LOC input (issue title says 1,005; drift is the
grown monolith-cleanup file) with a net-reduction floor of 850 LOC; #3427 = 99
whole-file plus two partial edits.

### 2.5 Fake-SDK harness and tests-of-tests (#3428)

| File | LOC | Disposition |
| --- | ---: | --- |
| `tests/unit/conftest.py` | 383 | remove the fake aiogram/aiogram-dialog/FlagEmbedding/asyncpg/Anthropic/Fluent/OTEL `sys.modules` graph (roughly lines 28–232, ~205 LOC) and `pytest_unconfigure` restore (line 233); keep #3447's dotenv isolation at `tests/conftest.py` |
| `tests/unit/test_conftest_lazy_mock_get_client.py` | 20 | delete (tests a test fixture) |
| `tests/unit/test_module_pollution.py` | 127 | delete (meta-policy scanner exempting the global mutations) |
| `tests/unit/test_main.py` | 259 | rewrite against directly imported collaborators |
| `tests/unit/test_bot_log_triage.py` | 390 | rewrite against directly imported collaborators |

Subtotal: 147 LOC straight deletion, ~205 LOC conftest graph removal, 649 LOC
rewritten in place.

### 2.6 A08 migration micro-suites and the test-only splitter (#3444)

| File | LOC | Disposition |
| --- | ---: | --- |
| `tests/unit/scripts/test_git_hygiene.py` | 31 | merge with the row below into one real temp-repository behavior owner; delete absence/source-string migration assertions |
| `tests/unit/test_native_git_migration_contract.py` | 72 | merge (see above) |
| `tests/unit/test_telegram_formatting.py` | 77 | merge into `tests/unit/services/test_telegram_formatting.py` (23 LOC) as the one formatting owner |
| `tests/unit/test_telegram_constants.py` | 11 | delete with the test-only `split_telegram_response` (defined at `telegram_bot/constants/__init__.py:7`, zero runtime callers) after final revalidation |

Subtotal: 191 LOC gross across four files plus one test-only production function.

### 2.7 False-green judge heuristics and version-pin ratchet

| Packet | File | LOC | Disposition |
| --- | --- | ---: | --- |
| #3391 | `scripts/e2e/claude_judge.py` (PassthroughJudge at line 253) | 417 | fix: compare requested values, not token presence; runner wiring only if changed |
| #3391 | `tests/unit/e2e_adapters/test_passthrough_judge.py` | 239 | extend with the three confirmed false greens as RED cases |
| #3409 | `tests/unit/dialogs/test_dialog_dependency_baseline.py` | 8 | delete the exact `aiogram==3.31.0` / `aiogram-dialog==2.6.0` equality test after used-API behavior owners exist |

These are behavior-correctness packets, not deletions; they are in scope because
#3391 is the P1 false-green risk that the strict #3364 gate would inherit, and
#3409 is a false ratchet (version pins in tests instead of manifest/lock).

### 2.8 Unowned A04-addendum script gates (decision point D2)

The A04 addendum comment on #3330 assigns two private policy gates for deletion
after external-caller revalidation. No child issue currently owns them — this is
a real ownership gap, and revalidation at `0f774b3b6` shows zero callers:

| File | LOC | Caller evidence at `0f774b3b6` |
| --- | ---: | --- |
| `scripts/check_test_tracking.py` | 80 | no reference outside `tests/unit/scripts/` |
| `tests/unit/scripts/test_check_test_tracking.py` | 48 | private consumer |
| `scripts/ci/validate_pr_guardrails.py` | 417 | only a stale comment at `.github/bug-classes.yml:2` (its other named consumer, swarm-acceptance, was retired by #3385); no workflow or pre-commit caller |
| `tests/unit/scripts/test_validate_pr_guardrails.py` | 280 | private consumer |

Subtotal: 4 files, 825 LOC. The A04 addendum requires deleting both
implementations and their private tests rather than writing tombstones, while
keeping `.github/bug-classes.yml` and the behavior tests that consume that
registry (`tests/unit/test_bug_class_registry_contract.py`). The stale comment on
`bug-classes.yml:2` should be corrected in the same packet.

### 2.9 Residue summary

Roughly **6,000 LOC gross** of migration-only contracts and false ratchets remain
(≈4,900 in deletion packets, ≈1,100 in fix/rewrite packets that mostly keep their
LOC), spread across 15 open children plus the unowned A04-addendum pair. Net
deletion after the mandated replacement coverage lands is estimated at
**4,500–5,000 LOC** (per-issue floors: #3433 ≥ 850 net, #3457 ≥ 550 net).

## 3. Already delivered (evidence — what is NOT in scope)

The recent deletion waves removed the bulk of the original audit. Each row was
verified against the tracked tree at `0f774b3b6`: the listed surfaces are gone.

| Wave | Delivered via | Removed from the tree |
| --- | --- | --- |
| #3339 duplicate-name ratchet | PR #3527 (`31ca7a3d3`) | `scripts/check_unique_test_names.py`, `tests/data/known_duplicate_test_names.json`, 3 tombstone contracts, scanner unit test |
| #3340 migration tombstones | PR #3526 (`b4ace0572`) | 8 tombstone contracts + `tests/contract/conftest.py` (989 LOC claim) |
| #3341 deleted-façade guards | PR #3557 (`dcb7641aa`) | 4 "no imports of deleted façade" contracts (466 LOC claim) |
| #3342 retired-service checks | PR #3568 (`076a8796f`) | K8s parity, LiveKit/RAG-API voice pipeline, quantization smoke |
| #3343 mock-only "E2E" | PR #3569 (`74e180fb5`) | `tests/e2e/surfaces/`, `tests/integration/test_qdrant_service.py` (471 LOC claim) |
| #3344 collection warnings | PR #3505 | PytestCollectionWarning noise; alias/import fixes |
| #3345 PropertyBot builders | PR #3562 | Eleven duplicated builders consolidated (includes the demo-catalog callback duplicate) |
| A05 #3402/#3403/#3404/#3405/#3406/#3407/#3408 | PRs #3551/#3549/#3555/#3550/#3570/#3595/#3548 | Duplicate scanner/security/BGE/redis-lock/vector-routing/ingestion/PII suites; #3406 also removed the stale `BotConfig` ratchet |
| #3390 CRM FSM delete | PR #3565 | Archived CRM FSM groups + vacuous state-coverage ratchet |
| #3411 E2E mislabel | PR #3564 | `tests/unit/handlers/test_demo_e2e.py` |
| A07 #3424/#3425/#3426/#3429/#3430 | PRs #3607/#3513/#3512/#3525/#3511 | 7 compose/Dockerfile contracts consolidated onto native render; inline-keyboard ratchet; unreachable VPS tests; dormant HyDE/query-analysis surface + its tests; duplicate 296-line middleware suite |
| #3435 async AST ratchet | merge `85badc4a3` (`1ff09aeb4`) | `test_async_tests_have_await_contract.py` |
| #3436 callback contracts | PR #3567 (`8d7ee0e00`) | 3 callback/CRM/feedback extraction contracts (449 LOC claim) |
| #3446 Python matrix | PR #3521 | Semantic runtime-matrix ownership replacing version ratchets |
| #3447 Redis-load safety | merge `4115e6d57` (+`d22d3f402` repair) | Load isolated to run-owned disposable containers; repo dotenv loading removed from `tests/conftest.py` |
| #3413–#3422 deterministic E2E | PRs #3596/#3583/#3597/#3598/#3602/#3603/#3604/#3601/#3600/#3605 | Hermetic capability suites replaced the fake live/E2E corpus; the two 41-byte ONNX files remain static fixtures rejected by runtime lanes |
| A11 orphans #3384/#3385 | PRs #3590/#3591 | Orphan eval/benchmark corpus (1,395 LOC); Kiro/tmux swarm incl. its private script tests (4,154 LOC) |
| #3482 partial | `4cc4432a3` (Refs #3482) | Stale pre-#3326 `candidate-check` unit regex deleted; canonical owner `test_makefile_local_gate_ladder` keeps the ladder |

Behavior owners that now make the remaining ratchets redundant: the deterministic
capability E2E lanes (funnel, postgres, ingestion, catalog, voice, telegram
dispatch, handoff, core, observability), the hermetic harness (#3414), the
native rendered-Compose contracts (#3424), and import-linter as the designated
boundary owner (#3457). These owners did not exist (or were not green) when the
ratchets were written; that is the core rationale for finishing the removal.

## 4. Decision points (owner must approve)

The owner reads this section and says "go". Each point needs one answer recorded
on #3330 before the corresponding wave starts.

### D1 — Wave order for the remaining deletion packets

- **Option A (recommended): independence-first waves.** Run the packets whose
  dependencies are already closed as Wave 1 (section 5), then the #3353-coupled
  packets, then the #3355-coupled final wave. Rationale: 18 merged waves landed
  as one exact-scope child each with green gates; no failure in that record came
  from ordering, while #3457's hosted-gate retarget is the one genuinely risky
  move and benefits from a stabilized contract lane.
- **Option B: issue-number order.** Simple, but blocks ready packets (#3431's
  dependencies #3331/#3342/#3405 are all closed) behind unrelated open ones.
- **Option C: one bulk PR.** Rejected by the parent contract — the #3330
  comment "Do not implement a single bulk test deletion PR" — and by every
  child's exact file ownership.

### D2 — Owner for the two unowned A04-addendum script gates (825 LOC)

`scripts/check_test_tracking.py` + `scripts/ci/validate_pr_guardrails.py` and
their private tests are mandated for deletion by the A04 addendum comment on
#3330, but **no open child issue owns them** (verified by issue search). External
callers are already revalidated as zero (section 2.8), so the packet has no open
dependency.

- **Option A (recommended): open one new exact-scope child issue** owning
  exactly the four files plus the `.github/bug-classes.yml:2` comment fix.
  Rationale: the global worker contract requires exact non-overlapping file sets;
  #3456 and #3428 already own their scopes precisely and must not absorb files.
- **Option B: extend #3456** (thematically "stale scanners") — violates its
  five-file exact delete ownership and mixes A04 scripts into an A10 packet.
- **Option C: drop the deletion.** Leaves 825 LOC of private meta-gates that
  nothing executes, directly against the #3330 outcome statement.

### D3 — #3437 sequencing against open dependency #3355

#3437 (465-LOC env AST allowlist → typed + Compose-native ownership, ≤150 LOC)
formally depends on #3355 (LiteLLM boundary characterization, open), #3350/#3362/
#3367 (closed).

- **Option A (recommended): hold #3437 until #3355 lands.** Rationale: the ≤150
  LOC contract must keep one explicit allowlist for variables consumed directly
  by an official SDK; without #3355's characterized LiteLLM surface that mapping
  would be guessed and reworked.
- **Option B: start now, accept rework risk on the SDK allowlist.**
- **Option C: descope #3437 to pure deletion** without replacement owners —
  violates its own acceptance ("every documented variable has exactly one
  owner") and would break `.env.example` completeness coverage.

### D4 — #3391 judge-fix scope (P1 false-green risk)

Confirmed false greens: price bound violated (90000 accepted for max 80000),
wrong attribute matched (price found for a rooms query), loose distance marker.
#3364's strict gate inherits these verdicts.

- **Option A (recommended): full assertion-type inventory as written** — exact
  normalized values, range/upper bound, set membership, required/forbidden
  statements, route/error outcomes — capped by the issue's own non-goal (parse
  only explicit supported values; no natural-language mini-LLM; ambiguity
  becomes provider-judge-only, never green). Rationale: the three proven false
  greens show the failure is a class, not three bugs; option B leaves the class
  open under a strict gate.
- **Option B: minimal fix of the three confirmed examples only.** Fast, but the
  next scenario type re-opens the hole.
- **Option C: move all ambiguous scenarios to provider-judge-only and delete
  the token-presence path.** Honest but shrinks deterministic coverage that the
  just-delivered E2E portfolio (#3596–#3605) was built to provide.

### D5 — When #3330 itself may close

- **Option A (recommended): hold #3330 open until the final gate.** Completion
  requires "all child gates green at one SHA", zero unexpected skip/warning, no
  fake-only E2E, and a removed/rewritten LOC report with a retained-behavior
  matrix. #3437, #3456 and #3457 each name the "final #3330 gate" as successor;
  #3328 (required-CI wiring) and #3364 (strict six-service gate) are that gate.
  Only this option can produce the one-SHA proof.
- **Option B: close when the last deletion child merges.** Cheaper but cannot
  satisfy the issue's own Completion section.
- **Option C: close now and track the remainder in #3338 only.** Loses the
  portfolio-level acceptance that #3338's DAG explicitly delegates to #3330.

## 5. Proposed execution plan

One branch/worktree and one exact-scope PR per child, mirroring the delivered
waves. No bulk PR. Each child starts with its own characterization/red proof per
its issue and keeps its own rollback contract.

### Wave 1 — dependencies closed; executable immediately on approval

| Packet | Files (exact) | Gross LOC | Replacement / notes |
| --- | --- | ---: | --- |
| #3410 | the 3 files in 2.1 | 343 | Move draft-ID (positive int32) + send/finalize order + retained-exports assertions into the canonical supervisor/streaming suites; unblocks #3434 and #3386 |
| #3431 | the 4 files in 2.2 | 530 | No replacement scanner; Radon + existing direct metrics/retrieval tests |
| #3432 | the 2 files in 2.1 | 336 | Direct lifecycle + bootstrap unit behavior (recording fake pool); live PG stays with #3415 |
| #3433 | the 7 files in 2.4 | 1,094 | Bounded-subprocess execution of advertised targets; net ≥ 850; at most one target-existence smoke |
| #3456 | the 5 delete files in 2.3 + 4 fixes | 637 del | Negative fixtures prove each scanner false negative first |
| #3427 | 1 whole file + 2 partials in 2.4 | ~140 | Keep `git check-ignore` tests; CODEOWNERS stays tracked |
| #3409 | 1 file in 2.7 | 8 | Used-API behavior cases added to existing dialog suites first |
| #3391 | 2 files in 2.7 | ~0 net | RED tests for the three false greens, then value comparison; P1 — schedule first in the wave |
| D2 child (new) | 4 files in 2.8 | 825 | Only after D2 is approved; includes `bug-classes.yml:2` comment fix |

Wave-1 gross delta: ≈ **−3,900** LOC (net ≈ −3,000 after replacement coverage).

### Wave 2 — blocked on open issues #3353 / #3438

| Packet | Blocked by | Files | Gross LOC | Notes |
| --- | --- | --- | ---: | --- |
| #3434 | #3410 (Wave 1) + #3353 | 3 files in 2.1 | 405 | Retain `_build_trace_metadata` only if indexed callers remain post-#3353 |
| #3457 | #3353 (plus closed #3333) | 9 files in 2.2 | 752 | Atomic retarget of `.github/workflows/ci.yml:155` and `test_local_gate_policy_contract.py:66,424` to the import-linter check in the same PR; net ≥ 550 |
| #3428 | #3342/#3345 (closed) + #3353 | 5 files in 2.5 | ~352 del + 649 rewrite | Preserve #3447's dotenv isolation; lanes collect warning-free |
| #3444 | #3438 | 4 files in 2.6 + splitter | 191 | Real temp-repository Git behavior owner; one formatting owner |

Wave-2 gross delta: ≈ **−1,700** LOC plus in-place rewrites.

### Wave 3 — final gate

| Packet | Blocked by | Scope | Delta |
| --- | --- | --- | --- |
| #3437 | #3355 | 465 → ≤150 LOC, zero AST walks, zero retired-surface exceptions | ≈ −315 net |
| #3482 remainder | #3328 | Name the canonical Makefile contract lane in required CI (partial already delivered by `4cc4432a3`) | ~0 |
| #3328 | — | Contract-gate recovery; verified coverage into required CI | — |
| #3364 | #3391, #3457, wave 1–2 | Strict six-service full-stack capability gate | additive |
| #3412 | #3364, #3355, #3387, #3388, #3347 outcome | Opt-in real-provider smoke (`tests/smoke/test_real_providers.py`); never a deterministic predecessor | additive |
| #3445 | #3392 cohort | Exact install-set validation for the production image | additive |
| #3330 completion | all above | One-SHA green proof, retained-behavior matrix, removed/rewritten LOC report | — |

Total program estimate: gross ≈ **−6,000 LOC**, net ≈ **−4,500 to −5,000 LOC**
after replacement coverage; 7 additive/fix packets carry their own LOC.

## 6. Acceptance criteria

1. Every open #3330 child (15 issues) plus the D2 child is closed by its own
   issue acceptance, or explicitly re-parented with owner sign-off.
2. All child gates green at one SHA (the #3330 Completion clause).
3. Zero unexpected skip/warning; required service lanes fail rather than skip;
   no fake-only test is counted as E2E.
4. A removed/rewritten LOC report and a retained-behavior matrix are attached to
   #3330 (tracker owns the evidence; this document is not updated post-hoc
   except to point at the delivered SHA).
5. No tombstone, absence scanner, recipe parser, prose pin, fake-SDK
   `sys.modules` entry, or tests-of-tests remains from the inventoried residue.
6. D1–D5 answers recorded on #3330 before the corresponding wave starts.

## 7. Stop limits and non-goals

Stop limits:

- A characterization RED that reveals a live regression stops that packet only;
  rollback restores the direct behavior test, never the ratchet (per-child
  rollback contracts already say this).
- If #3353 or #3438 slip, Wave 2 stops without touching Wave 1; no packet widens
  its file list to "make progress".
- Any request to revive a deleted scanner, allowlist, or archive stops the work
  and goes back to the owner.
- The delivery gate for every packet remains `make candidate-check`; nothing
  here weakens or bypasses it.

Explicitly out of scope for the whole program:

- Production behavior changes, except the four named touchpoints: the judge
  script (#3391), the test-only `split_telegram_response` (#3444), the CI
  selection lines (#3457), and typed settings/`.env.example` (#3437).
- Dependency upgrades and version selection (#3392 and its cohorts).
- The PropertyBot façade removal itself (#3386) — this plan only unblocks it.
- Restoring any file deleted by the delivered waves or by #3454's archive
  cleanup; this proposal is a new document, not an archive restoration.
- New test frameworks, pytest plugins, scanner frameworks, or a second Make
  parser (each child's non-goal clause).

## 8. Blocked vs executable summary

Executable immediately on owner approval (all dependencies closed, callers
revalidated): #3410, #3431, #3432, #3433, #3456, #3427, #3409, #3391, and —
pending D2 — the new A04-addendum child.

Blocked on other open issues: #3434 (#3410, #3353), #3457 (#3353), #3428
(#3353), #3444 (#3438), #3437 (#3355), #3482 remainder + #3328 (gate wiring),
#3364 (final strict gate), #3412 (#3364, #3355, CRM decision #3347), #3445
(#3392).

## 9. Verification commands (evidence appendix)

```text
git rev-parse HEAD                      # 0f774b3b6... at proposal time
git ls-files tests/ scripts/            # tracked corpus
# per-file LOC: python -c "print(sum(1 for _ in open(p, 'rb')))" <file>
git log --diff-filter=D --name-status fb64892bc..origin/dev -- tests/ scripts/
gh issue view 3330                      # spec mandate and completion clauses
```

Child-issue states, exact scopes, and LOC quotes in sections 2–3 were taken from
the live GitHub issue bodies at proposal time; file paths and LOC were recounted
from the tracked tree at `0f774b3b6` and take precedence where they differ.
