# SDK Audit Remediation Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Убрать критичные риски из аудита Redis/Qdrant/LangGraph/Langfuse и привести tracing/validation к актуальному SDK-first контракту.

**Architecture:** Работаем инкрементально: сначала security и корректность trace-validation, затем observability parity между Telegram/API путями, затем тестовая изоляция и мелкие UX-баги. Все изменения делаем через TDD с маленькими коммитами, не смешивая независимые задачи. Runtime-поведение не переписываем; меняем только то, что необходимо для устранения зафиксированных рисков.

**Tech Stack:** Python 3.12, pytest, Langfuse SDK v3, LangGraph + langgraph-checkpoint-redis, qdrant-client, Redis/RedisVL, FastAPI.

---

### Task 1: Remove Hardcoded Qdrant Secret From Test Script

**Files:**
- Create: `tests/unit/security/test_secret_hygiene.py`
- Modify: `tests/integration/test_basic_connection.py`

**Step 1: Write the failing test**

```python
# tests/unit/security/test_secret_hygiene.py
from pathlib import Path


def test_basic_connection_script_has_no_hardcoded_qdrant_secret() -> None:
    content = Path("tests/integration/test_basic_connection.py").read_text(encoding="utf-8")
    assert "QDRANT_API_KEY = \"" not in content
    assert "95.111.252.29" not in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/security/test_secret_hygiene.py::test_basic_connection_script_has_no_hardcoded_qdrant_secret -v`
Expected: FAIL (в файле есть literal key и IP).

**Step 3: Write minimal implementation**

```python
# tests/integration/test_basic_connection.py (top of file)
import os

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")

if not QDRANT_API_KEY:
    raise RuntimeError("QDRANT_API_KEY is required for test_basic_connection.py")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/security/test_secret_hygiene.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/unit/security/test_secret_hygiene.py tests/integration/test_basic_connection.py
git commit -m "fix(security): remove hardcoded qdrant secret from integration script"
```

### Task 2: Align E2E Langfuse Trace Validator With Current Span Contract

**Files:**
- Create: `tests/unit/e2e/test_langfuse_trace_validator.py`
- Modify: `scripts/e2e/langfuse_trace_validator.py`

**Step 1: Write the failing test**

```python
# tests/unit/e2e/test_langfuse_trace_validator.py
from types import SimpleNamespace
from unittest.mock import patch

from scripts.e2e.langfuse_trace_validator import validate_latest_trace


def test_validator_accepts_current_langgraph_span_names() -> None:
    fake_trace = SimpleNamespace(
        observations=[
            SimpleNamespace(name="telegram-rag-query"),
            SimpleNamespace(name="node-classify"),
            SimpleNamespace(name="node-cache-check"),
            SimpleNamespace(name="node-respond"),
        ],
        scores=[
            SimpleNamespace(name="query_type", value=0.0),
            SimpleNamespace(name="latency_total_ms", value=1200),
            SimpleNamespace(name="semantic_cache_hit", value=1.0),
            SimpleNamespace(name="embeddings_cache_hit", value=1.0),
            SimpleNamespace(name="search_cache_hit", value=0.0),
            SimpleNamespace(name="rerank_applied", value=0.0),
            SimpleNamespace(name="rerank_cache_hit", value=0.0),
            SimpleNamespace(name="results_count", value=0.0),
            SimpleNamespace(name="no_results", value=1.0),
            SimpleNamespace(name="llm_used", value=0.0),
        ],
    )

    fake_lf = SimpleNamespace(api=SimpleNamespace(trace=SimpleNamespace(get=lambda _id: fake_trace)))

    with (
        patch("scripts.e2e.langfuse_trace_validator._langfuse_is_configured", return_value=True),
        patch("scripts.e2e.langfuse_trace_validator.wait_for_trace", return_value="trace-1"),
        patch("scripts.e2e.langfuse_trace_validator.Langfuse", return_value=fake_lf),
    ):
        result = validate_latest_trace(
            started_at=__import__("datetime").datetime.utcnow(),
            should_skip_rag=True,
            is_command=False,
        )

    assert result.ok is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/e2e/test_langfuse_trace_validator.py::test_validator_accepts_current_langgraph_span_names -v`
Expected: FAIL (текущий validator ожидает legacy spans `telegram-message/query-router/...`).

**Step 3: Write minimal implementation**

```python
# scripts/e2e/langfuse_trace_validator.py (core contract idea)
required_spans = {"telegram-rag-query", "node-classify"}

if not is_chitchat:
    required_spans |= {"node-cache-check"}

if not is_chitchat and semantic_hit is False:
    required_spans |= {"node-retrieve", "node-grade"}
    if rerank_applied is True:
        required_spans |= {"node-rerank"}
    if llm_used is True:
        required_spans |= {"node-generate", "node-cache-store", "node-respond"}
else:
    required_spans |= {"node-respond"}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/e2e/test_langfuse_trace_validator.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/unit/e2e/test_langfuse_trace_validator.py scripts/e2e/langfuse_trace_validator.py
git commit -m "fix(observability): align e2e trace validator with current langgraph spans"
```

### Task 3: Fix Cache Flush Version Drift (`v3` -> `v4`) In Trace Validation

**Files:**
- Modify: `scripts/validate_traces.py`
- Modify: `tests/unit/test_validate_aggregates.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_validate_aggregates.py
import pytest

from scripts.validate_traces import _flush_redis_caches


@pytest.mark.asyncio
async def test_flush_redis_caches_uses_current_cache_version_patterns():
    class _FakeRedis:
        def __init__(self):
            self.patterns = []

        async def scan_iter(self, match):
            self.patterns.append(match)
            if False:
                yield None

        async def delete(self, *_args):
            return 0

    class _FakeCache:
        def __init__(self):
            self.redis = _FakeRedis()
            self.semantic_cache = None

    cache = _FakeCache()
    await _flush_redis_caches(cache)

    assert "embeddings:v4:*" in cache.redis.patterns
    assert "search:v4:*" in cache.redis.patterns
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::test_flush_redis_caches_uses_current_cache_version_patterns -v`
Expected: FAIL (сейчас patterns зашиты как `v3`).

**Step 3: Write minimal implementation**

```python
# scripts/validate_traces.py
from telegram_bot.integrations.cache import CACHE_VERSION

patterns = [
    f"embeddings:{CACHE_VERSION}:*",
    f"sparse:{CACHE_VERSION}:*",
    f"analysis:{CACHE_VERSION}:*",
    f"search:{CACHE_VERSION}:*",
    f"rerank:{CACHE_VERSION}:*",
    "conversation:*",
]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::test_flush_redis_caches_uses_current_cache_version_patterns -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/validate_traces.py tests/unit/test_validate_aggregates.py
git commit -m "fix(validation): use current cache version when flushing redis"
```

### Task 4: Add Langfuse Score Parity For FastAPI `/query`

**Files:**
- Modify: `src/api/main.py`
- Modify: `tests/unit/api/test_rag_api_runtime.py`

**Step 1: Write the failing test**

```python
# tests/unit/api/test_rag_api_runtime.py
@pytest.mark.asyncio
async def test_query_writes_langfuse_scores() -> None:
    graph = _DummyGraph()
    app.state.graph = graph
    app.state.max_rewrite_attempts = 1

    lf = MagicMock()
    lf.update_current_trace = MagicMock()
    lf.score_current_trace = MagicMock()

    with (
        patch("telegram_bot.observability.propagate_attributes", return_value=nullcontext()),
        patch("telegram_bot.observability.get_client", return_value=lf),
    ):
        await query(QueryRequest(query="test", user_id=1))

    assert lf.score_current_trace.call_count > 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/api/test_rag_api_runtime.py::test_query_writes_langfuse_scores -v`
Expected: FAIL (сейчас API путь пишет только `update_current_trace`).

**Step 3: Write minimal implementation**

```python
# src/api/main.py (inside query)
from telegram_bot.bot import _write_langfuse_scores

result = await app.state.graph.ainvoke(state)
result["pipeline_wall_ms"] = (time.perf_counter() - start) * 1000
result["user_perceived_wall_ms"] = result["pipeline_wall_ms"]

lf = get_client()
lf.update_current_trace(...)
_write_langfuse_scores(lf, result)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/api/test_rag_api_runtime.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/api/main.py tests/unit/api/test_rag_api_runtime.py
git commit -m "feat(api): emit langfuse score set for /query path"
```

### Task 5: Remove Test Import-Time Module Pollution (`sys.modules`)

**Files:**
- Create: `tests/unit/test_module_pollution.py`
- Modify: `tests/unit/graph/test_cache_nodes.py`
- Modify: `tests/unit/integrations/test_cache_layers.py`
- Modify: `tests/unit/test_pii_redaction.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_module_pollution.py
from pathlib import Path


def test_no_global_sys_modules_assignment_in_unit_tests() -> None:
    targets = [
        "tests/unit/graph/test_cache_nodes.py",
        "tests/unit/integrations/test_cache_layers.py",
        "tests/unit/test_pii_redaction.py",
    ]
    bad = []
    for path in targets:
        content = Path(path).read_text(encoding="utf-8")
        if 'sys.modules["redisvl"]' in content or 'sys.modules["langfuse"]' in content:
            bad.append(path)
    assert bad == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_module_pollution.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
# pattern to use in affected tests
@pytest.fixture(autouse=True)
def _mock_redisvl(monkeypatch):
    fake = ModuleType("redisvl")
    fake_query = ModuleType("redisvl.query")
    fake_filter = ModuleType("redisvl.query.filter")
    fake_filter.Tag = MockTag
    monkeypatch.setitem(sys.modules, "redisvl", fake)
    monkeypatch.setitem(sys.modules, "redisvl.query", fake_query)
    monkeypatch.setitem(sys.modules, "redisvl.query.filter", fake_filter)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_module_pollution.py tests/unit/graph/test_cache_nodes.py tests/unit/integrations/test_cache_layers.py tests/unit/test_pii_redaction.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/unit/test_module_pollution.py tests/unit/graph/test_cache_nodes.py tests/unit/integrations/test_cache_layers.py tests/unit/test_pii_redaction.py
git commit -m "test(isolation): replace global sys.modules patching with fixture-scoped monkeypatch"
```

### Task 6: Fix `/stats` Denominator In Bot Cache Metrics Output

**Files:**
- Modify: `telegram_bot/bot.py`
- Modify: `tests/unit/test_bot_handlers.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_bot_handlers.py (new test)
@pytest.mark.asyncio
async def test_cmd_stats_uses_hits_plus_misses_denominator(mock_config):
    bot, _ = _create_bot(mock_config)
    bot._cache = MagicMock()
    bot._cache.get_metrics.return_value = {
        "semantic": {"hit_rate": 80.0, "hits": 40, "misses": 10},
    }

    message = MagicMock()
    message.answer = AsyncMock()

    await bot.cmd_stats(message)

    rendered = message.answer.call_args[0][0]
    assert "40/50" in rendered
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_bot_handlers.py::test_cmd_stats_uses_hits_plus_misses_denominator -v`
Expected: FAIL (текущий код использует `total`, которого нет).

**Step 3: Write minimal implementation**

```python
# telegram_bot/bot.py in cmd_stats
hits = int(data.get("hits", 0))
misses = int(data.get("misses", 0))
total = hits + misses
lines.append(f"• {tier}: {hit_rate:.0f}% ({hits}/{total})")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_bot_handlers.py::test_cmd_stats_uses_hits_plus_misses_denominator -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add telegram_bot/bot.py tests/unit/test_bot_handlers.py
git commit -m "fix(bot): correct /stats denominator from hits+misses"
```

### Task 7: Redis Authentication Hardening Rollout (Compose + k8s)

**Files:**
- Modify: `docker-compose.local.yml`
- Modify: `docker-compose.vps.yml`
- Modify: `k8s/base/redis/deployment.yaml`
- Modify: `k8s/base/bot/deployment.yaml`
- Modify: `.env.example`
- Modify: `docs/LOCAL-DEVELOPMENT.md`

**Step 1: Write the failing test**

```python
# tests/unit/security/test_secret_hygiene.py
from pathlib import Path


def test_compose_redis_uses_requirepass():
    local = Path("docker-compose.local.yml").read_text(encoding="utf-8")
    vps = Path("docker-compose.vps.yml").read_text(encoding="utf-8")
    assert "--requirepass" in local
    assert "--requirepass" in vps
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/security/test_secret_hygiene.py::test_compose_redis_uses_requirepass -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```yaml
# docker-compose.vps.yml (redis)
command: >
  redis-server
  --requirepass ${REDIS_PASSWORD:?REDIS_PASSWORD is required}
  --maxmemory 256mb
  --maxmemory-policy volatile-lfu
  --maxmemory-samples 10

# bot env
REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379
```

```yaml
# k8s/base/redis/deployment.yaml
- --requirepass
- $(REDIS_PASSWORD)
env:
  - name: REDIS_PASSWORD
    valueFrom:
      secretKeyRef:
        name: api-keys
        key: REDIS_PASSWORD
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/security/test_secret_hygiene.py::test_compose_redis_uses_requirepass -v`
Expected: PASS.

Run: `docker compose -f docker-compose.local.yml config`
Expected: compose config renders successfully.

Run: `docker compose -f docker-compose.vps.yml config`
Expected: compose config renders successfully.

**Step 5: Commit**

```bash
git add docker-compose.local.yml docker-compose.vps.yml k8s/base/redis/deployment.yaml k8s/base/bot/deployment.yaml .env.example docs/LOCAL-DEVELOPMENT.md tests/unit/security/test_secret_hygiene.py
git commit -m "feat(infra): require redis auth in compose and k8s runtime"
```

### Task 8: Final Verification and Documentation Sync

**Files:**
- Modify: `docs/PROJECT_STACK.md`
- Modify: `docs/agent-rules/project-analysis.md`
- Modify: `docs/ALERTING.md` (only if redis/langfuse wiring changed)

**Step 1: Write the failing test**

```python
# tests/unit/security/test_secret_hygiene.py
from pathlib import Path


def test_stack_doc_mentions_redis_auth_requirement():
    content = Path("docs/PROJECT_STACK.md").read_text(encoding="utf-8")
    assert "REDIS_PASSWORD" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/security/test_secret_hygiene.py::test_stack_doc_mentions_redis_auth_requirement -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```markdown
# docs/PROJECT_STACK.md
- Redis runtime now requires auth (`REDIS_PASSWORD`) for local/vps/k8s profiles.
- App services must use `REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379`.
```

**Step 4: Run full required checks**

Run: `make check`
Expected: PASS.

Run: `make test-unit`
Expected: PASS.

**Step 5: Commit**

```bash
git add docs/PROJECT_STACK.md docs/agent-rules/project-analysis.md docs/ALERTING.md tests/unit/security/test_secret_hygiene.py
git commit -m "docs(stack): sync redis auth and observability remediation notes"
```

---

## Execution Notes

- Required execution skill: `@superpowers/executing-plans`
- If any step fails unexpectedly: `@superpowers/systematic-debugging`
- Before claiming completion: `@superpowers/verification-before-completion`
- Keep commits small and one-task-per-commit.
- Do not rewrite unrelated history while removing leaked keys; rotate credentials out-of-band immediately.
