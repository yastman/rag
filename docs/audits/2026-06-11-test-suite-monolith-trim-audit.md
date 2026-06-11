# Test Suite Audit for Python Monolith Core

Date: 2026-06-11
Branch: `audit/test-suite-trim-monolith-20260611`
Repository: `yastman/rag`
Base branch checked: `dev`
Scope: test-suite audit, required/optional/archive lanes, and test reduction plan for the Python monolith direction.
Runtime code changes in this branch: none.

---

## 1. Problem

The project is moving toward a lean Python monolith core:

```text
telegram_bot -> src.core -> src.runtime -> clients/providers
```

But the test suite still reflects the old platform scope:

```text
Telegram bot
RAG graph
Mini App
voice
Docling / CocoIndex ingestion
Langfuse / OTel / Sentry observability
Docker service checks
benchmarks
evals
legacy graph / legacy API paths
```

This creates three problems:

1. The fast gate runs too much.
2. Optional/legacy services keep blocking core work.
3. Deleting or optionalizing services becomes hard because their tests are still treated as first-class required tests.

The goal is not to delete safety. The goal is to keep the tests that prove the monolith core and move service-specific tests into optional lanes.

---

## 2. Current test setup

### 2.1 Current fast gate

`make test` currently runs:

```bash
pytest tests/unit/ tests/integration/test_graph_paths.py \
  ... \
  -m "not legacy_api and not requires_extras and not slow"
```

Problem:

```text
tests/unit/ is too broad.
It includes tests for Telegram, graph legacy, observability, ingestion, API, Mini App, and optional surfaces.
```

### 2.2 Current full/unit lanes

The Makefile already has useful separation:

```text
test              = fast deterministic PR/local gate
test-unit         = all unit tests except legacy/requires_extras/slow
test-unit-full    = unit tests with optional extras
test-unit-extras  = optional-extra tests only
test-contract     = tests/contract
test-nightly      = chaos/smoke/slow
```

This is directionally good, but the default fast gate is still too wide for a monolith-core migration.

### 2.3 CI currently does not run pytest

The current GitHub CI runs:

```text
secret scan
semgrep
ruff lint/format
uv lock
compose config
```

It does not run a core pytest lane. That means local/PR descriptions may claim test success, but GitHub CI does not enforce the core behavior.

### 2.4 Existing marker system is useful

The repo already has pytest markers:

```text
unit
integration
slow
chaos
load
e2e
smoke
benchmark
legacy_api
requires_extras
kommo
contract
baseline
performance
regression
no_services
requires_services
```

This should be kept and extended, not replaced.

---

## 3. Target test strategy

Use four lanes:

```text
Lane 1: core-required
Lane 2: adapter-required
Lane 3: optional-service
Lane 4: archive/delete candidates
```

### 3.1 Lane 1 — core-required

These must stay required for the monolith core.

Should prove:

```text
src.core contracts
src.core.run_assistant_request
src.runtime.pipeline.assistant_pipeline
runtime generation fallback behavior
runtime grounding policy
runtime Qdrant service contracts
cache policy that affects core output
runtime->telegram coupling ratchet
core live E2E optional/manual
```

Required examples:

```text
tests/unit/core/
tests/unit/runtime/
tests/contract/test_runtime_no_telegram_bot_coupling_contract.py
tests/contract/test_layering_no_telegram_bot_imports_contract.py
tests/contract/test_langfuse_optional_core_contract.py
tests/e2e/test_core_live_ingest_answer.py  # manual/live, not fast default
```

### 3.2 Lane 2 — adapter-required

These should run when the adapter changes, not for every core PR.

Adapter lanes:

```text
telegram adapter
api adapter
voice adapter
mini-app adapter
```

Examples:

```text
tests/unit/test_bot_handlers.py
tests/unit/test_bot_initialization.py
tests/unit/api/
tests/unit/mini_app/
tests/unit/voice/
mini_app/frontend tests
```

### 3.3 Lane 3 — optional-service

These are useful but not required for core monolith development.

Categories:

```text
ingestion/docling/cocoindex
observability/langfuse/otel/sentry
smoke/live docker services
benchmarks/evals/ragas
kommo live CRM
load/chaos
```

Run them with:

```text
make test-unit-extras
make test-smoke
make test-nightly
make test-benchmark
make e2e-core-live
```

### 3.4 Lane 4 — archive/delete candidates

These should be removed or archived only when the related product surface is removed.

Candidates:

```text
legacy graph path tests after graph builder is retired
old Langfuse/OTel trace-validator tests after optionalization cleanup
Mini App tests after Mini App archive decision
voice tests after voice adapter decision
old API tests once API is adapter-over-core
obsolete Compose/LiteLLM proxy tests after #2454 cleanup
```

---

## 4. What to keep

### 4.1 Keep core contract tests

Keep and strengthen:

```text
tests/contract/test_runtime_no_telegram_bot_coupling_contract.py
tests/contract/test_layering_no_telegram_bot_imports_contract.py
tests/contract/test_langfuse_optional_core_contract.py
tests/contract/test_service_dependency_markers_contract.py
```

Why:

```text
These encode architectural direction and prevent regressions during monolith cleanup.
```

### 4.2 Keep service marker contract

`test_service_dependency_markers_contract.py` is useful because it forces integration/smoke tests to say whether they need services.

Keep it, but extend the idea to optional surfaces:

```text
core_required
adapter_required
optional_surface
archive_candidate
```

### 4.3 Keep core E2E, but not in fast default

Keep:

```text
tests/e2e/test_core_live_ingest_answer.py
```

But run manually or as live lane:

```text
make e2e-core-live
```

Not every small PR needs live Qdrant/BGE.

### 4.4 Keep graceful-degradation observability tests

Do not delete all observability tests. Keep tests proving:

```text
Langfuse disabled by default
core/runtime does not require Langfuse import
observability missing/unavailable does not break core
Sentry/Langfuse no-op path is safe
```

This aligns with optional observability, not observability deletion.

---

## 5. What to move out of default fast gate

The default fast gate should not run every historical unit test.

Move these out of the default core gate:

### 5.1 Telegram adapter tests

Examples:

```text
tests/unit/test_bot_handlers.py
tests/unit/test_bot_initialization.py
telegram_bot/bot.py heavy behavior tests
```

New lane:

```text
make test-telegram-adapter
```

Run when:

```text
telegram_bot/* changes
src.core AssistantResult rendering changes
HITL button rendering changes
```

### 5.2 API tests

Examples:

```text
tests/unit/api/
```

New lane:

```text
make test-api-adapter
```

Run when:

```text
src/api/* changes
core response schema changes
```

After #2483, API tests should assert API calls `src.core`, not graph builder.

### 5.3 Voice tests

Examples:

```text
tests/unit/voice/
tests/unit/agents/test_voice_agent_factory.py
```

New lane:

```text
make test-voice-extra
```

Run only with voice extra.

### 5.4 Mini App tests

Examples:

```text
tests/unit/mini_app/
mini_app/frontend tests
```

New lane:

```text
make test-mini-app
make test-frontend
```

If Mini App is archived, move these tests to archive or delete with the surface.

### 5.5 Ingestion tests

Examples:

```text
tests/unit/ingestion/
Docling
CocoIndex
Qdrant ingestion target tests
```

New lane:

```text
make test-ingest-extra
```

Run only with ingest extra or ingestion changes.

### 5.6 Eval / benchmark tests

Examples:

```text
tests/unit/evaluation/
tests/benchmark/
RAGAS / datasets / pandas paths
```

New lane:

```text
make test-eval-extra
make test-benchmark
```

Run only for evaluation changes.

### 5.7 Legacy graph / legacy API tests

Current marker already exists:

```text
legacy_api
```

Do not expand these. As ADR-0019 progresses, convert useful tests to core/runtime tests or delete them.

---

## 6. What to remove or archive later

Do not delete immediately, but mark these as removal candidates tied to service decisions.

### 6.1 Observability trace-validator tests

There is already a contract checking obsolete observability assets are removed:

```text
tests/contract/test_obsolete_observability_assets_removed_contract.py
```

Keep this contract if the project is truly removing old trace validators.

But re-scope #2452:

```text
not “remove observability tests”
but “remove obsolete trace-validator assets and keep optional no-op contracts”
```

### 6.2 Mini App tests

If #2430 archives Mini App:

```text
move tests/unit/mini_app/ to archive with mini_app
or delete if no longer used
```

Do not keep Mini App tests in required PR gate.

### 6.3 Voice tests

If voice is optional:

```text
mark all voice tests requires_extras
exclude from core gate
```

If voice is archived:

```text
archive/delete voice tests together with voice code
```

### 6.4 Old graph tests

After #2405/#2427:

```text
remove StateGraph-specific tests
keep behavior tests rewritten against run_assistant_pipeline
```

### 6.5 LiteLLM proxy tests

After #2454:

```text
remove tests that assert Docker LiteLLM proxy behavior
keep tests that assert runtime LiteLLM Router behavior
```

---

## 7. New recommended Makefile lanes

Add focused lanes:

```makefile
test-core:
	pytest \
	  tests/unit/core/ \
	  tests/unit/runtime/ \
	  tests/contract/test_runtime_no_telegram_bot_coupling_contract.py \
	  tests/contract/test_layering_no_telegram_bot_imports_contract.py \
	  tests/contract/test_langfuse_optional_core_contract.py \
	  -q --timeout=30 -m "not requires_extras and not slow"

test-telegram-adapter:
	pytest tests/unit/telegram_bot tests/unit/test_bot_*.py -q --timeout=30

test-api-adapter:
	pytest tests/unit/api/ -q --timeout=30

test-ingest-extra:
	uv sync --extra ingest --all-groups
	pytest tests/unit/ingestion/ -q --timeout=30

test-voice-extra:
	uv sync --extra voice --all-groups
	pytest tests/unit/voice/ tests/unit/agents/test_voice_agent_factory.py -q --timeout=30

test-mini-app:
	pytest tests/unit/mini_app/ -q --timeout=30
	$(MAKE) test-frontend

test-eval-extra:
	uv sync --extra eval --all-groups
	pytest tests/unit/evaluation/ -q --timeout=30
```

Then redefine:

```text
make test = test-core + minimal adapter smoke only if needed
make test-unit = broad local unit lane, not required core PR lane
make test-full = all extras/nightly/manual
```

---

## 8. New CI recommendation

Current CI does not run pytest. Keep it that way for required checks.

**Policy:**
- GitHub required CI = hygiene/static only (Lint, Semgrep, Secret Scan, Lockfile, Compose Config)
- Python tests = local/manual or workflow_dispatch-only
- `make test-core` = local/manual monolith-core gate
- Do NOT make pytest jobs required branch protection

If a manual core-tests workflow is added later, it must use `workflow_dispatch` only:

```yaml
on:
  workflow_dispatch:
```

Do not add full `make test` to CI; it is too broad.

Optional scheduled jobs (all non-required):

```text
nightly optional extras (workflow_dispatch only)
weekly full tests (workflow_dispatch only)
manual live e2e (workflow_dispatch only)
```

---

## 9. Issue mapping

### Create new issue: TEST-001 — Define core-required test lane

Scope:

```text
Add make test-core as local/manual monolith-core gate.
Do not make it required GitHub branch protection.
Do not add it to required CI until explicitly approved later.
```

Acceptance:

```text
make test-core target exists
make test-core is documented as local/manual
Existing make test remains unchanged
GitHub required CI remains hygiene/static only
If a manual core-tests workflow is added, it uses workflow_dispatch only and is not required
```

### Create new issue: TEST-002 — Mark optional surface tests

Scope:

```text
Mark voice/ingest/eval/Mini App tests as requires_extras or adapter-specific.
```

Acceptance:

```text
core gate does not install optional deps
optional tests still runnable by explicit Make targets
```

### Create new issue: TEST-003 — Archive/delete tests for removed surfaces

Scope:

```text
After Mini App/voice/legacy graph decisions, delete or archive related tests with code.
```

Acceptance:

```text
No required tests for removed services remain.
No test imports removed modules.
```

### Create new issue: TEST-004 — Rewrite old graph/API tests against core

Scope:

```text
Convert behavior tests that still prove useful requirements to run_assistant_pipeline / run_assistant_request.
Delete graph implementation tests after rewrite.
```

Acceptance:

```text
behavior coverage remains
implementation-specific StateGraph assertions gone
```

### Create new issue: TEST-005 — Observability optionalization test cleanup

Scope:

```text
Keep no-op/graceful-degradation contracts.
Remove obsolete trace-validator tests only.
```

Acceptance:

```text
core does not require Langfuse/OTel
obsolete trace validator assets remain absent
optional observability tests run only in optional lane
```

---

## 10. Practical reduction plan

### Phase A — No deletion, only lanes

```text
Add make test-core as local/manual gate.
Do not add required CI pytest job.
Keep existing make test as-is for one PR if needed.
```

### Phase B — Move optional tests out of core lane

```text
voice -> test-voice-extra
Mini App -> test-mini-app
ingest -> test-ingest-extra
eval -> test-eval-extra
observability heavy -> optional observability lane
```

### Phase C — Rewrite useful legacy tests

```text
Graph behavior tests -> runtime/core tests
API graph tests -> API adapter over core tests
Telegram generation tests -> adapter wrapper tests
```

### Phase D — Delete/archive tests with removed services

```text
Only delete when code is removed or archived.
Never keep tests for services that no longer exist in required lanes.
```

---

## 11. What not to do

Do not:

```text
- delete all tests for optional services immediately
- put full test suite in CI as required before lanes are split
- delete observability no-op tests
- delete Mini App/voice tests before product archive decision
- keep service tests in make test-core
- let test cleanup touch runtime generation during #2486/#2489
```

---

## 12. Final recommendation

Yes, the test suite should be reduced for the Python monolith direction.

But the safe way is:

```text
1. Create test-core lane.
2. Move service tests to explicit optional lanes.
3. Rewrite useful legacy behavior tests against src.core/src.runtime.
4. Delete tests only when the service/code is actually removed.
```

The core gate should prove this and nothing more:

```text
core contracts
runtime pipeline
generation fallback
grounding policy
runtime->telegram coupling ratchet
core observability optionality
```

Tests for services that will not exist should not stay in the required gate. They can stay temporarily as optional/archive tests until the corresponding service removal PR lands.
