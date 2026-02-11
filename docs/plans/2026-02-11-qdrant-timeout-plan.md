# Qdrant Timeout + Server-Side FormulaQuery Score Boosting

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Добавить explicit timeout в AsyncQdrantClient и мигрировать client-side exp_decay boosting на server-side FormulaQuery (Qdrant 1.14+).

**Architecture:** AsyncQdrantClient получает configurable timeout (default 30s). Метод `search_with_score_boosting()` заменяет numpy client-side вычисление на `models.FormulaQuery` с `ExpDecayExpression` — decay считается на сервере, убирая overhead на 2x overfetch + python loop. Требуется payload index на `metadata.created_at` для FormulaQuery.

**Tech Stack:** qdrant-client 1.16.2, Qdrant v1.16 (Docker), models.FormulaQuery, ExpDecayExpression, DecayParamsExpression

**Issue:** [#122](https://github.com/yastman/rag/issues/122) | **Milestone:** Stream-D: Infra-Perf

---

## Текущее состояние (Audit)

| Аспект | Текущее | Целевое |
|--------|---------|---------|
| AsyncQdrantClient timeout | `None` (default ~5s REST, none gRPC) | `30` (configurable via `QDRANT_TIMEOUT`) |
| Score boosting | Client-side numpy exp_decay, 2x overfetch | Server-side FormulaQuery + ExpDecayExpression |
| Qdrant server | v1.16 ✓ (docker-compose) | v1.16 (не меняем) |
| qdrant-client | 1.16.2 ✓ (pyproject.toml) | 1.16.2 (не меняем) |
| FormulaQuery | Доступен в SDK ✓ | Используем |
| `search_with_score_boosting()` usage | НЕ используется в graph (disabled by default) | Готов к use через config |
| bot pyproject.toml | `qdrant-client>=1.12.0` | `>=1.14.0` (минимум для FormulaQuery) |

## Файлы

| Файл | Изменения |
|------|-----------|
| `telegram_bot/services/qdrant.py:50` | Добавить `timeout` параметр |
| `telegram_bot/services/qdrant.py:376-471` | Переписать `search_with_score_boosting` на FormulaQuery |
| `telegram_bot/config.py:138-150` | Добавить `qdrant_timeout` field |
| `telegram_bot/pyproject.toml:9` | Bump `qdrant-client>=1.14.0` |
| `tests/unit/test_qdrant_service.py:629-820` | Обновить 8 тестов для FormulaQuery |

---

### Task 1: Добавить explicit timeout в AsyncQdrantClient

**Files:**
- Modify: `telegram_bot/config.py:138` (добавить поле перед freshness_boost_enabled)
- Modify: `telegram_bot/services/qdrant.py:31-50` (принять + передать timeout)
- Test: `tests/unit/test_qdrant_service.py`

**Step 1: Write the failing test**

В `tests/unit/test_qdrant_service.py`, добавить в начало файла (после существующих тестов `__init__`):

```python
class TestQdrantServiceTimeout:
    """Tests for explicit timeout configuration."""

    def test_default_timeout(self):
        """Verify AsyncQdrantClient receives timeout=30 by default."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_client:
            QdrantService(url="http://localhost:6333")
            mock_client.assert_called_once_with(
                url="http://localhost:6333",
                api_key=None,
                prefer_grpc=True,
                timeout=30,
            )

    def test_custom_timeout(self):
        """Verify custom timeout is passed through."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_client:
            QdrantService(url="http://localhost:6333", timeout=60)
            mock_client.assert_called_once_with(
                url="http://localhost:6333",
                api_key=None,
                prefer_grpc=True,
                timeout=60,
            )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_qdrant_service.py::TestQdrantServiceTimeout -v`
Expected: FAIL — `QdrantService.__init__` не принимает `timeout`

**Step 3: Implement**

3a. В `telegram_bot/config.py`, добавить перед `freshness_boost_enabled` (line ~138):

```python
    # Qdrant Connection
    qdrant_timeout: int = Field(
        default=30,
        validation_alias=AliasChoices("qdrant_timeout", "QDRANT_TIMEOUT"),
    )
```

3b. В `telegram_bot/services/qdrant.py:31-50`, добавить `timeout` параметр:

```python
    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        collection_name: str = "documents",
        dense_vector_name: str = "dense",
        sparse_vector_name: str = "bm42",
        quantization_mode: str = "off",
        timeout: int = 30,
    ):
        ...
        self._client = AsyncQdrantClient(
            url=url, api_key=api_key, prefer_grpc=True, timeout=timeout
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_qdrant_service.py::TestQdrantServiceTimeout -v`
Expected: PASS

**Step 5: Verify existing tests still pass**

Run: `uv run pytest tests/unit/test_qdrant_service.py -v`
Expected: ALL PASS (existing tests patch AsyncQdrantClient — не затронуты)

**Step 6: Commit**

```bash
git add telegram_bot/services/qdrant.py telegram_bot/config.py tests/unit/test_qdrant_service.py
git commit -m "feat(qdrant): add explicit timeout=30 to AsyncQdrantClient (#122)"
```

---

### Task 2: Migrate search_with_score_boosting to FormulaQuery

**Files:**
- Modify: `telegram_bot/services/qdrant.py:376-471` (переписать метод)
- Test: `tests/unit/test_qdrant_service.py:629-820` (обновить 8 тестов)

**Step 1: Write the failing test**

Заменить тест `test_score_boosting_with_fresh_document` на проверку FormulaQuery:

```python
    @pytest.mark.asyncio
    async def test_score_boosting_uses_formula_query(self, service):
        """Test that freshness boost uses server-side FormulaQuery."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.85  # Server already boosted
        mock_point.payload = {
            "page_content": "recent doc",
            "metadata": {"created_at": datetime.now(UTC).isoformat()},
        }

        service._client.query_points = AsyncMock(
            return_value=MagicMock(points=[mock_point])
        )

        results = await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=True,
            freshness_scale_days=7,
            top_k=5,
        )

        # Verify FormulaQuery was used (not raw dense vector)
        call_args = service._client.query_points.call_args
        query_arg = call_args.kwargs.get("query") or call_args[1].get("query")
        assert hasattr(query_arg, "formula"), "Expected FormulaQuery with formula attribute"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_qdrant_service.py::TestQdrantServiceScoreBoosting::test_score_boosting_uses_formula_query -v`
Expected: FAIL — текущая реализация передаёт raw dense vector, не FormulaQuery

**Step 3: Implement — переписать search_with_score_boosting**

Заменить `telegram_bot/services/qdrant.py:376-471`:

```python
    @observe(name="qdrant-search-score-boosting")
    async def search_with_score_boosting(
        self,
        dense_vector: list[float],
        filters: dict | None = None,
        top_k: int = 10,
        freshness_boost: bool = True,
        freshness_field: str = "created_at",
        freshness_scale_days: int = 7,
    ) -> list[dict]:
        """Search with score boosting using Qdrant FormulaQuery (server-side).

        Uses FormulaQuery with exp_decay for freshness boosting.
        Requires Qdrant 1.14+ and qdrant-client >= 1.14.0.
        Note: payload field used in formula must have a payload index.

        Args:
            dense_vector: Query embedding
            filters: Optional metadata filters
            top_k: Number of results
            freshness_boost: Enable freshness boosting
            freshness_field: Payload field for datetime (e.g., "created_at")
            freshness_scale_days: Decay scale in days

        Returns:
            List of results with boosted scores
        """
        await self.ensure_collection()

        # Base search without boosting
        if not freshness_boost:
            result = await self._client.query_points(
                collection_name=self._collection_name,
                query=dense_vector,
                using=self._dense_vector_name,
                query_filter=self._build_filter(filters),
                limit=top_k,
                with_payload=True,
            )
            return self._format_results(result.points)

        # Server-side score boosting via FormulaQuery (Qdrant 1.14+)
        # Formula: $score + 0.1 * exp_decay(metadata.created_at → now, scale=N days)
        formula_query = models.FormulaQuery(
            formula=models.SumExpression(
                sum=[
                    "$score",
                    models.MultExpression(
                        mult=[
                            0.1,
                            models.ExpDecayExpression(
                                exp_decay=models.DecayParamsExpression(
                                    x=models.DatetimeKeyExpression(
                                        datetime_key=f"metadata.{freshness_field}"
                                    ),
                                    scale=float(freshness_scale_days),
                                )
                            ),
                        ]
                    ),
                ]
            ),
        )

        try:
            result = await self._client.query_points(
                collection_name=self._collection_name,
                prefetch=models.Prefetch(
                    query=dense_vector,
                    using=self._dense_vector_name,
                    limit=top_k,
                ),
                query=formula_query,
                query_filter=self._build_filter(filters),
                limit=top_k,
                with_payload=True,
            )
            return self._format_results(result.points)

        except Exception as e:
            logger.warning(f"FormulaQuery score boosting failed, falling back: {e}")
            result = await self._client.query_points(
                collection_name=self._collection_name,
                query=dense_vector,
                using=self._dense_vector_name,
                query_filter=self._build_filter(filters),
                limit=top_k,
                with_payload=True,
            )
            return self._format_results(result.points)
```

**Ключевые отличия от текущего кода:**
- Убран numpy (`np.exp`), 2x overfetch, python loop по points
- `prefetch` делает dense search, `query=FormulaQuery` делает re-score
- `$score` — ссылка на score из prefetch
- `exp_decay` с `datetime_key` — сервер вычисляет decay по payload полю
- `scale` в ДНЯХ (не секундах) — Qdrant decay принимает масштаб в единицах поля

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_qdrant_service.py::TestQdrantServiceScoreBoosting::test_score_boosting_uses_formula_query -v`
Expected: PASS

**Step 5: Update remaining tests**

Обновить остальные 7 тестов в `TestQdrantServiceScoreBoosting`:

1. **test_score_boosting_disabled** — без изменений (не использует FormulaQuery)
2. **test_score_boosting_with_fresh_document** — заменить на `test_score_boosting_uses_formula_query` (уже написан)
3. **test_score_boosting_with_old_document** — убрать проверку client-side boosted score, проверять что FormulaQuery передан
4. **test_score_boosting_reorders_by_freshness** — убрать (reordering теперь server-side, нечего тестировать на mock)
5. **test_score_boosting_handles_missing_date** — убрать (server handles missing fields)
6. **test_score_boosting_handles_invalid_date** — убрать (server handles)
7. **test_score_boosting_fallback_on_error** — обновить: первый вызов (FormulaQuery) fails, fallback к plain query_points

Новые тесты:

```python
    @pytest.mark.asyncio
    async def test_score_boosting_prefetch_structure(self, service):
        """Verify prefetch contains dense query with correct limit."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.8
        mock_point.payload = {"page_content": "test", "metadata": {}}

        service._client.query_points = AsyncMock(
            return_value=MagicMock(points=[mock_point])
        )

        await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=True,
            top_k=10,
        )

        call_args = service._client.query_points.call_args
        prefetch = call_args.kwargs.get("prefetch")
        assert prefetch is not None
        assert prefetch.limit == 10

    @pytest.mark.asyncio
    async def test_score_boosting_custom_scale(self, service):
        """Verify custom freshness_scale_days is passed to FormulaQuery."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.8
        mock_point.payload = {"page_content": "test", "metadata": {}}

        service._client.query_points = AsyncMock(
            return_value=MagicMock(points=[mock_point])
        )

        await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=True,
            freshness_scale_days=14,
            top_k=5,
        )

        call_args = service._client.query_points.call_args
        query = call_args.kwargs.get("query")
        # Dig into formula to find scale=14.0
        sum_expr = query.formula
        mult_expr = sum_expr.sum[1]
        decay_expr = mult_expr.mult[1]
        assert decay_expr.exp_decay.scale == 14.0
```

**Step 6: Run all score boosting tests**

Run: `uv run pytest tests/unit/test_qdrant_service.py::TestQdrantServiceScoreBoosting -v`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add telegram_bot/services/qdrant.py tests/unit/test_qdrant_service.py
git commit -m "feat(qdrant): migrate score boosting to server-side FormulaQuery (#122)"
```

---

### Task 3: Bump qdrant-client dep + cleanup

**Files:**
- Modify: `telegram_bot/pyproject.toml:9`
- Modify: `telegram_bot/services/qdrant.py` (remove unused numpy import if no longer needed)

**Step 1: Check numpy usage in qdrant.py**

`numpy` used only in `mmr_rerank()` (lines 473-547) — KEEP import.

**Step 2: Bump dep**

В `telegram_bot/pyproject.toml:9`:
```
"qdrant-client>=1.14.0",
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/test_qdrant_service.py -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add telegram_bot/pyproject.toml
git commit -m "chore(deps): bump bot qdrant-client to >=1.14.0 for FormulaQuery (#122)"
```

---

### Task 4: (Ops) Payload index для FormulaQuery

**Контекст:** FormulaQuery с `datetime_key` ТРЕБУЕТ payload index на используемом поле. Без индекса Qdrant вернёт ошибку или проигнорирует decay.

**Действие (при включении freshness_boost):**

```python
# Одноразово на collection:
await client.create_payload_index(
    collection_name="gdrive_documents_bge",
    field_name="metadata.created_at",
    field_schema=models.PayloadSchemaType.DATETIME,
)
```

**Не включено в автоматизацию** — требуется только если `FRESHNESS_BOOST=true` (сейчас `false`).
Добавить комментарий в docstring `search_with_score_boosting` и в config.

---

## Rollback план

1. Timeout: убрать `timeout=30` из конструктора → вернуть `AsyncQdrantClient(url=url, api_key=api_key, prefer_grpc=True)`
2. FormulaQuery: git revert коммита Task 2 → вернёт client-side boosting
3. Dep bump: не блокирует (>=1.14.0 compatible с текущей 1.16.2)

## Риски

| Риск | Митигация |
|------|-----------|
| FormulaQuery синтаксис отличается для gRPC | qdrant-client конвертирует автоматически (REST↔gRPC) |
| Payload index отсутствует на VPS | `freshness_boost_enabled=False` по умолчанию — fallback path есть |
| Timeout 30s слишком длинный для fast queries | Configurable через `QDRANT_TIMEOUT`, не влияет на p95 |
| scale в DecayParamsExpression в каких единицах? | В единицах x — для datetime_key это дни (float). Проверить эмпирически. |
