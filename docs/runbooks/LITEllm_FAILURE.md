# Runbook: LiteLLM SDK Router and Provider Failure

- **Owner:** LLM runtime / On-call
- **Last verified:** 2026-06-12
- **Verification command:** `uv run python scripts/probe/check_bot_runtime_env.py`

Use this runbook when LiteLLM provider routing has outages or LLM calls are failing.
The bot uses the in-process SDK router in `src/runtime/llm/router.py`; there is
no separate local gateway container in the default runtime.

## Symptoms

- `LLM_TIMEOUT` errors in logs
- `Model not found` (404) errors
- Extremely high latency on all LLM calls
- No responses from bot despite successful retrieval
- Traces show `LLM failed: Connection error` while Langfuse ingestion appears healthy

## Diagnosis

### 1. Verify runtime environment

```bash
uv run python scripts/probe/check_bot_runtime_env.py
```

The check should confirm at least one provider key is configured:

- `CEREBRAS_API_KEY`
- `GROQ_API_KEY`
- `OPENAI_API_KEY`
- `LLM_API_KEY` (legacy OpenAI-compatible fallback)

### 2. Verify SDK-router aliases

```bash
uv run python - <<'PY'
from src.runtime.llm.router import build_model_list
for entry in build_model_list():
    print(entry["model_name"], "->", entry["litellm_params"]["model"])
PY
```

Expected state: the bot sends requests to the canonical alias `gpt-4o-mini`,
with fallback entries owned by `src/runtime/llm/router.py`.

### 3. Check bot logs for LLM errors

```bash
docker compose logs telegram-bot --tail=200 | grep -Ei 'llm|litellm|openai|cerebras|groq|timeout|rate'
```

Classify the error:

| Error | Likely cause | Action |
|---|---|---|
| `AuthenticationError` / `401` | Missing or invalid provider key | Refresh the relevant provider key secret. |
| `RateLimitError` / `429` | Provider rate limit | Wait, lower traffic, or temporarily switch primary alias in router config. |
| `NotFoundError` / `404` | Alias or upstream model typo | Compare the alias in `src/runtime/llm/router.py` with provider docs. |
| `TimeoutError` | Provider latency or network issue | Check provider status and retry with fallback alias. |

### 4. Run a local SDK-router smoke call

```bash
uv run python - <<'PY'
import asyncio
from src.runtime.llm import create_litellm_chat_client

async def main():
    client = create_litellm_chat_client(model="gpt-4o-mini", timeout=30.0)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Reply with OK"}],
        max_tokens=5,
    )
    print(response.choices[0].message.content)

asyncio.run(main())
PY
```

## Safe recovery

1. Verify secrets are present in the target environment.
2. Restart only the bot process after secret changes:

   ```bash
   docker compose restart telegram-bot
   ```

3. Re-run the runtime env probe and a single SDK-router smoke call.
4. Watch logs for the next user request.

## Escalation

Escalate to the runtime owner if:

- all configured providers return authentication failures after secret refresh;
- the SDK-router alias map no longer includes `gpt-4o-mini`;
- retries produce repeated provider-side 5xx errors across all fallback models.
