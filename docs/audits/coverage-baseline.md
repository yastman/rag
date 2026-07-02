# Coverage Baseline — card_d880b32250dc

**Date:** 2026-07-02
**Gate run:** `make test-core` with `--cov=src/core --cov=src/runtime --cov=telegram_bot --cov-report=term-missing`
**Tests collected/passed:** 126 passed (core gate — `tests/unit/core/`, `tests/unit/runtime/`, `tests/regression/`, two contract files)
**`fail_under=80` status: FAILS** — total coverage is **9.80%**

---

## Why total is so low

The `fail_under=80` threshold in `pyproject.toml` applies to `source = ["src", "telegram_bot"]`.
The core gate does not import `telegram_bot` (it has no `aiogram`/`langchain_core` in this env),
so the entire `telegram_bot` package (~11 000 stmts) is measured as 0% covered.
That drags the combined total down to ~10%.

Running the full `make test-cov` (`pytest tests/`) hits 43 collection errors (missing optional
deps: `langfuse`, `langchain_core`, `groq`, `apscheduler`, `prometheus_client`, `aiogram`, etc.)
and produces no coverage summary at all — exit 2.

---

## Per-package summary (core gate)

| Package | Stmts | Miss | Cover |
|---|---|---|---|
| `src/core` | 144 | 39 | **73%** |
| `src/runtime` | 2 517 | 1 966 | **20%** |
| `telegram_bot` | 12 093 | 12 093+ | **~0%** |
| **TOTAL** | **14 754** | **13 084** | **9.80%** |

---

## Answer-spine files (card DoD targets)

| File | Stmts | Miss | Cover |
|---|---|---|---|
| `src/core/assistant.py` | 27 | 0 | **100%** |
| `src/runtime/pipeline/assistant_pipeline.py` | 78 | 1 | **97%** |
| `src/runtime/pipeline/rag.py` | 132 | 67 | **44%** |
| `src/runtime/generation/service.py` | 94 | 3 | **94%** |
| `telegram_bot/agents/rag_pipeline.py` | 406 | 406 | **0%** |
| `telegram_bot/agents/rag_tool.py` | 89 | 89 | **0%** |
| `telegram_bot/pipelines/client.py` | 179 | 179 | **0%** |

> `telegram_bot/` answer-spine files are 0% because the core gate does not exercise
> the Telegram adapter layer (no `aiogram` installed in the baseline env).

---

## Selected `src/core` detail

| File | Cover |
|---|---|
| `src/core/assistant.py` | 100% |
| `src/core/contracts.py` | 90% |
| `src/core/telemetry.py` | 89% |
| `src/core/__init__.py` | 16% |
| `src/core/app.py` | 0% |

---

## Selected `src/runtime` detail

| File | Cover |
|---|---|
| `src/runtime/generation/service.py` | 94% |
| `src/runtime/generation/setup.py` | 98% |
| `src/runtime/generation/context.py` | 96% |
| `src/runtime/generation/messages.py` | 92% |
| `src/runtime/pipeline/assistant_pipeline.py` | 97% |
| `src/runtime/pipeline/context.py` | 100% |
| `src/runtime/pipeline/rag.py` | 44% |
| `src/runtime/graph/builder.py` | 91% |
| `src/runtime/graph/config.py` | 79% |
| `src/runtime/integrations/cache.py` | 0% |
| `src/runtime/integrations/embeddings.py` | 0% |
| `src/runtime/qdrant/service.py` | 12% |
| `src/runtime/pipeline/_retrieve.py` | 18% |
| `src/runtime/pipeline/_cache_stage.py` | 23% |

---

## Conclusion

- `fail_under=80` **FAILS today** with a combined total of **9.80%**.
- The core spine (`assistant.py` → `assistant_pipeline.py` → `generation/service.py`) is
  well-covered at 94–100%.
- The retrieval internals (`rag.py` 44%, `_retrieve.py` 18%, `qdrant/service.py` 12%) and
  the full `telegram_bot` adapter are the largest gaps.
- Enforcing `fail_under=80` against the full `telegram_bot` source while only running the
  core gate will always fail. The threshold needs to either be scoped to `src/` only, or the
  adapter tests need to be runnable in the same env (requires `aiogram` etc.).
