# Compose Source Cleanup Runbook (#2195)

Local Docker validation is only meaningful when the `dev` Compose project
references a single, canonical checkout. When `docker compose ls` shows
mixed `ConfigFiles` from multiple worktrees plus stray `/tmp/compose.*.yml`
overrides, container state diverges from what the main `compose.yml` and
`compose.dev.yml` actually describe — port bindings, env files, and image
digests stop matching the source of truth.

This runbook recreates the `dev` project from canonical sources without
deleting persistent volumes (Postgres, Redis, Qdrant, Langfuse data).

## Symptoms

- `docker compose ls --format json` lists more than two entries under
  `ConfigFiles` for the `dev` project, or any entry under `/tmp`.
- Container labels (`com.docker.compose.project.config_files`) reference
  worktree paths like `/home/user/projects/rag-fresh-*/compose.yml`.
- `make bot` works through workarounds while `docker compose ps` shows
  containers that the canonical compose graph does not declare.
- `bge-m3-tmp` or other manually-created containers exist outside the
  Compose lifecycle.
- The contract test
  `tests/contract/test_compose_source_cleanup_contract.py` reports
  stray `/tmp` sources or multiple checkout roots.

## Diagnosis

```bash
# 1. List all Compose projects on the host.
docker compose ls --all --format json | jq

# 2. Inspect the dev project's effective config files.
docker compose ls --all --format json \
  | jq -r '.[] | select(.Name=="dev") | .ConfigFiles'

# 3. Audit container labels for stale worktree references.
docker ps --format '{{.Names}}\t{{.Label "com.docker.compose.project.config_files"}}\t{{.Label "com.docker.compose.project.environment_file"}}' \
  | grep -E 'rag-fresh|/tmp/compose' || echo "clean"
```

## Cleanup (no volume loss)

The cleanup brings down the project containers but keeps named volumes,
so persistent data survives.

```bash
# 0. Move to the canonical checkout — stop everything else first.
cd /home/user/projects/rag-fresh

# 1. Stop the dev project from EVERY checkout that may have started it.
#    This is the part that allows mixed config_files to accumulate; we
#    have to ask each known checkout to stop its containers, otherwise
#    Compose will keep re-attaching them.
for d in /home/user/projects/rag-fresh*; do
  if [ -f "$d/compose.yml" ]; then
    echo "[stopping from $d]"
    (cd "$d" && docker compose -p dev down --remove-orphans) || true
  fi
done

# 2. Remove the stray temp override and any other /tmp/compose.*.yml.
rm -f /tmp/compose.postgres-root.yml /tmp/compose.*.yml

# 3. Sweep manually-created containers that are not part of the canonical
#    compose graph. Review the list before running the rm command.
docker ps -a --filter 'name=bge-m3-tmp' --filter 'name=^/dev-.*-legacy$' \
  --format '{{.Names}}'
# After review:
docker ps -a --filter 'name=bge-m3-tmp' --format '{{.Names}}' \
  | xargs -r docker rm -f

# 4. Recreate the project from canonical sources only.
docker compose --env-file .env \
  -f compose.yml -f compose.dev.yml \
  --profile full \
  up -d
```

## Verification

```bash
# Single checkout, no /tmp overrides:
docker compose ls --all --format json \
  | jq -r '.[] | select(.Name=="dev") | .ConfigFiles' \
  | tr ',' '\n' \
  | grep -v '^/home/user/projects/rag-fresh/' && echo "DRIFT" || echo "OK"

# Image digests and port bindings match docker compose config:
docker compose --env-file .env \
  -f compose.yml -f compose.dev.yml --profile full ps -a

# Contract test:
uv run --python 3.12 pytest tests/contract/test_compose_source_cleanup_contract.py -q
```

The contract test skips when Docker is unavailable or the `dev` project
is not running, so it is safe in CI; locally it surfaces drift.

## BGE-M3 Closure Check

For BGE-M3 endpoint regressions such as #2182 and #2188, do not close the
issue only because the Compose file declares the right port. Close it after the
running local stack proves the canonical endpoint and startup path.

```bash
# Canonical project source only:
docker compose ls --format json

# Canonical BGE-M3 endpoint is healthy:
curl -fsS http://localhost:8000/health

# No port-8888 workaround:
grep '^BGE_M3_URL=' .env

# The canonical Compose container publishes host port 8000:
docker inspect dev-bge-m3-1 --format '{{json .NetworkSettings.Ports}}'

# Runtime drift and bot startup guards:
make verify-compose-runtime
make test-bot-health
PREFLIGHT_BOT_FLAGS="--env-file /home/user/projects/rag-fresh/.env" make preflight-bot
make bot
```

Expected evidence:

- `curl` returns `status=ok`, `model_loaded=true`, and `warmed_up=true`.
- `BGE_M3_URL` points to `http://localhost:8000`, not a temporary port such as
  `8888`.
- `dev-bge-m3-1` publishes `127.0.0.1:8000->8000/tcp`.
- `make verify-compose-runtime` reports zero image drift and zero port drift.
- `make bot` reaches polling with `bge_m3 [CRITICAL]` passing. A degraded
  optional Langfuse check is not the BGE-M3 root cause; track it separately.

## Volume safety

`docker compose down` (without `-v`) leaves named volumes intact. Persistent
data lives in the volumes declared at the bottom of `compose.yml` —
`postgres_data`, `qdrant_data`, `redis_data`, `langfuse_clickhouse_data`,
`langfuse_minio_data`, etc. Do **not** add `-v` to the `down` invocations
above unless you have an external backup.

## Related

- Broad Docker audit: #2185
- BGE temp endpoint vs canonical service: #2188
- Bot response smoke gate: #2192
- Smoke-zoo redis-cli host-independence: #2196
- Pinned by `tests/contract/test_compose_source_cleanup_contract.py`.
