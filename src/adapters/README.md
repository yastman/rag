# src/adapters/

Application-facing provider adapters for external services. Runtime code depends on these
Protocol-based providers; the low-level SDK clients they wrap stay in
[`../services/`](../services/).

## Subpackages

### `embeddings/`

| Symbol | File | Role |
|--------|------|------|
| `EmbeddingProvider` | [`embeddings/base.py`](./embeddings/base.py) | Provider Protocol |
| `BgeM3EmbeddingProvider` | [`embeddings/bge_m3.py`](./embeddings/bge_m3.py) | BGE-M3 via the self-hosted API |

### `llm/`

| Symbol | File | Role |
|--------|------|------|
| `LLMProvider` | [`llm/base.py`](./llm/base.py) | Provider Protocol + error taxonomy (`LLMError`, `LLMRateLimitError`, `LLMTimeoutError`, `LLMAuthenticationError`) |
| `LiteLlmProvider` | [`llm/litellm_provider.py`](./llm/litellm_provider.py) | LiteLLM-backed provider |

## Boundaries

- Adapters are the **canonical embedding/LLM entrypoint** for runtime retrieval — depend on
  these, not on the raw clients in `src/services/`.
- Error handling is normalised through the `llm/base.py` exception hierarchy.

## See Also

- [`../services/README.md`](../services/README.md) — low-level SDK clients wrapped here
- [`../runtime/README.md`](../runtime/README.md) — the engine that consumes these providers
