# Rewrite Stop-Guard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop rewrite/retrieve loops when retrieval quality (top score) doesn't improve between attempts.

**Architecture:** grade_node compares current `top_score` with previous `grade_confidence` from state. If delta < threshold, sets `score_improved=False`. route_grade edge checks this flag alongside existing `rewrite_effective` and `rewrite_count` guards.

**Tech Stack:** LangGraph StateGraph, Python 3.12, pytest

---

## Анализ текущего состояния

### Текущий flow (rewrite loop)

```
retrieve → grade → [not relevant, count < max, effective] → rewrite → retrieve → grade → ...
```

**Ключевые значения:**
- `max_rewrite_attempts = 1` (default, env: `MAX_REWRITE_ATTEMPTS`)
- `relevance_threshold_rrf = 0.005` (env: `RELEVANCE_THRESHOLD_RRF`)
- `grade_confidence` = top document score (RRF scale: 0.001–0.016)
- `rewrite_effective` = LLM вернул другой текст (не пустой, не равен оригиналу)

**Проблема:** `rewrite_effective` проверяет только текстовое изменение, не качество retrieval. С `max_rewrite_attempts > 1` pipeline может делать бесполезные циклы.

### Ключевой инсайт

`state["grade_confidence"]` сохраняет значение из ПРЕДЫДУЩЕГО вызова grade_node. На следующем вызове можно сравнить с новым `top_score`:
- Первый вызов: `state["grade_confidence"] = 0.0` (initial) → delta всегда положительный
- Второй вызов: `state["grade_confidence"]` = top_score из первого grade → можно проверить улучшение

### Файлы

| Файл | Изменение |
|------|-----------|
| `telegram_bot/graph/state.py` | Добавить `score_improved: bool` |
| `telegram_bot/graph/config.py` | Добавить `score_improvement_delta: float` |
| `telegram_bot/graph/nodes/grade.py` | Вычислять delta, устанавливать `score_improved` |
| `telegram_bot/graph/edges.py` | Проверять `score_improved` в `route_grade` |
| `tests/unit/graph/test_edges.py` | Тесты на новое условие |
| `tests/unit/graph/test_agentic_nodes.py` | Тесты на delta в grade_node |

---

## Task 1: Добавить state field и config

**Files:**
- Modify: `telegram_bot/graph/state.py:13-39` (RAGState) и `:42-69` (make_initial_state)
- Modify: `telegram_bot/graph/config.py:14-41` (GraphConfig) и `:62-85` (from_env)

**Step 1: Write failing test — state field exists**

```python
# tests/unit/graph/test_edges.py — добавить в начало файла
def test_initial_state_has_score_improved():
    """make_initial_state должен включать score_improved=True."""
    state = make_initial_state(user_id=1, session_id="s", query="test")
    assert state["score_improved"] is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/graph/test_edges.py::test_initial_state_has_score_improved -v`
Expected: FAIL — KeyError: 'score_improved'

**Step 3: Add `score_improved` to RAGState and make_initial_state**

В `telegram_bot/graph/state.py`:

```python
class RAGState(TypedDict):
    # ... existing fields ...
    score_improved: bool  # True if retrieval score improved vs previous attempt


def make_initial_state(user_id: int, session_id: str, query: str) -> dict[str, Any]:
    return {
        # ... existing fields ...
        "score_improved": True,  # no previous attempt → allow rewrite
    }
```

**Step 4: Add `score_improvement_delta` to GraphConfig**

В `telegram_bot/graph/config.py`:

```python
@dataclass
class GraphConfig:
    # ... existing fields ...
    score_improvement_delta: float = 0.001  # minimum score gain to continue rewriting

    @classmethod
    def from_env(cls) -> GraphConfig:
        return cls(
            # ... existing ...
            score_improvement_delta=float(os.getenv("SCORE_IMPROVEMENT_DELTA", "0.001")),
        )
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/graph/test_edges.py::test_initial_state_has_score_improved -v`
Expected: PASS

**Step 6: Commit**

```bash
git add telegram_bot/graph/state.py telegram_bot/graph/config.py tests/unit/graph/test_edges.py
git commit -m "feat(graph): add score_improved state field and score_improvement_delta config"
```

---

## Task 2: Обновить grade_node — вычислять score delta

**Files:**
- Modify: `telegram_bot/graph/nodes/grade.py:20-71`
- Test: `tests/unit/graph/test_agentic_nodes.py`

**Step 1: Write failing tests**

```python
# tests/unit/graph/test_agentic_nodes.py — добавить в конец TestGradeNode

class TestGradeNodeScoreImproved:
    @pytest.mark.asyncio
    async def test_first_grade_always_improved(self):
        """First grade (prev=0.0) always sets score_improved=True."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents"] = [{"text": "doc", "score": 0.003}]
        # grade_confidence starts at 0.0
        result = await grade_node(state)
        assert result["score_improved"] is True

    @pytest.mark.asyncio
    async def test_score_improved_above_delta(self):
        """Score improved by >= delta → score_improved=True."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["grade_confidence"] = 0.003  # previous top score
        state["documents"] = [{"text": "doc", "score": 0.005}]  # delta = 0.002 > 0.001
        result = await grade_node(state)
        assert result["score_improved"] is True

    @pytest.mark.asyncio
    async def test_score_not_improved_below_delta(self):
        """Score didn't improve enough → score_improved=False."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["grade_confidence"] = 0.004  # previous top score
        state["documents"] = [{"text": "doc", "score": 0.0045}]  # delta = 0.0005 < 0.001
        result = await grade_node(state)
        assert result["score_improved"] is False

    @pytest.mark.asyncio
    async def test_score_decreased_not_improved(self):
        """Score got worse → score_improved=False."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["grade_confidence"] = 0.006
        state["documents"] = [{"text": "doc", "score": 0.004}]  # worse
        result = await grade_node(state)
        assert result["score_improved"] is False

    @pytest.mark.asyncio
    async def test_empty_docs_not_improved(self):
        """Empty documents → score_improved=False."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["grade_confidence"] = 0.005
        state["documents"] = []
        result = await grade_node(state)
        assert result["score_improved"] is False
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/graph/test_agentic_nodes.py::TestGradeNodeScoreImproved -v`
Expected: FAIL — KeyError: 'score_improved'

**Step 3: Implement delta check in grade_node**

В `telegram_bot/graph/nodes/grade.py`, обновить `grade_node`:

```python
@observe(name="node-grade")
async def grade_node(state: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    documents = state.get("documents", [])
    prev_confidence = state.get("grade_confidence", 0.0)

    if not documents:
        elapsed = time.perf_counter() - t0
        logger.info("grade: no documents, marking not relevant (%.3fs)", elapsed)
        return {
            "documents_relevant": False,
            "grade_confidence": 0.0,
            "skip_rerank": False,
            "score_improved": False,
            "latency_stages": {**state.get("latency_stages", {}), "grade": elapsed},
        }

    top_score = max(doc.get("score", 0) for doc in documents)

    from telegram_bot.graph.config import GraphConfig
    config = GraphConfig.from_env()
    relevance_threshold = config.relevance_threshold_rrf
    relevant = top_score > relevance_threshold
    skip_rerank = relevant and top_score >= config.skip_rerank_threshold

    # Score improvement check for rewrite guard
    delta = top_score - prev_confidence
    score_improved = delta >= config.score_improvement_delta or prev_confidence == 0.0

    elapsed = time.perf_counter() - t0
    logger.info(
        "grade: top_score=%.4f prev=%.4f delta=%.4f improved=%s "
        "threshold=%.3f relevant=%s skip_rerank=%s (%d docs, %.3fs)",
        top_score, prev_confidence, delta, score_improved,
        relevance_threshold, relevant, skip_rerank, len(documents), elapsed,
    )

    return {
        "documents_relevant": relevant,
        "grade_confidence": top_score,
        "skip_rerank": skip_rerank,
        "score_improved": score_improved,
        "latency_stages": {**state.get("latency_stages", {}), "grade": elapsed},
    }
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/graph/test_agentic_nodes.py::TestGradeNodeScoreImproved -v`
Expected: PASS (5/5)

**Step 5: Run all grade tests to verify no regression**

Run: `uv run pytest tests/unit/graph/test_agentic_nodes.py::TestGradeNode tests/unit/graph/test_agentic_nodes.py::TestGradeNodeRRFScores tests/unit/graph/test_agentic_nodes.py::TestGradeNodeScoreImproved -v`
Expected: PASS (all)

**Step 6: Commit**

```bash
git add telegram_bot/graph/nodes/grade.py tests/unit/graph/test_agentic_nodes.py
git commit -m "feat(graph): add score improvement delta to grade_node (#108)"
```

---

## Task 3: Обновить route_grade — проверять score_improved

**Files:**
- Modify: `telegram_bot/graph/edges.py:33-44`
- Test: `tests/unit/graph/test_edges.py`

**Step 1: Write failing tests**

```python
# tests/unit/graph/test_edges.py — добавить в TestRouteGrade

    def test_score_not_improved_stops_rewrite(self):
        """If score didn't improve, stop rewriting even if count < max."""
        state = {
            "documents_relevant": False,
            "rewrite_count": 1,
            "max_rewrite_attempts": 3,
            "rewrite_effective": True,
            "score_improved": False,
        }
        assert route_grade(state) == "generate"

    def test_score_improved_allows_rewrite(self):
        """If score improved and conditions met, allow rewrite."""
        state = {
            "documents_relevant": False,
            "rewrite_count": 1,
            "max_rewrite_attempts": 3,
            "rewrite_effective": True,
            "score_improved": True,
        }
        assert route_grade(state) == "rewrite"

    def test_score_improved_default_true_allows_rewrite(self):
        """Missing score_improved defaults to True (backward compat)."""
        state = {
            "documents_relevant": False,
            "rewrite_count": 0,
            "max_rewrite_attempts": 1,
            "rewrite_effective": True,
        }
        assert route_grade(state) == "rewrite"
```

**Step 2: Run tests to verify first fails**

Run: `uv run pytest tests/unit/graph/test_edges.py::TestRouteGrade::test_score_not_improved_stops_rewrite -v`
Expected: FAIL — AssertionError: 'rewrite' != 'generate'

**Step 3: Update route_grade**

В `telegram_bot/graph/edges.py`:

```python
def route_grade(
    state: dict[str, Any],
) -> Literal["rerank", "rewrite", "generate"]:
    """Route after grading: skip_rerank → generate, relevant → rerank, not relevant + retries → rewrite/generate."""
    if state.get("documents_relevant", False):
        if state.get("skip_rerank", False):
            return "generate"
        return "rerank"
    max_attempts = state.get("max_rewrite_attempts", 1)
    if (
        state.get("rewrite_count", 0) < max_attempts
        and state.get("rewrite_effective", True)
        and state.get("score_improved", True)
    ):
        return "rewrite"
    return "generate"
```

**Step 4: Run all edge tests**

Run: `uv run pytest tests/unit/graph/test_edges.py -v`
Expected: PASS (all, including 3 new)

**Step 5: Commit**

```bash
git add telegram_bot/graph/edges.py tests/unit/graph/test_edges.py
git commit -m "feat(graph): add score_improved guard to route_grade (#108)"
```

---

## Task 4: Интеграционный тест — полный rewrite loop с guard

**Files:**
- Modify: `tests/integration/test_graph_paths.py`

**Step 1: Проверить текущие integration tests**

Run: `uv run pytest tests/integration/test_graph_paths.py -v`
Expected: PASS (все 6 существующих)

**Step 2: Добавить тест для score guard**

```python
# tests/integration/test_graph_paths.py — добавить новый тест

@pytest.mark.asyncio
async def test_path_rewrite_stopped_by_score_guard():
    """grade(not relevant, score not improved) → generate (skip rewrite)."""
    # Настройка: max_rewrite_attempts=3, но score не улучшается
    # Первый retrieve: score=0.003 (not relevant)
    # rewrite → второй retrieve: score=0.0031 (delta=0.0001 < 0.001)
    # → score_improved=False → generate (не делаем третий rewrite)
    ...
```

Точная реализация зависит от паттерна мокирования в существующих тестах — адаптировать стиль `test_path_rewrite_loop_then_success`.

**Step 3: Run integration test**

Run: `uv run pytest tests/integration/test_graph_paths.py::test_path_rewrite_stopped_by_score_guard -v`
Expected: PASS

**Step 4: Run full test suite**

Run: `uv run pytest tests/unit/graph/ tests/integration/test_graph_paths.py -v`
Expected: PASS (all)

**Step 5: Commit**

```bash
git add tests/integration/test_graph_paths.py
git commit -m "test(graph): add integration test for rewrite score guard (#108)"
```

---

## Task 5: Проверка и финализация

**Step 1: Lint + types**

Run: `make check`
Expected: PASS

**Step 2: Full unit tests**

Run: `uv run pytest tests/unit/ -n auto`
Expected: PASS

**Step 3: Integration tests**

Run: `uv run pytest tests/integration/test_graph_paths.py -v`
Expected: PASS (7 tests)

---

## Summary таблица

| Что | Где | Значение |
|-----|-----|----------|
| Новый state field | `state.py` | `score_improved: bool` (default True) |
| Новый config | `config.py` | `score_improvement_delta: float = 0.001` (env: `SCORE_IMPROVEMENT_DELTA`) |
| Delta check | `grade.py` | `top_score - prev_confidence >= delta` |
| Guard | `edges.py` | `route_grade` проверяет `score_improved` |
| Первый grade | — | `prev_confidence = 0.0` → всегда improved |
| RRF scale | — | Scores 0.001–0.016, delta 0.001 = ~6% от top-1 |
| Backward compat | — | `state.get("score_improved", True)` — старый state без поля → разрешает rewrite |

### Edge cases

| Case | Поведение |
|------|-----------|
| `max_rewrite_attempts=1` (default) | Guard не меняет поведение (1 попытка max) |
| `max_rewrite_attempts=3`, score растёт | Все 3 попытки разрешены |
| `max_rewrite_attempts=3`, score стагнирует | Стоп после 2-й попытки (score_improved=False) |
| Empty documents после rewrite | `score_improved=False`, стоп |
| `rewrite_effective=False` | Стоп (existing guard, до score check) |
