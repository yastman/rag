# Local Observability Diagnostic Runbook (#2199)

Classifies the four noise patterns currently degrading local Langfuse and
LiteLLM observability and links each to its remediation. Use the diagnostic
probe to collect evidence, then act on the matching section.

## Probe

```bash
uv run python -m scripts.probe.observability_diagnostic
```

Tails recent logs from `langfuse-worker`, `langfuse-web`, `litellm`, and
`bot`, classifies each line, and prints a summary like:

```text
Observability diagnostic summary (#2199):
  langfuse_queue_timeout      80
  litellm_auth_noise          0
  langfuse_prompt_miss        0
  metrics_port_conflict       0
  healthy                     0
  unknown                     320
```

The probe exits non-zero when `langfuse_queue_timeout` exceeds
`QUEUE_TIMEOUT_NOISE_THRESHOLD` (currently 3) so it can gate CI dashboards.

For deterministic input use:

```bash
docker compose logs --no-color --tail 200 langfuse-worker > /tmp/lf.log
uv run python -m scripts.probe.observability_diagnostic --from-file /tmp/lf.log
```

## Categories

### langfuse_queue_timeout

Match: `Socket timeout` (ioredis emits `Error: Socket timeout. Expecting data, but didn't receive any in 30000ms.`).

Affects queues: `data-retention`, `evaluation-execution`, `batch-action`,
`secondary-ingestion`, `trace-delete`, `secondary-otel-ingestion`, `webhook`.

Likely causes (in order of likelihood for the local audit profile):

1. The Langfuse worker is talking to a different Redis than the one
   `make bot` uses. Local stack publishes Redis on `127.0.0.1:6379`;
   the worker should target the in-network alias `redis-langfuse:6379`
   (Langfuse owns its own Redis to keep traces independent from bot
   cache traffic).
2. `redis-langfuse` is healthy on RDB writes but has high latency under
   the local `dev` project load.
3. A stale legacy `langfuse-worker` container survives the canonical
   compose graph (see #2195: stray `/tmp/compose.*.yml` overrides).

Remediation:

```bash
# Confirm worker is attached to the canonical compose project.
docker inspect dev-langfuse-worker-1 \
  --format '{{ index .Config.Labels "com.docker.compose.project.config_files"}}'

# Should print only paths under your main checkout. If it includes a
# worktree path or /tmp, run docs/runbooks/COMPOSE_SOURCE_CLEANUP.md.

# Confirm the worker's Redis URL points at redis-langfuse, not redis.
docker compose exec langfuse-worker env | grep -E '(REDIS|LANGFUSE_REDIS)'

# Restart the worker after fixing env or recreating the project.
docker compose --profile ml restart langfuse-worker
```

### litellm_auth_noise

Match: `No api key passed in.` or `"GET /models" 401`.

Cause: anonymous probes from monitoring/tooling hit `/v1/models` without
the master key, and LiteLLM logs the rejection at WARNING. The bot uses
the same proxy with `LITELLM_MASTER_KEY` and is unaffected.

Remediation: either pass the master key from the probe source or filter
the log line at the LiteLLM proxy. A reproducible diagnostic call is:

```bash
curl -fsS \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  http://localhost:4000/v1/models | jq '.data | length'
```

If the bot succeeds and the only 401s come from a known prober, this
category is informational and can stay in the noise summary.

### langfuse_prompt_miss

Match: `Langfuse prompt ... not found ... fallback`.

Cause: prompts referenced by the runtime are not seeded into the local
Langfuse project. The bot's prompt-management layer falls back to
inline defaults, so query behavior is unaffected — this is expected
"dev state" until the operator runs the prompt seed.

Remediation: seed the prompts (see `scripts/setup_langfuse_dashboards.py`
and the Langfuse SDK docs) or accept the fallback. The probe surfaces
this category so prompt drift is not silently ignored.

### metrics_port_conflict

Match: `Cannot bind Prometheus metrics server` + `Address already in use`.

Tracked separately in #2190 (resolved by moving the bot metrics default
from 9091 to 9092). The probe still classifies the line so historical
log scans surface the conflict in evidence collection.

### unknown

Anything not matched. A high `unknown` count is normal — most lines are
routine HTTP access logs and progress messages. Investigate `unknown`
only when total volume changes sharply.

## Acceptance evidence template

When closing the loop on #2199, attach a probe summary captured before
and after the remediation:

```text
Before: langfuse_queue_timeout = N (degraded)
After:  langfuse_queue_timeout = 0 over a 5-minute log window
Steps:  <numbered list of actions taken>
```

## Related

- Bot metrics port conflict: #2190
- Compose source drift: #2195
- Trace verification gate: #2179
- Pinned by `tests/unit/scripts/test_observability_diagnostic.py`.
