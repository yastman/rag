***REMOVED*** ADR-0007: Custom HyDEGenerator Retained (No LangChain-Native Replacement)

**Status:** Accepted

**Date:** 2026-05-20

**Issue:** ***REMOVED***1652

***REMOVED******REMOVED*** Context

PR ***REMOVED***1622 proposed replacing the custom `HyDEGenerator` (in `telegram_bot/services/query_preprocessor.py`) with LangChain's `HypotheticalDocumentEmbedder`. This ADR documents the SDK research that proves no viable LangChain 1.2-native replacement exists in the pinned dependency set.

***REMOVED******REMOVED******REMOVED*** Pinned Environment (from `uv.lock`)

| Package | Version | Role |
|---------|---------|------|
| `langchain` | 1.2.15 | New slim orchestration package |
| `langchain-core` | 1.2.31 | Core abstractions (Embeddings, Runnables) |
| `langchain-openai` | 1.1.9 | OpenAI LLM/Embeddings wrappers |
| `langchain-classic` | 1.0.1 | Legacy chains (transitive via langchain-community) |
| `langchain-community` | 0.4.1 | Community integrations (not a direct dependency) |

***REMOVED******REMOVED******REMOVED*** Key Finding: LangChain 1.2 Restructuring

`langchain==1.2.15` is a completely restructured package containing only:
- `agents/` (factory, middleware, structured_output)
- `chat_models/` (base)
- `embeddings/` (init_embeddings helper)
- `messages/`, `rate_limiters/`, `tools/`

**There is no `langchain.chains` module.** All chain implementations (including HyDE) were moved to `langchain-classic`, which is a legacy compatibility package.

***REMOVED******REMOVED******REMOVED*** Verification Evidence

```python
***REMOVED*** langchain 1.2.15 has no chains module
>>> import importlib.util
>>> importlib.util.find_spec("langchain.chains.hyde.base")
ModuleNotFoundError: No module named 'langchain.chains'

***REMOVED*** HypotheticalDocumentEmbedder exists only in langchain-classic
>>> from langchain_classic.chains.hyde.base import HypotheticalDocumentEmbedder
***REMOVED*** (works, but langchain-classic is not a direct dependency)
```

***REMOVED******REMOVED*** Decision

**Keep the custom `HyDEGenerator`** in `telegram_bot/services/query_preprocessor.py`. The `custom_justified` decision is based on six incompatibilities:

***REMOVED******REMOVED******REMOVED*** 1. Wrong Package Location

`HypotheticalDocumentEmbedder` lives in `langchain-classic==1.0.1`, which is:
- A legacy compatibility package, not recommended for new code
- Only transitively installed via `langchain-community` (not a direct dependency)
- Adding it as a direct dependency increases maintenance burden for a deprecated package

***REMOVED******REMOVED******REMOVED*** 2. Fundamentally Different Contract

| Aspect | Custom HyDEGenerator | HypotheticalDocumentEmbedder |
|--------|---------------------|------------------------------|
| Returns | Hypothetical document **text** | **Embedding vectors** |
| Purpose | Text generation for separate embedding | Combined generate + embed |
| Interface | `generate_hypothetical_document(query) -> str` | `embed_query(text) -> list[float]` |

The project embeds the hypothetical text separately (via Voyage AI). `HypotheticalDocumentEmbedder` merges generation and embedding into one step, which breaks the pipeline architecture.

***REMOVED******REMOVED******REMOVED*** 3. No True Async Support

`HypotheticalDocumentEmbedder.aembed_query()` simply wraps the sync `embed_query()` in `run_in_executor()`. The custom implementation is natively async using `AsyncOpenAI`.

***REMOVED******REMOVED******REMOVED*** 4. Cannot Integrate with LiteLLM Proxy

The custom generator uses `AsyncOpenAI(base_url="http://localhost:4000")` to route through the LiteLLM proxy. `HypotheticalDocumentEmbedder` requires a LangChain `BaseLanguageModel`, which does not support arbitrary `base_url` routing through LiteLLM without additional adapter code.

***REMOVED******REMOVED******REMOVED*** 5. Cannot Integrate with Langfuse Observability

The custom generator uses:
- `langfuse.openai.AsyncOpenAI` for automatic trace capture
- `@observe()` decorator for span nesting
- `update_current_span()` for curated metadata
- `langfuse_prompt` linking for prompt versioning

`HypotheticalDocumentEmbedder` uses LangChain callbacks, which are incompatible with the project's Langfuse v4 native integration.

***REMOVED******REMOVED******REMOVED*** 6. Cannot Use Dynamic Prompt Loading

The custom generator calls `get_prompt_with_object("hyde", fallback=...)` to load prompts dynamically from Langfuse Prompt Management. `HypotheticalDocumentEmbedder.from_llm()` only accepts static `BasePromptTemplate` objects or predefined keys (`web_search`, `sci_fact`, `arguana`, etc.), none of which match the project's Russian-language real estate domain.

***REMOVED******REMOVED*** Consequences

***REMOVED******REMOVED******REMOVED*** Positive
- No dependency on deprecated `langchain-classic` package
- Full async-native performance (no executor thread overhead)
- Full Langfuse observability (auto-tracing, prompt versioning, span metadata)
- Clean LiteLLM proxy routing (model/key abstraction)
- Dynamic prompt management via Langfuse

***REMOVED******REMOVED******REMOVED*** Negative
- ~80 lines of custom code to maintain
- Must track LangChain ecosystem for future native HyDE support

***REMOVED******REMOVED******REMOVED*** Future Considerations
- If LangChain 2.x introduces a native async HyDE primitive that accepts arbitrary LLM callables, revisit this decision
- The custom implementation is intentionally thin (single async method + error handling) and low-maintenance
- Unit tests exist and pass: `tests/unit/test_query_preprocessor.py` (39 tests)

***REMOVED******REMOVED*** Verification

```bash
***REMOVED*** Confirms langchain.chains.hyde is NOT importable
uv run python -c "import importlib.util; print(importlib.util.find_spec('langchain.chains.hyde.base'))"
***REMOVED*** Output: ModuleNotFoundError: No module named 'langchain.chains'

***REMOVED*** Existing tests pass
uv run pytest tests/unit/test_query_preprocessor.py -q
***REMOVED*** Output: 39 passed
```
