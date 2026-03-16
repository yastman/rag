# Open Issues Reconciliation Notes

Evidence timestamp: 2026-03-16 (UTC)

## #952
- Issue claim: add sdk_agent streaming response path.
- Current code evidence:
  - `telegram_bot/bot.py:90` defines `_stream_agent_to_draft(...)`.
  - `telegram_bot/bot.py:3606` calls `_stream_agent_to_draft(...)` from supervisor flow.
- Current test evidence:
  - `tests/unit/test_agent_streaming.py` contains dedicated tests for `_stream_agent_to_draft`.
- GitHub state evidence:
  - CLOSED - https://github.com/yastman/rag/issues/952
- Verdict: close

## #901
- Issue claim: index `services.yaml` into Qdrant and wire command entrypoint.
- Current code evidence:
  - `scripts/index_services.py` includes `index_services(...)`.
  - `Makefile:822` defines `ingest-services`.
  - `Makefile:824` executes `uv run python -m scripts.index_services`.
- Current test evidence:
  - `tests/unit/test_index_services.py` has direct unit coverage for writer contract and idempotency.
- GitHub state evidence:
  - CLOSED - https://github.com/yastman/rag/issues/901
- Verdict: close

## #855
- Issue claim: missing unit tests for grade/rerank/rewrite nodes.
- Current code evidence:
  - Direct node-level tests exist in `tests/unit/graph/nodes/test_grade.py`,
    `tests/unit/graph/nodes/test_rerank.py`, `tests/unit/graph/nodes/test_rewrite.py`.
- Current test evidence:
  - `rg` output confirms dedicated files and test functions are present.
- GitHub state evidence:
  - CLOSED - https://github.com/yastman/rag/issues/855
- Verdict: close

## #857
- Issue claim: missing dedicated coverage for search/manager/dialog/ingestion/voice modules.
- Current code evidence:
  - Dedicated test files exist for all named surfaces:
    `test_search_engines.py`, `test_manager_tools.py`, `test_crm_cards.py`,
    `test_gdrive_flow.py`, `test_gdrive_indexer.py`, `test_qdrant_hybrid_target.py`,
    `test_voice_schemas.py`, `test_voice_observability.py`.
- Current test evidence:
  - `uv run pytest ...` targeted Task 6 suite passed (`138 passed, 2 skipped`).
- GitHub state evidence:
  - CLOSED - https://github.com/yastman/rag/issues/857
- Verdict: close

## #978
- Issue claim: pre-main audit findings need fresh proof on current `dev`.
- Current code evidence:
  - Audit report exists: `docs/plans/2026-03-16-pre-pr-pre-main-audit-report.md`.
- Current test evidence:
  - Re-ran `ruff`, `mypy`, and `pytest tests/unit -q` and updated stale count in report.
- GitHub state evidence:
  - CLOSED - https://github.com/yastman/rag/issues/978
- Verdict: close

## #981
- Issue claim: remaining Bandit/Vulture findings after audit.
- Current code evidence:
  - Removed pseudo-random draft IDs (`secrets` helper).
  - Removed B105 placeholder-token false positives in Kommo seed payloads.
  - Cleared B112 keyboard `except/continue` path and vulture-unused callback noise.
- Current test evidence:
  - Targeted pytest + bandit + vulture reruns completed during Tasks 8-10.
- GitHub state evidence:
  - CLOSED - https://github.com/yastman/rag/issues/981
- Verdict: close

## #858
- Issue claim: `ignore_errors=true` masks mypy in core modules.
- Current code evidence:
  - Current `pyproject.toml` no longer contains `ignore_errors = true`.
  - Added narrow strictness pilot override:
    - `[[tool.mypy.overrides]]`
    - `module = "src.retrieval.topic_classifier"`
    - `disallow_untyped_defs = true`
- Current test evidence:
  - `uv run mypy src/retrieval/topic_classifier.py src/ingestion/unified/qdrant_writer.py --ignore-missing-imports --no-error-summary` passes.
  - `uv run pytest tests/unit/retrieval/test_topic_classifier.py -q` passes.
- GitHub state evidence:
  - OPEN with re-baseline comment: https://github.com/yastman/rag/issues/858#issuecomment-4067553370
- Verdict: patch

## #728
- Issue claim: SDK migration closure still required.
- Current code evidence:
  - `gh pr view 972` confirms MERGED at `2026-03-16T11:22:55Z`.
  - Added status note in `docs/plans/2026-03-15-sdk-canonical-remediation-plan.md`.
- Current test evidence:
  - Reconciliation completed via PR + issue state verification.
- GitHub state evidence:
  - CLOSED - https://github.com/yastman/rag/issues/728
- Verdict: close

## #956
- Issue claim: retrieval quality upgrades (short-query handling, policy shaping, tail-cut).
- Current code evidence:
  - Added retrieval-quality fixture:
    `tests/fixtures/retrieval/retrieval_quality_cases.yaml`.
  - Added deterministic short finance-query expansion in
    `telegram_bot/services/query_preprocessor.py` + `_rewrite_query(...)`.
  - Added topic/doc-type-aware retrieval shaping for short finance queries in
    `_hybrid_retrieve(...)`.
  - Added post-rerank weak-tail trimming guard in `_rerank(...)`.
- Current test evidence:
  - Added/updated regression tests in:
    `tests/unit/retrieval/test_topic_classifier.py` and
    `tests/unit/agents/test_rag_pipeline.py`.
- GitHub state evidence:
  - CLOSED - https://github.com/yastman/rag/issues/956
- Verdict: close

## Command Evidence

```bash
rg -n "_stream_agent_to_draft|ingest-services|index_services|test_grade|test_rerank|test_rewrite" \
  telegram_bot scripts Makefile tests -S
```

Selected lines:
- `Makefile:822:ingest-services: ## Index curated services.yaml content into Qdrant`
- `Makefile:824: ... uv run python scripts/index_services.py`
- `telegram_bot/bot.py:90:async def _stream_agent_to_draft(`
- `telegram_bot/bot.py:3606:                    return await _stream_agent_to_draft(`
- `scripts/index_services.py:55:def index_services(`
- `tests/unit/test_agent_streaming.py:3:Tests for _stream_agent_to_draft helper ...`
- `tests/unit/test_index_services.py:1:"""Tests for scripts/index_services.py."""`
- `tests/unit/graph/nodes/test_rerank.py:88:    async def test_rerank_cache_hit_propagated(self):`
- `tests/unit/graph/nodes/test_rewrite.py:36:    async def test_rewrites_query(self):`
- `tests/unit/graph/nodes/test_grade.py:248:    async def test_grade_confidence_equals_top_score(self):`

```bash
for n in 978 981 855 857 858 728 952 956 901; do gh issue view "$n" --json number,title,state,url; done
```

Result snapshot:
- #978 CLOSED https://github.com/yastman/rag/issues/978
- #981 CLOSED https://github.com/yastman/rag/issues/981
- #855 CLOSED https://github.com/yastman/rag/issues/855
- #857 CLOSED https://github.com/yastman/rag/issues/857
- #858 OPEN https://github.com/yastman/rag/issues/858
- #728 CLOSED https://github.com/yastman/rag/issues/728
- #952 CLOSED https://github.com/yastman/rag/issues/952
- #956 CLOSED https://github.com/yastman/rag/issues/956
- #901 CLOSED https://github.com/yastman/rag/issues/901

## Final Verification Matrix

- `make check`: PASS
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`: PASS (`5330 passed, 20 skipped`)
- `uv run bandit -r src/ telegram_bot/ -c pyproject.toml`: only 3 low B311 findings in untouched
  `telegram_bot/graph/nodes/classify.py`
- `uv run vulture telegram_bot/dialogs telegram_bot/services/vectorizers.py telegram_bot/services/generate_response.py telegram_bot/services/draft_streamer.py --min-confidence 80`: PASS
