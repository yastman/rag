# Redis 8.6.3 → 8.10.1 upgrade and rollback runbook (#3231)

Server-image-only upgrade. redis-py client, cache key schemas, health checks and
service semantics are unchanged. Apply per environment; keep the old image
references available until the new version has soaked.

## Image pins

| Variant | New (8.10.1) | Old (8.6.3) |
|---|---|---|
| `compose.yml` (dev/prod stack) | `redis:8.10.1@sha256:298e5b3bc566bade82f46ad5511777a4a07a294097ce16ada2f6a42be5239df5` | `redis:8.6.3@sha256:4d25e2fe601f7ffaeb4437cb6ced3518bc36edf34ebe98863c80836943d94529` |
| `compose.core.yml` / `starter/compose.yml` (alpine) | `redis:8.10.1-alpine@sha256:becdda6c7f4b3fb42e42fd7f120bbf5c54c4caaaf16f26da24e4563d2c1f0576` | `redis:8.6.3-alpine@sha256:c25154ff5e2e6d0820a0268abd9dd3bc84f48fddd40396fb1f4de5b3dcc2182a` |

Notes:

- The old debian digest (`redis:8.6.3@sha256:4d25e2fe…`) still resolves on the
  registry; the old **alpine** digest (`sha256:c25154ff…`) no longer resolves
  (registry manifest verification fails). A rollback of the alpine variant must
  therefore re-pin by **tag**: `redis:8.6.3-alpine` (local ID `d146f83b1e0f` at
  the time of verification) or re-tag from a locally retained image.
- The new digest pins were verified to resolve and pull on `linux/arm64/v8`
  (multi-arch index also covers amd64, arm/v5–v7, ppc64le, riscv64, s390x).

## Pre-upgrade: snapshot the populated volume

Run **before the first populated-environment run on 8.10.1**. Substitute the
volume name (`<project>_redis_data`, e.g. `dev_redis_data`) and a host backup
directory **under `$HOME`** (Docker Desktop on macOS does not file-share
`/tmp` by default, and a bind-mounted write there silently fails):

```bash
mkdir -p ~/redis-backups
docker run --rm \
  -v dev_redis_data:/data:ro \
  -v "$HOME/redis-backups:/backup" \
  redis:8.10.1-alpine \
  tar czf /backup/redis-pre-8.10.1.tgz -C / data
shasum -a 256 ~/redis-backups/redis-pre-8.10.1.tgz   # record the checksum
```

Verified snapshot from the #3231 acceptance run (synthetic keys):

```
sha256:0796881bf3bc7d0249238dad461659fd042765e13675f194459397cc63fed448
```

## Upgrade

1. Stop the stack: `docker compose -p dev down` (keep volumes).
2. Take the snapshot (above).
3. Pull the new image so a registry hiccup cannot strand a half-updated stack:
   `docker compose -p dev -f compose.yml -f compose.dev.yml pull redis`
4. Start: `docker compose -p dev -f compose.yml -f compose.dev.yml up -d redis`
5. Verify: `docker compose -p dev exec redis redis-server --version` →
   `v=8.10.1`; container health check reaches `healthy`; smoke probes pass.

## Rollback

If 8.10.1 misbehaves (health flaps, cache semantics drift, event-stream or
polling-lock regressions):

1. Stop redis: `docker compose -p dev stop redis`.
2. Re-pin the image in `compose.yml` (or an override file) back to the old
   reference from the table above — for the debian variant the old digest pin
   resolves directly; for the alpine variant use the `redis:8.6.3-alpine` tag.
3. If data loss or corruption is suspected, restore the snapshot first:

   ```bash
   docker volume rm dev_redis_data && docker volume create dev_redis_data
   docker run --rm \
     -v dev_redis_data:/data \
     -v "$HOME/redis-backups:/backup:ro" \
     redis:8.6.3-alpine \
     sh -c 'tar xzf /backup/redis-pre-8.10.1.tgz -C /'
   ```

4. Start the stack and verify `redis-server --version` → `v=8.6.3` and that
   sentinel keys (e.g. an expected cache key or stream) are readable.

## Acceptance evidence (2026-09-03, issue #3231)

Executed on a scratch compose project (`i3231`, port 6380) plus isolated
containers/volumes; the shared `dev` stack was not touched.

| Probe | Result |
|---|---|
| Pull both new pins by digest (`linux/arm64/v8` host) | pass |
| `docker compose config` renders new pins (`compose.yml` + ci env, `compose.core.yml`, `starter/compose.yml`) | pass |
| Fresh volume up, healthcheck → `healthy`, `redis-server v=8.10.1` (debian and alpine variants) | pass |
| Preflight redis probes (`tests/smoke/test_preflight.py -k redis`) | 5 passed, 1 expected skip (no semantic index on fresh volume) |
| LFU eviction/load (`tests/load/test_load_redis_eviction.py`): policy, maxmemory, 19 660 keys / 192 MB pressure → 8 956 evictions, Zipf hit rate 100 % | pass |
| Polling lock (`RedisPollingLock` vs live 8.10.1): acquire → second owner busy → refresh → release → reacquire | pass |
| Event stream: `XADD` + `XREAD` non-blocking + `XREAD BLOCK` timeout nil + wake-on-new-entry | pass |
| Upgrade on populated volume: 8.6.3 RDB (string/hash/stream keys) read by 8.10.1; post-upgrade write + `SAVE` | pass |
| Rollback: volume snapshot → wipe → restore → 8.6.3-alpine serves pre-upgrade keys, post-upgrade key absent | pass |
