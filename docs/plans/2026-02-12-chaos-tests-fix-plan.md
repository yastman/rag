# Fix Chaos LLM Fallback Tests (Issue #164)

## Problem
All 16 async chaos tests in `tests/chaos/test_llm_fallback.py` fail with `TypeError`:
```
LLMService.__init__() got an unexpected keyword argument 'client'
```

Tests were written for an old API where `LLMService` accepted `client=httpx.AsyncClient`.
Current `LLMService.__init__(self, api_key, base_url, model, low_confidence_threshold)` creates
its own `AsyncOpenAI` client internally.

3 sync tests in `TestLowConfidenceFallback` pass (don't use HTTP client).

## Root Cause
Tests inject `httpx.AsyncClient` via `client=` kwarg which doesn't exist in current API.

## Fix (single task)

1. Add `pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)` — needed because
   OpenAI SDK has `max_retries=2` which may re-send matched requests
2. Remove all `async with httpx.AsyncClient() as client:` blocks
3. Change `LLMService(api_key="test-key", client=client)` → `LLMService(api_key="test-key")`
4. Dedent code that was inside `async with` blocks
5. Run ruff check + format
6. Run pytest and verify all 19 tests pass

## Reference
PR #180 on `fix/164-chaos-llm-api` branch has same fix but CI lint fails.
