# ADR-0008: Superseded — structured output uses LiteLLM SDK JSON schema

Status: Superseded by #2429 / #2481.

## Context

This ADR previously recorded a decision around an extra structured-output SDK
and deferred streaming helpers. The active runtime no longer uses that SDK for
query analysis, apartment extraction, or generated evaluation queries.

## Current decision

Structured output call sites must use the canonical runtime client:

```python
from src.runtime.llm import create_litellm_chat_client

client = create_litellm_chat_client(model="gpt-4o-mini")
result = await client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[...],
    response_model=MyPydanticModel,
)
```

`src/runtime/llm/router.py` translates `response_model` into an
OpenAI-compatible JSON-schema `response_format`, calls LiteLLM in-process, and
parses the returned JSON into the requested Pydantic model.

## Consequences

- Active runtime paths have one LLM/structured-output path: `src.runtime.llm`.
- Additional structured-output SDKs are not part of the active dependency set.
- Regression coverage lives in `tests/unit/test_litellm_sdk_router.py` and
  `tests/unit/services/test_instructor_sdk_contract.py`.
