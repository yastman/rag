# Deploy Checklist: Conversation Memory (#157)

**PR:** follow-up от #154 (Conversation Memory)
**Branch:** `chore/parallel-backlog/deploy-157`

## Changes

| Change | File | Impact |
|--------|------|--------|
| Remove CallbackHandler from summarize model | `telegram_bot/graph/graph.py` | No functional change — tracing via @observe + LiteLLM |
| Remove dead conversation methods | `telegram_bot/integrations/cache.py` | No callers in production code |
| Test cleanup | 6 test files | Removed tests/mocks for deleted methods |

## Pre-deploy

- [ ] `make check` passes (ruff + mypy)
- [ ] `uv run pytest tests/unit/integrations/test_cache_layers.py tests/unit/graph/test_cache_nodes.py -v` — all pass
- [ ] `uv run pytest tests/integration/test_graph_paths.py -v` — all 6 paths pass
- [ ] `uv run pytest tests/unit/ -n auto` — full unit suite passes
- [ ] PR approved

## Deploy Steps

```bash
# 1. Build bot image
docker buildx bake bot --load

# 2. Push to VPS
make k3s-push-bot

# 3. Apply k3s manifests
make k3s-bot

# 4. Verify pods
make k3s-status
# Expected: bot pod Running, 1/1 Ready
```

## Post-deploy Live Tests

### Memory Continuity
1. Send: "Расскажи про квартиры в Несебре"
2. Wait for response
3. Send: "А какие цены?" (follow-up without explicit context)
4. Verify: response references Несебр from previous message (checkpointer memory works)

### /clear Command
1. Send: `/clear`
2. Verify: "История очищена" response
3. Send: "А какие цены?" (same follow-up)
4. Verify: response does NOT reference Несебр (memory cleared)

### Redis Keys
```bash
# On VPS:
ssh vps "docker exec redis redis-cli keys 'conversation:*'"
# Expected: no conversation:* keys (legacy writes removed)
# Semantic cache keys (sem:v3:*) should still exist
```

### Langfuse Traces
1. Open Langfuse dashboard → filter by session_id
2. Verify: no duplicate traces from CallbackHandler
3. Verify: SummarizationNode spans nest correctly under pipeline trace

## Rollback Plan

```bash
# If memory is broken:
ssh vps
kubectl rollout undo deployment/bot -n rag
kubectl rollout status deployment/bot -n rag
# Verify previous version is running:
kubectl get pods -n rag -l app=bot
```

## Success Criteria

- [ ] Bot responds to follow-up queries with context (checkpointer memory)
- [ ] `/clear` resets conversation
- [ ] No `conversation:*` Redis keys created
- [ ] Langfuse traces clean (no orphan CallbackHandler traces)
- [ ] No errors in bot logs: `kubectl logs -f deployment/bot -n rag`
