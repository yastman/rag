# Memory Observability Implementation Plan (#159)

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Закрыть quick wins + medium effort из issue #159 без изменений SDK: добавить memory scores, измерить proxy checkpointer overhead вокруг `graph.ainvoke()`, расширить Redis monitor (memory + рост checkpoint keys), стандартизировать score schema.

**Architecture:** Не трогаем `AsyncRedisSaver` internals. Добавляем score-метрики в `_write_langfuse_scores` + фиксируем их через Langfuse `ScoreConfig`, считаем `graph.ainvoke()` wall-time как прокси для checkpointer overhead, в `RedisHealthMonitor` считаем checkpoint keys и алертим на рост. SDK-level hooks остаются в deferred.

**Tech Stack:** Langfuse SDK v3 (scores + score configs), Redis 8.4.0, langgraph-checkpoint-redis 0.3.4 (без модификаций)

---

## Task 1: Deferred (SDK-level) — InstrumentedAsyncRedisSaver

**Files:**
- No code changes in this plan
- Follow-up only: GitHub issue / ADR note

### Step 1: Keep SDK constraints explicit

Add to this plan (or linked tracking issue) a short note:

```markdown
Reason deferred: `AsyncRedisSaver` load/save happens inside `graph.ainvoke()`, SDK has no callback hooks.
Deferred options:
- upstream PR to `langgraph-checkpoint-redis` (load/save hooks)
- evaluate `AsyncShallowRedisSaver`
```

### Step 2: Create follow-up tracking

Create/update follow-up issue for SDK-level work and link it from #159.

Expected: #159 remains focused on quick wins + medium effort, no risky SDK subclassing in this batch.

No implementation steps in this execution plan.

---

## Task 2: New Langfuse scores — memory_messages_count, summarization_triggered + ScoreConfig

**Files:**
- Modify: `telegram_bot/bot.py:145-148` (inside `_write_langfuse_scores`)
- Test: `tests/unit/test_bot_scores.py`

### Step 1: Define score schema (Langfuse ScoreConfig)

Create/update ScoreConfig entries (UI or API) before rollout:

- `memory_messages_count`: `NUMERIC`, min `0`
- `summarization_triggered`: `BOOLEAN`, values `0/1`

Expected: ingest is schema-validated and consistent in dashboards.

### Step 2: Write failing tests

Add to `tests/unit/test_bot_scores.py`:

1. Add `"messages"` key to `FULL_PIPELINE_RESULT` (line ~86):
```python
# After "response": line, add:
"messages": [{"role": "user", "content": "query"}, {"role": "assistant", "content": "response"}],
```

2. Add `"messages"` to `CACHE_HIT_RESULT` and `CHITCHAT_RESULT` similarly.

3. Add `"summarize"` to `FULL_PIPELINE_RESULT["latency_stages"]`:
```python
"summarize": 0.250,  # 250ms summarization
```

4. Add new test class:

```python
class TestMemoryScores:
    """Test conversation memory Langfuse scores (#159)."""

    async def _run_handle_query(self, mock_config, graph_result, mock_lf_client):
        """Helper: same as TestScoreWriting._run_handle_query."""
        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=graph_result)

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf_client),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm
            mock_prop.return_value.__enter__ = MagicMock()
            mock_prop.return_value.__exit__ = MagicMock()

            await bot.handle_query(_make_message())

        return mock_lf_client

    @pytest.mark.asyncio
    async def test_memory_messages_count_written(self, mock_config):
        """memory_messages_count = len(result['messages'])."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        result = {
            **FULL_PIPELINE_RESULT,
            "messages": [{"role": "user"}, {"role": "assistant"}, {"role": "user"}],
        }
        await self._run_handle_query(mock_config, result, mock_lf)

        scores = {
            c.kwargs["name"]: c.kwargs["value"]
            for c in mock_lf.score_current_trace.call_args_list
        }
        assert scores["memory_messages_count"] == 3.0

    @pytest.mark.asyncio
    async def test_summarization_triggered_true(self, mock_config):
        """summarization_triggered=1 when summarize_ms > 0."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        result = {
            **FULL_PIPELINE_RESULT,
            "latency_stages": {**FULL_PIPELINE_RESULT["latency_stages"], "summarize": 0.250},
        }
        await self._run_handle_query(mock_config, result, mock_lf)

        scores = {
            c.kwargs["name"]: c.kwargs for c in mock_lf.score_current_trace.call_args_list
        }
        assert scores["summarization_triggered"]["value"] == 1
        assert scores["summarization_triggered"]["data_type"] == "BOOLEAN"
        assert scores["summarize_ms"]["value"] == pytest.approx(250.0, abs=1)

    @pytest.mark.asyncio
    async def test_summarization_triggered_false(self, mock_config):
        """summarization_triggered=0 when no summarize stage."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await self._run_handle_query(mock_config, CACHE_HIT_RESULT, mock_lf)

        scores = {
            c.kwargs["name"]: c.kwargs for c in mock_lf.score_current_trace.call_args_list
        }
        assert scores["summarization_triggered"]["value"] == 0
        assert scores["summarization_triggered"]["data_type"] == "BOOLEAN"

    @pytest.mark.asyncio
    async def test_memory_messages_count_zero_when_no_messages(self, mock_config):
        """memory_messages_count=0 when messages key absent."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        result = {**CHITCHAT_RESULT}
        result.pop("messages", None)  # no messages key

        await self._run_handle_query(mock_config, result, mock_lf)

        scores = {
            c.kwargs["name"]: c.kwargs["value"]
            for c in mock_lf.score_current_trace.call_args_list
        }
        assert scores["memory_messages_count"] == 0.0
```

### Step 3: Run tests to verify they fail

```bash
uv run pytest tests/unit/test_bot_scores.py::TestMemoryScores -v
```

Expected: FAIL — `"memory_messages_count" not in scores`

### Step 4: Implement scores in bot.py

In `telegram_bot/bot.py`, replace the block at lines 145-148:

```python
    # --- Conversation memory (#154, #159) ---
    summarize_ms = result.get("latency_stages", {}).get("summarize", 0) * 1000
    if summarize_ms > 0:
        lf.score_current_trace(name="summarize_ms", value=summarize_ms)
```

With:

```python
    # --- Conversation memory (#154, #159) ---
    summarize_ms = result.get("latency_stages", {}).get("summarize", 0) * 1000
    if summarize_ms > 0:
        lf.score_current_trace(name="summarize_ms", value=summarize_ms)

    # Memory scores (#159)
    messages = result.get("messages", [])
    lf.score_current_trace(name="memory_messages_count", value=float(len(messages)))
    lf.score_current_trace(
        name="summarization_triggered",
        value=1 if summarize_ms > 0 else 0,
        data_type="BOOLEAN",
    )
```

### Step 5: Update existing score count assertions

In `test_bot_scores.py`, class `TestScoreWriting`:
- `test_scores_written_full_pipeline`: add `"memory_messages_count"` and `"summarization_triggered"` to `expected_names` list. Update `call_count` from `25` to `27`.
- Add `"messages"` key to all result dicts (`FULL_PIPELINE_RESULT`, `CACHE_HIT_RESULT`, `CHITCHAT_RESULT`).

### Step 6: Run all score tests

```bash
uv run pytest tests/unit/test_bot_scores.py -v
```

Expected: ALL PASS

### Step 7: Commit

```bash
git add telegram_bot/bot.py tests/unit/test_bot_scores.py
git commit -m "feat(observability): memory_messages_count + summarization_triggered scores #159"
```

---

## Task 3: Checkpoint key growth metrics + alert in RedisHealthMonitor

**Files:**
- Modify: `telegram_bot/services/redis_monitor.py`
- Test: `tests/unit/services/test_redis_monitor.py` (new file)

### Step 1: Write failing tests

Create `tests/unit/services/test_redis_monitor.py` with two checks:

1. `_check_health` iterates `SCAN` cursor until `0` (not one-shot scan).
2. `_check_health` emits warning when `checkpoint_keys` grows above threshold.

```python
@pytest.mark.asyncio
async def test_check_health_scans_all_checkpoint_keys_and_alerts_on_growth():
    monitor = RedisHealthMonitor("redis://localhost:6379")
    monitor._prev_checkpoint_count = 100

    mock_redis = AsyncMock()
    mock_redis.info = AsyncMock(side_effect=[{"used_memory": 1, "maxmemory": 10}, {"evicted_keys": 0, "keyspace_hits": 1, "keyspace_misses": 1}])
    mock_redis.dbsize = AsyncMock(return_value=5000)
    mock_redis.scan = AsyncMock(side_effect=[(1, ["checkpoint:1", "checkpoint:2"]), (0, ["checkpoint:3"])])
    monitor._redis = mock_redis

    with patch("telegram_bot.services.redis_monitor.logger") as mock_logger:
        await monitor._check_health()

    assert mock_redis.scan.call_count == 2
    mock_logger.warning.assert_any_call(
        "Redis health: checkpoint key growth detected prev=%d current=%d delta=%d",
        100,
        103,
        3,
    )
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/unit/services/test_redis_monitor.py -v
```

Expected: FAIL — cursor iteration and/or growth alert missing.

### Step 3: Implement checkpoint growth monitoring

In `telegram_bot/services/redis_monitor.py`:

1. Add threshold constant:

```python
CHECKPOINT_GROWTH_WARN_DELTA = 1  # warn on any growth; tune later if noisy
```

2. Add state in `RedisHealthMonitor.__init__`:

```python
self._prev_checkpoint_count: int | None = None
```

3. Extend `_check_health()` after existing INFO metrics:

```python
# --- Checkpoint key metrics (#159) ---
dbsize = await self._redis.dbsize()
cursor = 0
checkpoint_count = 0
while True:
    cursor, keys = await self._redis.scan(
        cursor=cursor,
        match="checkpoint:*",
        count=1000,
    )
    checkpoint_count += len(keys)
    if cursor == 0:
        break

prev_checkpoint_count = self._prev_checkpoint_count
self._prev_checkpoint_count = checkpoint_count

logger.info(
    "Redis health: dbsize=%d checkpoint_keys=%d",
    dbsize,
    checkpoint_count,
)

if (
    prev_checkpoint_count is not None
    and checkpoint_count - prev_checkpoint_count >= CHECKPOINT_GROWTH_WARN_DELTA
):
    logger.warning(
        "Redis health: checkpoint key growth detected prev=%d current=%d delta=%d",
        prev_checkpoint_count,
        checkpoint_count,
        checkpoint_count - prev_checkpoint_count,
    )
```

### Step 4: Run tests

```bash
uv run pytest tests/unit/services/test_redis_monitor.py -v
```

Expected: PASS

### Step 5: Commit

```bash
git add telegram_bot/services/redis_monitor.py tests/unit/services/test_redis_monitor.py
git commit -m "feat(observability): checkpoint key growth monitoring in RedisHealthMonitor #159"
```

---

## Task 4: Measure `graph.ainvoke()` proxy overhead and write score

**Files:**
- Modify: `telegram_bot/bot.py`
- Test: `tests/unit/test_bot_scores.py`

### Step 1: Write failing tests

Add to `tests/unit/test_bot_scores.py`:

1. Unit test for helper:

```python
def test_compute_checkpointer_overhead_proxy_ms():
    from telegram_bot.bot import _compute_checkpointer_overhead_proxy_ms

    result = {"latency_stages": {"classify": 0.001, "generate": 0.100}}
    # stages = 101ms, ainvoke wall = 140ms -> proxy overhead = 39ms
    assert _compute_checkpointer_overhead_proxy_ms(result, 140.0) == pytest.approx(39.0, abs=0.1)
    # clamp at zero
    assert _compute_checkpointer_overhead_proxy_ms(result, 50.0) == 0.0
```

2. Score emission test:

```python
@pytest.mark.asyncio
async def test_checkpointer_overhead_proxy_score_written(self, mock_config):
    mock_lf = MagicMock()
    mock_lf.update_current_trace = MagicMock()
    mock_lf.score_current_trace = MagicMock()

    result = {**FULL_PIPELINE_RESULT, "checkpointer_overhead_proxy_ms": 39.0}
    await self._run_handle_query(mock_config, result, mock_lf)

    scores = {c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list}
    assert scores["checkpointer_overhead_proxy_ms"] == 39.0
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/unit/test_bot_scores.py -k "checkpointer_overhead_proxy or compute_checkpointer_overhead_proxy" -v
```

Expected: FAIL — helper + score are missing.

### Step 3: Implement in `bot.py`

1. Add helper:

```python
def _compute_checkpointer_overhead_proxy_ms(result: dict[str, Any], ainvoke_wall_ms: float) -> float:
    stages_ms = sum(float(v) * 1000 for v in result.get("latency_stages", {}).values())
    return max(0.0, ainvoke_wall_ms - stages_ms)
```

2. In `handle_query` and `handle_voice`, wrap `graph.ainvoke()`:

```python
invoke_start = time.perf_counter()
result = await graph.ainvoke(state, config=invoke_config)
ainvoke_wall_ms = (time.perf_counter() - invoke_start) * 1000
result["checkpointer_overhead_proxy_ms"] = _compute_checkpointer_overhead_proxy_ms(
    result, ainvoke_wall_ms
)
```

3. In `_write_langfuse_scores` add:

```python
if "checkpointer_overhead_proxy_ms" in result:
    lf.score_current_trace(
        name="checkpointer_overhead_proxy_ms",
        value=float(result["checkpointer_overhead_proxy_ms"]),
    )
```

4. Update `TestScoreWriting.test_scores_written_full_pipeline` expectations:
- add `"checkpointer_overhead_proxy_ms"` in `expected_names`
- update `call_count` from `27` to `28`

### Step 4: Run tests

```bash
uv run pytest tests/unit/test_bot_scores.py -v
```

Expected: PASS

### Step 5: Commit

```bash
git add telegram_bot/bot.py tests/unit/test_bot_scores.py
git commit -m "feat(observability): add checkpointer_overhead_proxy_ms score #159"
```

---

## Task 5: Add memory/overhead fields to trace metadata

**Files:**
- Modify: `telegram_bot/bot.py:166-185` (`_build_trace_metadata`)

### Step 1: Write failing test

Add to `tests/unit/test_bot_scores.py::TestVoiceTraceMetadata`:

```python
    @pytest.mark.asyncio
    async def test_trace_metadata_contains_memory_and_overhead(self, mock_config):
        """Trace metadata should include memory_messages_count and overhead proxy."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        result = {
            **FULL_PIPELINE_RESULT,
            "messages": [{"role": "user"}, {"role": "assistant"}],
            "checkpointer_overhead_proxy_ms": 39.0,
        }
        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=result)

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm
            mock_prop.return_value.__enter__ = MagicMock()
            mock_prop.return_value.__exit__ = MagicMock()

            await bot.handle_query(_make_message())

        metadata = mock_lf.update_current_trace.call_args.kwargs["metadata"]
        assert metadata["memory_messages_count"] == 2
        assert metadata["checkpointer_overhead_proxy_ms"] == 39.0
```

### Step 2: Run test

```bash
uv run pytest tests/unit/test_bot_scores.py::TestVoiceTraceMetadata::test_trace_metadata_contains_memory_and_overhead -v
```

Expected: FAIL — one/both fields absent in metadata.

### Step 3: Implement

In `telegram_bot/bot.py`, add to `_build_trace_metadata()` (after `"stt_duration_ms"` line):

```python
        # Conversation memory (#159)
        "memory_messages_count": len(result.get("messages", [])),
        "checkpointer_overhead_proxy_ms": result.get("checkpointer_overhead_proxy_ms"),
```

### Step 4: Run all tests

```bash
uv run pytest tests/unit/test_bot_scores.py -v
```

Expected: ALL PASS

### Step 5: Commit

```bash
git add telegram_bot/bot.py tests/unit/test_bot_scores.py
git commit -m "feat(observability): add memory + overhead fields to trace metadata #159"
```

---

## Task 6: Run full test suite + lint

### Step 1: Lint

```bash
uv run ruff check telegram_bot/bot.py telegram_bot/services/redis_monitor.py tests/unit/test_bot_scores.py tests/unit/services/test_redis_monitor.py
uv run ruff format telegram_bot/bot.py telegram_bot/services/redis_monitor.py tests/unit/test_bot_scores.py tests/unit/services/test_redis_monitor.py
```

### Step 2: MyPy

```bash
uv run mypy telegram_bot/bot.py telegram_bot/services/redis_monitor.py --ignore-missing-imports
```

### Step 3: Full unit test suite

```bash
uv run pytest tests/unit/ -x -q --timeout=30
```

Expected: ALL PASS, no regressions

### Step 4: Integration test (graph paths)

```bash
uv run pytest tests/integration/test_graph_paths.py -v
```

Expected: 6/6 PASS

### Step 5: Final commit (if any lint fixes)

```bash
git add -u
git commit -m "style: lint fixes for memory observability #159"
```

---

## Summary

| Task | What | Langfuse Impact |
|------|------|-----------------|
| 1 | Deferred SDK work | Track `AsyncRedisSaver` hook options in follow-up issue (no code in this batch) |
| 2 | New scores + schema | `memory_messages_count` (NUMERIC), `summarization_triggered` (BOOLEAN), ScoreConfig guardrails |
| 3 | Redis monitor | `checkpoint_keys` count via full SCAN + growth warning alert |
| 4 | Medium effort metric | `checkpointer_overhead_proxy_ms` score from `graph.ainvoke()` wall-time delta |
| 5 | Trace metadata | `memory_messages_count` + `checkpointer_overhead_proxy_ms` filterable in Langfuse UI |
| 6 | Lint + full tests | No regressions |

**Observability rules reference:** `.claude/rules/observability.md` — pattern: `@observe(capture_input=False, capture_output=False)` + curated `update_current_span(input={...}, output={...})`.
