# Telegram adapter

`telegram_bot` is the aiogram adapter of one Python modular monolith. It receives
text, voice and callbacks, maps them to application requests, and delivers answers.
Shared retrieval and generation run in the same process through
[`src/core`](../src/core/README.md) and the [runtime](../src/runtime/README.md).
This README is the package navigation entrypoint; [local rules](AGENTS.override.md)
own its engineering boundaries and required checks.

## Composition and lifecycle

[`main.py`](main.py) loads `BotConfig`, configures structured logging, constructs
`PropertyBot`, retries transient startup failures and always calls `stop()` in its
`finally` block. [`bot.py`](bot.py) wires the aiogram dispatcher, middleware and
handlers. [`build_services`](lifecycle/services.py) constructs long-lived clients
and the runtime configuration; Telegram validation stays in [`BotConfig`](config.py).
Dependencies come from the repository's [pyproject.toml](../pyproject.toml) and
[uv.lock](../uv.lock), including the `telegram` extra. There is no separate bot lock.

[`start_bot` and `stop_bot`](lifecycle/lifecycle.py) own startup and teardown:
preflight, cache setup, PostgreSQL bootstrap, dialogs and commands, BGE warmup,
then the mode-dependent polling lock and aiogram polling. Teardown cancels the
heartbeat, releases an owned lock and closes the monitor, clients, database pool
and Telegram session. Module-level imports in `lifecycle/lifecycle.py` stay
stdlib-only; its warmup and heartbeat helpers accept their collaborators directly.
[Preflight](preflight/README.md) owns dependency/readiness checks and remediation;
[PostgreSQL bootstrap](lifecycle/postgres_bootstrap.py) owns database initialization.

## Application boundaries

Handlers and dialogs translate Telegram interactions and render results. Middleware
owns transport concerns such as throttling, errors and locale; it does not own
retrieval or LLM policy. [`pipeline/supervisor.py`](pipeline/supervisor.py) enters
assistant-core behavior and handles Telegram delivery. Runtime retrieval,
generation and prompt decisions belong to the shared runtime, not the transport.

[`ApartmentCatalog`](services/apartment/apartment_catalog.py) is the common search
interface for demo and catalog dialogs: regex-first extraction with optional LLM
gap filling, Qdrant payload filtering, price-ordered pages and cursor continuation
with shown-ID deduplication. Dialogs map those results to UI rather than maintaining
separate search implementations. An unavailable catalog produces an empty page.

Shared cache, embeddings, prompts and polling-lock implementations live in
[`src/runtime/integrations`](../src/runtime/integrations/); the canonical Qdrant
client lives in [`src/runtime/qdrant`](../src/runtime/qdrant/). Shared content and
CRM clients belong to [`src/services`](../src/services/README.md).
[Trace metadata](observability/trace.py) and [session context](observability/context.py)
support structured logging; they do not initialize a tracing backend.
[PII masking](../src/observability/README.md) has a separate shared owner.

Voice input is optional (`VOICE_ENABLED` and the configured STT key in `BotConfig`).
Demo and catalog dialogs share [in-process transcription](services/voice_transcription.py);
unconfigured or failing voice falls back to typed input. No voice sidecar is required.
Markdown ingestion, collection schemas and manifest identity are owned outside this
package: follow [Ingestion](../docs/INGESTION.md), not Telegram handlers, to populate
or change the knowledge corpus.

## Redis modes

[`REDIS_MODE`](../src/runtime/integrations/redis_mode.py) controls connection and
capability behavior. A URL alone does not enable Redis.

| Mode | Runtime behavior |
| --- | --- |
| `disabled` | No Redis client or connection; Redis-backed durable capabilities are disabled. Explicitly enabling a Redis-only feature is a configuration error. |
| `single_instance` | Redis is optional; cache failures become misses/no-store. Durable capabilities report availability separately; no distributed polling lock is required. |
| `multi_instance` | A Redis connection and distributed polling lock are required before polling; lock loss stops polling. |

The reusable-core default is `disabled`; Compose explicitly selects
`single_instance`. Install the root `redis` extra when using Redis-backed features.
The [deployment guide](../DOCKER.md) owns topology and operator environment setup.

## Run and verify

Run commands from the repository root using the Python version and platform setup
in [Local Development](../docs/LOCAL-DEVELOPMENT.md). Configure the operator
runtime environment as described in [Deployment](../DOCKER.md) before starting.

```bash
uv sync --frozen --extra telegram
make bot                    # Foreground runtime; Ctrl+C stops it
make bot-logs-startup        # Startup/preflight diagnostics
make bot-logs-errors         # Errors and tracebacks in logs/bot-run.log
```

For Redis modes, include `--extra redis` in the sync selection. Container setup and
corpus bootstrap procedures stay in the deployment and ingestion guides above.
The [test guide](../tests/README.md) owns lane prerequisites and selectors:

```bash
make check
make test-core
make test
make test-telegram-adapter
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
uv sync --frozen             # Restore the isolated base environment for the gate
make candidate-check
```

Adapter tests and broad unit tests cover different owners; neither replaces the
other. For ownership beyond this package, use [Structure](../docs/architecture/STRUCTURE.md).
