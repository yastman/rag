# Docker Desktop stale-socket recovery (Windows)

Non-destructive recovery for Docker Desktop startup failure caused by a stale Docker AI
inference AF_UNIX socket under the AppData Docker runtime directory. Verified on Docker
Desktop 4.83.0 (Engine 29.6.2 restored); upstream reports:
[docker/desktop-feedback#460](https://github.com/docker/desktop-feedback/issues/460),
[docker/desktop-feedback#531](https://github.com/docker/desktop-feedback/issues/531).

For general Compose/runtime reference see [`../../DOCKER.md`](../../DOCKER.md) and
[Local Development](../LOCAL-DEVELOPMENT.md).

## Safety gates

This procedure **moves** one stale runtime directory and never deletes anything.

- No recursive deletion (`Remove-Item -Recurse`), no factory reset ("Troubleshoot →
  Reset to factory data"), no `wsl --shutdown`.
- Never touched: named volumes, images, WSL data (`C:\Users\<you>\AppData\Local\Docker\wsl`),
  Docker settings (`settings-store.json`), logs, and the quarantined directory itself.
- The quarantine is kept until the post-recovery checklist passes. Rollback is a rename back.
- Not every Docker Desktop startup failure shares this cause — verify the log signature
  below before moving anything.

## Symptoms and log signatures

- Docker Desktop fails during startup and the engine never becomes ready.
- The host log (Docker Desktop → Troubleshoot → Diagnose & Feedback, or
  `C:\Users\<you>\AppData\Local\Docker\log\host\`) shows the backend failing while removing
  the runtime directory `AppData\Local\Docker\run\dockerInference` (a stale Docker AI
  inference AF_UNIX socket), after which the backend cancels all engines.

## 1. Stop Docker Desktop and verify processes

Quit Docker Desktop from the system-tray whale menu (right-click → **Quit Docker Desktop**),
then verify no Docker backend process still holds the socket:

```powershell
Get-Process | Where-Object { $_.ProcessName -like 'com.docker*' -or $_.ProcessName -like 'Docker Desktop*' }
```

Expected: no output. If processes remain, stop only the Docker Desktop processes (never WSL):

```powershell
Stop-Process -Name 'Docker Desktop','com.docker.backend'
```

## 2. Resolve and verify the exact AppData runtime target

Resolve your literal AppData path first and substitute it in every command below
(`<you>` is your Windows user name):

```powershell
Write-Output $env:LOCALAPPDATA   # e.g. C:\Users\you\AppData\Local
```

Confirm the stale target exists and inspect it read-only before moving:

```powershell
Test-Path 'C:\Users\<you>\AppData\Local\Docker\run\dockerInference'
Get-ChildItem 'C:\Users\<you>\AppData\Local\Docker\run\dockerInference'
```

Verify the target is the Docker Desktop **runtime** directory — its parent must be
`C:\Users\<you>\AppData\Local\Docker\run`. Do not move anything under
`C:\Users\<you>\AppData\Local\Docker\wsl` (WSL data), `C:\Users\<you>\AppData\Roaming\Docker`
(settings), or `C:\Users\<you>\AppData\Local\Docker\log` (logs).

## 3. Quarantine the stale runtime directory

Move only the stale directory to a timestamped sibling (same volume, so this is a rename):

```powershell
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
Move-Item 'C:\Users\<you>\AppData\Local\Docker\run\dockerInference' "C:\Users\<you>\AppData\Local\Docker\run\dockerInference.quarantine-$ts"
```

If the log names a different `dockerInference*` runtime directory, move only that one, using
its exact resolved path. Keep the quarantined copy until verification passes.

## 4. Restart and wait for the engine

```powershell
Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
$deadline = (Get-Date).AddMinutes(5)
while ((Get-Date) -lt $deadline) {
    docker info 2>$null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 5
}
docker info
```

`docker info` must succeed and report a server engine version (for example `Server Version:
29.6.2`) before you continue. If it does not come up within the deadline, go to
[Diagnostics escalation](#diagnostics-escalation-if-the-failure-repeats).

## Post-recovery checklist

From the repository root (requires `.env` with `POSTGRES_PASSWORD` and `REDIS_PASSWORD`;
see [Local Development](../LOCAL-DEVELOPMENT.md)):

1. **Docker engine**: `docker info` succeeds (Server Version reported).
2. **Start the three base data services** (PostgreSQL, Redis, Qdrant):

   ```powershell
   docker compose -f compose.yml -f compose.dev.yml --profile postgres up -d
   ```

3. **All three containers healthy** — `postgres`, `redis`, `qdrant` show `Up ... (healthy)`:

   ```powershell
   docker compose -f compose.yml -f compose.dev.yml --profile postgres ps
   ```

4. **Direct probes** (each must answer as shown):

   ```powershell
   curl.exe -s http://127.0.0.1:6333/readyz
   # -> ok
   docker compose -f compose.yml -f compose.dev.yml --profile postgres exec redis sh -c 'redis-cli -a "$REDIS_PASSWORD" ping'
   # -> PONG
   docker compose -f compose.yml -f compose.dev.yml --profile postgres exec postgres pg_isready -U postgres
   # -> ... accepting connections
   ```

5. **Data preserved**: `docker volume ls` still lists your named volumes
   (`*_qdrant_data`, `*_redis_data`, `*_postgres_data`) and the Qdrant collections are intact
   (`curl.exe -s http://127.0.0.1:6333/collections`).

Only after this checklist passes may you delete the quarantined directory yourself; this
runbook does not prescribe that deletion.

## Rollback from quarantine

If verification fails and you need the previous state back:

1. Quit Docker Desktop and verify processes are gone (step 1 above).
2. Check the original path is absent again (Docker may have recreated it; if it exists, do
   **not** move over it — go to diagnostics escalation instead):

   ```powershell
   Test-Path 'C:\Users\<you>\AppData\Local\Docker\run\dockerInference'
   ```

3. Rename the quarantine back (substitute your timestamp):

   ```powershell
   Move-Item 'C:\Users\<you>\AppData\Local\Docker\run\dockerInference.quarantine-<timestamp>' 'C:\Users\<you>\AppData\Local\Docker\run\dockerInference'
   ```

4. Restart Docker Desktop and wait on `docker info` (step 4 above). Volumes were never
   touched, so no data rollback is needed.

## Diagnostics escalation if the failure repeats

A repeat of the same signature means the stale socket is a symptom of an underlying fault,
not a one-off. Escalate instead of repeating or escalating the cleanup:

1. Capture diagnostics: Docker Desktop → Troubleshoot → **Get support** (Diagnose & Feedback),
   including the host logs under `C:\Users\<you>\AppData\Local\Docker\log\host\`.
2. Compare against and subscribe to the upstream reports
   [#460](https://github.com/docker/desktop-feedback/issues/460) and
   [#531](https://github.com/docker/desktop-feedback/issues/531).
3. Do not use factory reset as a first resort — it destroys volumes and images that this
   procedure exists to preserve. Factory reset is an explicitly operator-owned, last-resort
   decision outside this runbook.
