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
  - OPEN - https://github.com/yastman/rag/issues/952
- Verdict: close

## #901
- Issue claim: index `services.yaml` into Qdrant and wire command entrypoint.
- Current code evidence:
  - `scripts/index_services.py` includes `index_services(...)`.
  - `Makefile:822` defines `ingest-services`.
  - `Makefile:824` executes `uv run python scripts/index_services.py`.
- Current test evidence:
  - `tests/unit/test_index_services.py` has direct unit coverage for writer contract and idempotency.
- GitHub state evidence:
  - OPEN - https://github.com/yastman/rag/issues/901
- Verdict: close

## #855
- Issue claim: missing unit tests for grade/rerank/rewrite nodes.
- Current code evidence:
  - Direct node-level tests exist in `tests/unit/graph/nodes/test_grade.py`,
    `tests/unit/graph/nodes/test_rerank.py`, `tests/unit/graph/nodes/test_rewrite.py`.
- Current test evidence:
  - `rg` output confirms dedicated files and test functions are present.
- GitHub state evidence:
  - OPEN - https://github.com/yastman/rag/issues/855
- Verdict: close

## #857
- Issue claim: missing dedicated coverage for search/manager/dialog/ingestion/voice modules.
- Current code evidence:
  - Dedicated test files are present for named surfaces (to validate in Task 6 run).
- Current test evidence:
  - Targeted suite pending execution in Task 6.
- GitHub state evidence:
  - OPEN - https://github.com/yastman/rag/issues/857
- Verdict: patch

## #978
- Issue claim: pre-main audit findings need fresh proof on current `dev`.
- Current code evidence:
  - Audit report exists: `docs/plans/2026-03-16-pre-pr-pre-main-audit-report.md`.
- Current test evidence:
  - Fresh verification rerun pending in Task 7.
- GitHub state evidence:
  - OPEN - https://github.com/yastman/rag/issues/978
- Verdict: patch

## #981
- Issue claim: remaining Bandit/Vulture findings after audit.
- Current code evidence:
  - Residual findings are tracked in issue and covered by Tasks 8-10.
- Current test evidence:
  - Regression tests to be added/executed in Tasks 8-10.
- GitHub state evidence:
  - OPEN - https://github.com/yastman/rag/issues/981
- Verdict: patch

## #858
- Issue claim: `ignore_errors=true` masks mypy in core modules.
- Current code evidence:
  - Current `pyproject.toml` no longer matches old issue wording; strictness work remains.
- Current test evidence:
  - Narrow mypy pilot and tests are planned in Task 11.
- GitHub state evidence:
  - OPEN - https://github.com/yastman/rag/issues/858
- Verdict: split

## #728
- Issue claim: SDK migration closure still required.
- Current code evidence:
  - Plan states PR #972 already merged into `dev`; remaining work is reconciliation.
- Current test evidence:
  - Doc/PR reconciliation pending in Task 12.
- GitHub state evidence:
  - OPEN - https://github.com/yastman/rag/issues/728
- Verdict: close

## #956
- Issue claim: retrieval quality upgrades (short-query handling, policy shaping, tail-cut).
- Current code evidence:
  - No equivalent completed implementation identified in this initial reconciliation pass.
- Current test evidence:
  - New fixture and TDD tasks planned in Tasks 13-16.
- GitHub state evidence:
  - OPEN - https://github.com/yastman/rag/issues/956
- Verdict: patch

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
- #978 OPEN https://github.com/yastman/rag/issues/978
- #981 OPEN https://github.com/yastman/rag/issues/981
- #855 OPEN https://github.com/yastman/rag/issues/855
- #857 OPEN https://github.com/yastman/rag/issues/857
- #858 OPEN https://github.com/yastman/rag/issues/858
- #728 OPEN https://github.com/yastman/rag/issues/728
- #952 OPEN https://github.com/yastman/rag/issues/952
- #956 OPEN https://github.com/yastman/rag/issues/956
- #901 OPEN https://github.com/yastman/rag/issues/901
