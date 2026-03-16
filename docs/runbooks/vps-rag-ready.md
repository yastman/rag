# VPS RAG-Ready Runbook

## Reality Check

1. Collect runtime inventory:
   `uv run python scripts/vps_runtime_inventory.py --host vps --project-dir /opt/rag-fresh`
2. Confirm remote `COMPOSE_FILE` is `compose.yml:compose.vps.yml`.
3. Verify core containers include `vps-postgres`, `vps-redis`, `vps-qdrant`, `vps-bge-m3`, `vps-litellm`, `vps-bot`.

## Deploy Rehearsal

1. Run local gate before deploy: `make check`.
2. Run manual VPS deploy path: `./scripts/deploy-vps.sh`.
3. Run preflight verification: `make vps-rag-preflight`.

## Telegram Smoke

1. Send one Telegram knowledge-base question to the VPS bot.
2. Confirm the bot returns an answer with expected retrieval-backed content.
3. If failed, inspect logs first in `vps-bot`, then `vps-qdrant`, then `vps-litellm`.

## Restart And Cutover

1. Perform restart/recreate rehearsal for core services and re-run the same Telegram question.
2. If both smoke runs pass, decision is `ready for main auto-deploy`.
3. If any step fails, decision is `blocked` and blocker must be documented before cutover.
