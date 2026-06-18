# Dockerfile Inventory

Audit pass for GitHub issue #2636 (2026-06-17).

## Active Dockerfiles (keep)

| Path | Image | Build context | Notes |
|---|---|---|---|
| `telegram_bot/Dockerfile` | `rag-bot` | repo root | Bot application; uses Python 3.13 per Langfuse policy (#1307, #1381) |
| `Dockerfile.ingestion` | `rag-ingestion` | repo root | Unified ingestion pipeline; copies only `src/` — `telegram_bot/` removed (#2636) |
| `services/bge-m3-api/Dockerfile` | `rag-bge-m3` | `services/bge-m3-api/` | BGE-M3 ONNX embedding service; Python 3.14 (no Langfuse import) |
| `services/docling/Dockerfile` | `rag-docling` | `services/docling/` | Docling document parser; Python 3.14 (no Langfuse import) |

## Archived Dockerfiles (do not activate)

| Path | Archived via | Original path |
|---|---|---|
| `archive/api/Dockerfile` | #2598 | `src/api/Dockerfile` |
| `archive/voice/Dockerfile` | #2598 | `src/voice/Dockerfile` |
| `archive/mini_app/Dockerfile` | #2597 | mini-app backend |
| `archive/mini_app/frontend/Dockerfile` | #2597 | mini-app frontend |

No active compose build block or publish-workflow matrix entry references any archived Dockerfile path.

## Ingestion COPY decision (#2636)

**Finding:** `Dockerfile.ingestion` previously copied `telegram_bot/` into the ingestion image in both builder and runtime stages.

**Proof that `telegram_bot/` is not needed:**

- Ingestion entrypoint: `docker/ingestion/entrypoint.sh` runs `python -m src.ingestion.unified.cli`
- `src/ingestion/unified/cli.py` and all transitive imports resolve exclusively to `src.*` packages
- `grep -rn "from telegram_bot\|import telegram_bot" src/ingestion/` returns zero hits
- `grep -rn "from telegram_bot\|import telegram_bot" src/` returns zero runtime imports (only docstring comments)

**Fix applied:** removed `COPY telegram_bot/ ./telegram_bot/` from both builder and runtime stages.

## Compose build references

Active build blocks in `compose.yml`:

| Service | Context | Dockerfile |
|---|---|---|
| `bge-m3` | `./services/bge-m3-api` | `Dockerfile` |
| `docling` | `./services/docling` | `Dockerfile` |
| `bot` | `.` (repo root) | `telegram_bot/Dockerfile` |
| `ingestion` | `.` (repo root) | `Dockerfile.ingestion` |

No references to archived `src/api/Dockerfile`, `src/voice/Dockerfile`, or mini-app Dockerfiles.

## Follow-up items (out of scope for this PR)

- Python version alignment with #2623 (bge-m3 / docling are 3.14; bot / ingestion are 3.13).
- `bot` image still passes Langfuse/OTel/Sentry/Kommo env; cleanup tracked by #2600/#2603/#2625.
- `ingestion` still receives Langfuse/OTel env; cleanup tracked by #2603.
