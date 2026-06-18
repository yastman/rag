# 5-Minute Product Demo

Run the core product path end-to-end in under 5 minutes.

## Prerequisites

- Docker with Compose support
- Python 3.12+ and [`uv`](https://docs.astral.sh/uv/)
- `.env` copied and filled:

```bash
cp .env.example .env
# Fill MOCK_LLM=true (or LLM_MODEL + LLM_API_KEY for a real provider)
```

## Steps

**1. Start core services** (~1 min, one-time pull)

```bash
make core-min-up   # starts Qdrant + Redis only
```

**2. Run the E2E golden path** (~2–3 min)

```bash
make e2e-core-live
```

That's it. The command indexes the synthetic fixture corpus, runs the full
assistant pipeline against it, and exits with a pass/fail result.

## Expected Output

```
Running simplification core live E2E golden path...
PASSED tests/e2e/core/... [classification, retrieval, generation, HITL-mock]
✓ Simplification core live E2E complete
```

All tests run with a mock LLM by default — no API key or external calls needed.

## What It Proves

| Behaviour | Verified by |
|---|---|
| Intent classification routes correctly | E2E classifier assertions |
| RAG retrieval returns grounded results | Qdrant query + scoring checks |
| Generation falls back gracefully | Mock LLM fallback path |
| CRM/HITL mock confirms before write | HITL guard assertions |
| No Telegram, Langfuse, or voice required | Test runs without those services |

## Next Steps

- Real LLM: `make e2e-core-live-real-llm` (needs `LLM_MODEL` + `LLM_API_KEY`)
- Full bot stack: `make docker-bot-up`
- Understand the pipeline: [`docs/PIPELINE_OVERVIEW.md`](../PIPELINE_OVERVIEW.md)
- Safe reviewer path: [`docs/review/ACCESS_FOR_REVIEWERS.md`](../review/ACCESS_FOR_REVIEWERS.md)
