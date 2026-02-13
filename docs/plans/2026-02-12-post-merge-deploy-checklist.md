# Post-Merge Rebuild/Deploy Checklist (PRs #193 + #194)

> **DO NOT EXECUTE** — preparation only, run after both PRs merged to main.

## Impact Analysis

| PR | Affected Files | Container Impact |
|---|---|---|
| **#193** (CI fixes) | `telegram_bot/graph/graph.py`, tests, eval scripts, `.gitignore` | **bot** (graph.py baked into image) |
| **#194** (validation thresholds) | `scripts/validate_traces.py`, `tests/baseline/thresholds.yaml`, tests, docs | None (scripts run locally via `uv run`) |

**Verdict:** Only `bot` container needs rebuild (due to `graph.py` in #193).

## Phase 1: Local Dev (WSL2)

- [ ] Pull merged main: `git checkout main && git pull origin main`
- [ ] Sync dependencies: `uv sync`
- [ ] Run CI checks locally: `make check`
- [ ] Parallel unit tests: `uv run pytest tests/unit/ -n auto -q`
- [ ] Verify thresholds: `uv run pytest tests/baseline/test_thresholds_schema.py tests/unit/test_validate_aggregates.py -v`

## Phase 2: Container Rebuild (Dev)

- [ ] Rebuild bot only:
  ```bash
  mkdir -p logs
  tmux new-window -n "W-BUILD" -c /home/user/projects/rag-fresh
  tmux send-keys -t "W-BUILD" "docker compose build --no-cache bot 2>&1 | tee logs/build-bot.log; echo '[COMPLETE]'" Enter
  ```
- [ ] Verify: `grep '\[COMPLETE\]' logs/build-bot.log`
- [ ] Restart: `docker compose up -d --force-recreate bot`
- [ ] Health check: `docker ps | grep bot && docker logs bot --tail 20`

## Phase 3: VPS Deployment

- [ ] Rsync code: `rsync -avz --exclude='.venv' --exclude='__pycache__' --exclude='.git' /home/user/projects/rag-fresh/ vps:/opt/rag-fresh/`
- [ ] Build on VPS:
  ```bash
  ssh vps "cd /opt/rag-fresh && docker compose build --no-cache bot"
  ```
- [ ] Restart: `ssh vps "cd /opt/rag-fresh && docker compose up -d --force-recreate bot"`
- [ ] Verify: `ssh vps "docker logs bot --tail 30"`

## Phase 4: Post-Deploy Verification

- [ ] Send test message to Telegram bot
- [ ] Run trace validation: `make validate-traces-fast`
- [ ] Check CI green on main: `gh run list --branch main --limit 3`

## What NOT to Rebuild

All other services unchanged: postgres, redis, qdrant, litellm, bge-m3, user-base, docling, ingestion, monitoring, voice.
