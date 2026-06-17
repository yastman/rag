# Bugsink: self-hosted Sentry-compatible backend

Operator and integrator guide for the project's preferred Sentry-compatible
error tracking backend. Bugsink speaks the Sentry protocol, so the same
`sentry-sdk` configuration powers both Bugsink (self-hosted, default) and
Sentry Cloud (alternative, drop-in compatible).

> **Status:** documentation reference for issue
> [#2063](https://github.com/yastman/rag/issues/2063). Initialization helper is
> tracked separately in [#2060](https://github.com/yastman/rag/issues/2060)
> under the umbrella issue [#1417](https://github.com/yastman/rag/issues/1417).

## Why a Sentry-compatible backend

The project already has Langfuse for LLM/RAG traces and Prometheus for runtime
metrics. Neither groups Python stack traces or exposes alertable error
release/environment context. Sentry's wire protocol is the de-facto standard
for grouped Python exception tracking, and Bugsink implements that protocol
without requiring the full Grafana/Loki/Prometheus stack.

The bot must keep working when the backend is unreachable: `sentry-sdk` is
optional at runtime and silently no-ops when `SENTRY_DSN` is unset.

## Backend choice

| Backend | When to pick | Notes |
|---|---|---|
| **Bugsink (self-hosted)** | Default for production and staging | Single Docker image. Same DSN format as Sentry. |
| Sentry Cloud | Hosted alternative if self-hosting is not viable | Same SDK, same DSN format. Quotas billed by Sentry. |
| Sentry self-hosted (full) | Not recommended for this project | Heavy operational footprint (Kafka, ClickHouse, multiple workers). |

The application code never depends on a specific backend beyond Sentry SDK
compatibility. Switching between Bugsink and Sentry Cloud is purely an env
change.

## DSN format

Sentry-compatible DSN, identical for Bugsink and Sentry Cloud:

```text
https://<public_key>@<host>[:<port>]/<project_id>
```

Examples:

```text
# Bugsink, self-hosted on the local network
https://abc123def456@bugsink.example.internal/1

# Bugsink, self-hosted on a non-standard port
https://abc123def456@bugsink.example.internal:8443/1

# Sentry Cloud (the SaaS-issued DSN can be used as-is)
https://abc123def456@o0.ingest.sentry.io/0
```

The DSN is the only secret required for ingestion. Treat it the same as any
other backend secret: store in `.env` (gitignored), in CI / deploy secrets, or
in your secrets manager. Never commit a real DSN to the repository.

## Environment variables

The runtime helper reads a small set of variables. All except `SENTRY_DSN` are
optional.

| Variable | Required | Purpose |
|---|---|---|
| `SENTRY_DSN` | No (but required to enable error tracking) | Sentry-compatible DSN. When unset, error tracking is disabled and the bot logs a single info-level skip line at startup. |
| `SENTRY_ENVIRONMENT` | No | `production` / `staging` / `dev` / `test`. Defaults to `local` when unset. |
| `SENTRY_RELEASE` | No | Semver or git-sha release marker. The helper falls back to the package version when unset. |
| `SENTRY_TRACES_SAMPLE_RATE` | No | Float in `[0.0, 1.0]`. Defaults to `0.0` (errors only, no performance traces). |
| `SENTRY_DEBUG` | No | `1` to enable verbose SDK debug logging. Off by default. |

PII scrubbing is enforced in code (`send_default_pii=False` plus a project
`before_send` hook that runs `PIIRedactor.mask` over event payloads). It is
not configurable via env on purpose — see
[`docs/RAG_QUALITY_SCORES.md`](../RAG_QUALITY_SCORES.md) and the umbrella
issue for the safety contract.

## Local / test setup

Docker Compose snippet for a local Bugsink instance. Pin the digest in your
own deploy; the tag below is illustrative.

```yaml
# compose.observability.yml (illustrative — do not commit a real DSN)
services:
  bugsink:
    image: bugsink/bugsink:latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      SECRET_KEY: ${BUGSINK_SECRET_KEY:?set in .env}
      BEHIND_HTTPS_PROXY: "false"
      CREATE_SUPERUSER: "${BUGSINK_ADMIN_USER:-admin}:${BUGSINK_ADMIN_PASSWORD:?set in .env}"
    volumes:
      - bugsink-data:/data
volumes:
  bugsink-data:
```

Then point the bot at it via `.env`:

```bash
# Local dev only — never commit
SENTRY_DSN=https://<public_key>@127.0.0.1:8000/1
SENTRY_ENVIRONMENT=local
SENTRY_TRACES_SAMPLE_RATE=0.0
```

Smoke check (after the helper from #2060 lands):

```bash
uv run python - <<'PY'
import sentry_sdk
from src.observability_sentry import initialize_sentry

initialize_sentry()
sentry_sdk.capture_message("bugsink-smoke-check")
sentry_sdk.flush(timeout=2)
PY
```

The message should appear in the Bugsink UI grouped under the configured
project. Until #2060 ships, you can validate the DSN with a raw
`sentry_sdk.init(dsn=os.environ["SENTRY_DSN"])` call followed by
`capture_message`, but **do not** rely on raw init in production code paths.

## Production safety

* **No DSN, no problem.** The init helper short-circuits when `SENTRY_DSN` is
  unset, so the bot starts cleanly without a backend.
* **PII scrubbing is mandatory.** `send_default_pii=False` is hard-coded in
  the helper and is reinforced by a `before_send` hook that masks Telegram
  user IDs, phone numbers, emails, Ukrainian passport / РНОКПП IDs, and any
  long free-text payloads via the project `PIIRedactor`. CRM payloads,
  Telegram bot tokens, LiteLLM keys, and Langfuse keys are denylisted from
  Sentry's `EventScrubber`. Do not bypass this with custom `set_extra` calls.
* **Bounded traffic.** Default `traces_sample_rate=0.0` keeps Sentry to error
  events only. Raise to a small fraction (e.g. `0.05`) only after confirming
  Bugsink storage and bandwidth headroom.
* **Release / environment tagging.** Always set `SENTRY_RELEASE` from CI to
  the deployed git SHA or semver. This is what makes Bugsink's grouping and
  regression detection useful.
* **Network isolation.** Bugsink should be reachable only from the bot's
  network egress. Do not expose the ingestion port publicly without
  authentication or rate limiting.
* **Backups.** Bugsink stores events on disk (default SQLite, optional
  Postgres). Snapshot the data volume at the cadence required by your
  incident-investigation policy. There is no analytics value in long
  retention beyond that policy.

## Switching to Sentry Cloud

To swap Bugsink for Sentry Cloud, set `SENTRY_DSN` to the SaaS DSN issued by
Sentry. No code change is required. Per-environment DSNs (one per Sentry
project) are recommended so events from staging do not bleed into production.

## Cross-references

* Umbrella: [#1417 — Sentry-compatible error tracking with Bugsink backend](https://github.com/yastman/rag/issues/1417)
* SDK helper: [#2060 — `sentry-sdk` initialization](https://github.com/yastman/rag/issues/2060)
* Runtime tags / trace context: [#2061](https://github.com/yastman/rag/issues/2061)
* Breadcrumbs: [#2062](https://github.com/yastman/rag/issues/2062)
* End-to-end verification: [#2064](https://github.com/yastman/rag/issues/2064)
* PII redaction utility: [`src/security/pii_redaction.py`](../../src/security/pii_redaction.py)
* Existing observability runbooks: [`docs/runbooks/README.md`](../runbooks/README.md)
