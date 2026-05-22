# Runbook: Docling Failure

> **Owner:** Ingestion / Document parsing
> **Last verified:** 2026-05-22
> **Verification command:**
> ```bash
> COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps docling
> ```

Use this runbook when document parsing alerts fire from `docker/monitoring/rules/extended-services.yaml`.

## Covered Alerts

| Alert | Severity | Source |
|---|---|---|
| `DoclingDown` | critical | [`extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |
| `DoclingOOM` | critical | [`extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |
| `DoclingConversionFailed` | warning | [`extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |
| `DoclingError` | warning | [`extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |

## Service / Container Map

| Compose service | Typical container names |
|---|---|
| `docling` | `dev-docling-1`, `dev_docling_1` |

> Endpoints, ports, profiles: [`DOCKER.md`](../../DOCKER.md). Local dev: [`docs/LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md).

## Fast-Path Diagnosis (read-only)

### 1. Container state

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps docling
docker inspect dev-docling-1 --format '
  Name={{.Name}}
  Status={{.State.Status}}
  OOMKilled={{.State.OOMKilled}}
  ExitCode={{.State.ExitCode}}
  Restarts={{.RestartCount}}
'
```

### 2. Bounded log slice

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs docling --tail=200
```

Pattern → alert mapping:

| Pattern (case-insensitive) | Alert |
|---|---|
| no logs for 10m | `DoclingDown` |
| `killed`, `out of memory`, `oom`, `segmentation fault` | `DoclingOOM` |
| `failed to convert`, `conversion failed`, `pdf.*error`, `ocr.*error`, `timeout` | `DoclingConversionFailed` |
| `error`, `exception`, `traceback` (rate based) | `DoclingError` |

### 3. Health endpoint (if exposed)

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec docling wget -qO- http://localhost:5001/health || true
```

### 4. Backlog and last document

```bash
make ingest-unified-status
make ingest-unified-logs | tail -50
```

If a single document repeatedly crashes the converter, isolate it before restarting the service.

## Service Failure vs App Bug

| Observation | Interpretation | Next step |
|---|---|---|
| `DoclingOOM` with large PDF in last log line | Service failure (memory) | Raise memory limit in `compose.dev.yml`; consider streaming chunked input |
| `DoclingDown` after deploy of new Docling image | Service failure (regression) | Roll back image tag; pin in [`docs/engineering/sdk-registry.md`](../engineering/sdk-registry.md) |
| `DoclingConversionFailed` only on specific OCR-heavy PDFs | App bug / data issue | Quarantine offending file; capture sample for the upstream Docling repo |
| `DoclingError` with `traceback` from `coco*` | App bug (caller) | Check ingestion flow ([`src/ingestion/`](../../src/ingestion/)) for malformed payloads |
| `DoclingError` from Tesseract / EasyOCR | Service failure (OCR backend) | Reinstall OCR data files or pin language packs |

## Source Paths

| Component | Path |
|---|---|
| Docling service | [`services/docling/`](../../services/docling/) |
| Ingestion flow that calls Docling | [`src/ingestion/`](../../src/ingestion/) |
| Override ingestion flow | [`src/ingestion/unified/`](../../src/ingestion/unified/) |
| Compose definitions | [`compose.yml`](../../compose.yml), [`compose.dev.yml`](../../compose.dev.yml) |
| Alert rules | [`docker/monitoring/rules/extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |

## Logs and Artifacts

| Artifact | Location / command |
|---|---|
| Runtime logs | `docker compose logs docling --tail=200` |
| Container metadata | `docker inspect dev-docling-1` |
| Ingestion manifest | `make ingest-unified-status` |
| OCR / model cache | named volume on the docling service (`docker volume inspect`) |

## Remediation

> ⚠️ **Caution:** Mutating commands. Run only after fast-path diagnosis confirms the issue.

### `DoclingDown`

1. Capture exit reason and the last 200 log lines.
2. If image regression: pin a known-good tag in `compose.yml` and recreate.
3. Otherwise:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d --force-recreate docling
   ```

### `DoclingOOM`

1. `docker stats dev-docling-1` to capture pre-OOM RSS pattern.
2. Raise `services.docling.deploy.resources.limits.memory` in `compose.dev.yml`.
3. If the offending document was huge: split it upstream and add a size guard in the ingestion flow.

### `DoclingConversionFailed`

1. Identify the offending document (filename usually appears in the same log block).
2. Move the file to a quarantine directory and re-run the batch — should clear the alert without service restart.
3. File a follow-up issue with the document attached if it is reproducible.

### `DoclingError`

1. Aggregate the most common error class from the last 50 log lines.
2. Triage: is it a model load issue (restart fixes), a caller payload issue (fix `src/ingestion`), or an OCR backend issue (reinstall data files)?
3. Restart only after the root class is established.

## Prevention

- Pin Docling image versions in [`docs/engineering/sdk-registry.md`](../engineering/sdk-registry.md) and bump in dedicated PRs.
- Cap document size in the ingestion flow before it hits Docling.
- Track conversion latency p95 — sustained drift usually precedes OOM.

## See Also

- [`vps-gdrive-ingestion-recovery.md`](vps-gdrive-ingestion-recovery.md)
- [`EMBEDDING_SERVICE_FAILURE.md`](EMBEDDING_SERVICE_FAILURE.md)
- [`MINIO_FAILURE.md`](MINIO_FAILURE.md)
- [`DOCKER.md`](../../DOCKER.md)
- [`docs/INGESTION.md`](../INGESTION.md)
