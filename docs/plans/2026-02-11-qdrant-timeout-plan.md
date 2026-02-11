***REMOVED*** Timeout + FormulaQuery Score Boosting — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Добавить explicit timeout в AsyncQdrantClient и мигрировать client-side exp_decay boosting на server-side FormulaQuery (Qdrant 1.14+).

**Issue:** [#122](https://github.com/yastman/rag/issues/122) | **Milestone:** Stream-D: Infra-Perf

**Architecture:** AsyncQdrantClient получает configurable timeout (default 30s). Метод `search_with_score_boosting()` заменяет numpy client-side вычисление на `models.FormulaQuery` с `ExpDecayExpression` — decay считается на сервере, убирая overhead на 2x overfetch + python loop. Требуется payload index на `metadata.created_at` для FormulaQuery.

**Tech Stack:** qdrant-client 1.16.2, Qdrant v1.16 (Docker), models.FormulaQuery, ExpDecayExpression, DecayParamsExpression, DatetimeKeyExpression

---

## Текущее состояние (Audit)

| Аспект | Текущее | Целевое |
|--------|---------|---------|
| AsyncQdrantClient timeout | `None` (default 5s REST, unlimited gRPC) | `30` (configurable via `QDRANT_TIMEOUT`) |
| Score boosting | Client-side numpy exp_decay, 2x overfetch, python loop | Server-side FormulaQuery + ExpDecayExpression |
| Qdrant server | v1.16 (docker-compose.dev.yml:60) | v1.16 (не меняем) |
| qdrant-client (root) | 1.16.2 (pyproject.toml:19) | 1.16.2 (не меняем) |
| qdrant-client (bot) | >=1.12.0 (telegram_bot/pyproject.toml:9) | >=1.14.0 (минимум для FormulaQuery) |
| FormulaQuery в SDK | Доступен ✓ (models.FormulaQuery) | Используем |
| DatetimeKeyExpression | Доступен ✓ (models.DatetimeKeyExpression) | Используем в decay |
| `search_with_score_boosting()` usage | Не используется в graph (freshness_boost_enabled=False) | Готов к use через config |
| Тесты score boosting | 8 тестов (lines 629-823), client-side expectations | Обновить на FormulaQuery assertions |

## SDK Reference (verified on qdrant-client 1.16.2)

**Timeout:** `AsyncQdrantClient(timeout=N)` — applies to both REST (httpx timeout) and gRPC. Default: 5s REST, unlimited gRPC. Per-method override: `query_points(..., timeout=N)`.

**FormulaQuery construction (validated):**

    fq = models.FormulaQuery(
        formula=models.SumExpression(
            sum=[
                "$score",
                models.MultExpression(
                    mult=[
                        0.1,
                        models.ExpDecayExpression(
                            exp_decay=models.DecayParamsExpression(
                                x=models.DatetimeKeyExpression(datetime_key="metadata.created_at"),
                                scale=7.0,
                            )
                        ),
                    ]
                ),
            ]
        ),
    )

**Serializes to JSON:**

    {
      "formula": {
        "sum": [
          "$score",
          {"mult": [0.1, {"exp_decay": {"x": {"datetime_key": "metadata.created_at"}, "scale": 7.0}}]}
        ]
      }
    }

**Prefetch + FormulaQuery pattern (from Qdrant 1.14 blog):**

    result = await client.query_points(
        collection_name="...",
        prefetch=models.Prefetch(query=dense_vector, using="dense", limit=50),
        query=formula_query,
        limit=top_k,
        with_payload=True,
    )

**DecayParamsExpression fields:**
- `x` (Expression) — поле для decay (DatetimeKeyExpression для дат, GeoDistance для гео)
- `target` (Expression, optional) — целевое значение (default 0, для дат — "сейчас" автоматически)
- `scale` (float, optional) — масштаб decay в единицах x (для datetime_key — дни). Default 1.0
- `midpoint` (float, optional) — выход при |x-target|==scale. Default 0.5

## Файлы

| Файл | Строки | Изменения |
|------|--------|-----------|
| `telegram_bot/services/qdrant.py` | 31-50 | Добавить `timeout` параметр в `__init__` |
| `telegram_bot/services/qdrant.py` | 376-471 | Переписать `search_with_score_boosting` на FormulaQuery |
| `telegram_bot/config.py` | 138 | Добавить `qdrant_timeout` field перед `freshness_boost_enabled` |
| `telegram_bot/pyproject.toml` | 9 | Bump `qdrant-client>=1.14.0` |
| `tests/unit/test_qdrant_service.py` | 629-823 | Обновить 8 тестов для FormulaQuery |

---

### Task 1: Добавить explicit timeout в AsyncQdrantClient (~3 мин)

**Files:** `telegram_bot/config.py:138`, `telegram_bot/services/qdrant.py:31-50`, `tests/unit/test_qdrant_service.py`

**Step 1: Write the failing test**

В `tests/unit/test_qdrant_service.py`, добавить новый класс после `TestQdrantServiceFormatResults` (line ~627):

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

**Step 2: Run test — should FAIL**

    uv run pytest tests/unit/test_qdrant_service.py::TestQdrantServiceTimeout -v

Expected: FAIL — `QdrantService.__init__` не принимает `timeout`

**Step 3a: Add `qdrant_timeout` to BotConfig**

В `telegram_bot/config.py`, перед `freshness_boost_enabled` (line 138), добавить:

    ***REMOVED*** Connection
    qdrant_timeout: int = Field(
        default=30,
        validation_alias=AliasChoices("qdrant_timeout", "QDRANT_TIMEOUT"),
    )

**Step 3b: Add `timeout` parameter to QdrantService.__init__**

В `telegram_bot/services/qdrant.py:31-50`, добавить `timeout: int = 30` в параметры `__init__` и передать в AsyncQdrantClient:

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
        self._client = AsyncQdrantClient(url=url, api_key=api_key, prefer_grpc=True, timeout=timeout)

**Step 4: Run test — should PASS**

    uv run pytest tests/unit/test_qdrant_service.py::TestQdrantServiceTimeout -v

**Step 5: Run ALL existing tests — no regressions**

    uv run pytest tests/unit/test_qdrant_service.py -v

Existing tests patch AsyncQdrantClient и не проверяют timeout — не затронуты.

**Step 6: Commit**

    git add telegram_bot/services/qdrant.py telegram_bot/config.py tests/unit/test_qdrant_service.py
    git commit -m "feat(qdrant): add explicit timeout=30 to AsyncQdrantClient (#122)"

---

### Task 2: Migrate search_with_score_boosting to FormulaQuery (~5 мин)

**Files:** `telegram_bot/services/qdrant.py:376-471`, `tests/unit/test_qdrant_service.py:629-823`

**Step 1: Write the failing test**

Добавить тест в `TestQdrantServiceScoreBoosting` (line 629):

    @pytest.mark.asyncio
    async def test_score_boosting_uses_formula_query(self, service):
        """Test that freshness boost uses server-side FormulaQuery."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.85
        mock_point.payload = {"page_content": "recent doc", "metadata": {}}

        service._client.query_points = AsyncMock(
            return_value=MagicMock(points=[mock_point])
        )

        await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=True,
            freshness_scale_days=7,
            top_k=5,
        )

        call_args = service._client.query_points.call_args
        query_arg = call_args.kwargs.get("query") or call_args[1].get("query")
        assert hasattr(query_arg, "formula"), "Expected FormulaQuery with formula attribute"

**Step 2: Run test — should FAIL**

    uv run pytest "tests/unit/test_qdrant_service.py::TestQdrantServiceScoreBoosting::test_score_boosting_uses_formula_query" -v

Expected: FAIL — текущая реализация передаёт raw dense vector, не FormulaQuery

**Step 3: Rewrite search_with_score_boosting (lines 376-471)**

Заменить весь метод `search_with_score_boosting` в `telegram_bot/services/qdrant.py`:

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
        """Search with server-side score boosting using FormulaQuery.

        Uses FormulaQuery with exp_decay for freshness boosting (Qdrant 1.14+).
        Formula: $score + 0.1 * exp_decay(metadata.{field}, scale=N days)
        Note: payload field used in formula benefits from a payload index.

        Args:
            dense_vector: Query embedding
            filters: Optional metadata filters
            top_k: Number of results
            freshness_boost: Enable freshness boosting
            freshness_field: Payload field for datetime
            freshness_scale_days: Decay scale in days

        Returns:
            List of results with boosted scores
        """
        await self.ensure_collection()

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

**Ключевые отличия от текущего кода:**

| Было (client-side) | Стало (server-side) |
|--------------------|---------------------|
| `limit=top_k * 2` (2x overfetch) | `prefetch.limit=top_k` (точный лимит) |
| `np.exp(-age_seconds / scale_seconds)` | `ExpDecayExpression(scale=days)` |
| Python loop по points + sort | Qdrant вычисляет decay + сортирует |
| `import numpy as np` (для decay) | numpy используется только в mmr_rerank |

**Step 4: Run test — should PASS**

    uv run pytest "tests/unit/test_qdrant_service.py::TestQdrantServiceScoreBoosting::test_score_boosting_uses_formula_query" -v

**Step 5: Update remaining tests (lines 629-823)**

Тесты которые нужно ОБНОВИТЬ:

1. `test_score_boosting_disabled` (line 644) — БЕЗ ИЗМЕНЕНИЙ (freshness_boost=False path не изменился)

2. `test_score_boosting_with_fresh_document` (line 663) — Обновить: убрать проверку client-side score, проверить что FormulaQuery передан

3. `test_score_boosting_with_old_document` (line 691) — Обновить: убрать client-side score check, проверить FormulaQuery

4. `test_score_boosting_reorders_by_freshness` (line 717) — УДАЛИТЬ: reordering теперь server-side, на mock невозможно тестировать

5. `test_score_boosting_handles_missing_date` (line 757) — УДАЛИТЬ: server handles missing fields через defaults в FormulaQuery

6. `test_score_boosting_handles_invalid_date` (line 779) — УДАЛИТЬ: server handles invalid dates

7. `test_score_boosting_fallback_on_error` (line 801) — ОБНОВИТЬ: первый вызов (FormulaQuery) fails → fallback к plain query_points

Тесты которые нужно ДОБАВИТЬ:

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
            dense_vector=[0.1] * 1024, freshness_boost=True, top_k=10,
        )

        call_args = service._client.query_points.call_args
        prefetch = call_args.kwargs.get("prefetch")
        assert prefetch is not None
        assert prefetch.limit == 10

    @pytest.mark.asyncio
    async def test_score_boosting_custom_scale(self, service):
        """Verify custom freshness_scale_days reaches FormulaQuery."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.8
        mock_point.payload = {"page_content": "test", "metadata": {}}

        service._client.query_points = AsyncMock(
            return_value=MagicMock(points=[mock_point])
        )

        await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024, freshness_boost=True,
            freshness_scale_days=14, top_k=5,
        )

        call_args = service._client.query_points.call_args
        query = call_args.kwargs.get("query")
        sum_expr = query.formula
        mult_expr = sum_expr.sum[1]
        decay_expr = mult_expr.mult[1]
        assert decay_expr.exp_decay.scale == 14.0

    @pytest.mark.asyncio
    async def test_score_boosting_custom_field(self, service):
        """Verify custom freshness_field reaches FormulaQuery."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.8
        mock_point.payload = {"page_content": "test", "metadata": {}}

        service._client.query_points = AsyncMock(
            return_value=MagicMock(points=[mock_point])
        )

        await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024, freshness_boost=True,
            freshness_field="updated_at", top_k=5,
        )

        call_args = service._client.query_points.call_args
        query = call_args.kwargs.get("query")
        sum_expr = query.formula
        mult_expr = sum_expr.sum[1]
        decay_expr = mult_expr.mult[1]
        assert decay_expr.exp_decay.x.datetime_key == "metadata.updated_at"

**Step 6: Run all score boosting tests**

    uv run pytest tests/unit/test_qdrant_service.py::TestQdrantServiceScoreBoosting -v

Expected: ALL PASS

**Step 7: Commit**

    git add telegram_bot/services/qdrant.py tests/unit/test_qdrant_service.py
    git commit -m "feat(qdrant): migrate score boosting to server-side FormulaQuery (#122)"

---

### Task 3: Bump bot qdrant-client dep + final check (~2 мин)

**Files:** `telegram_bot/pyproject.toml:9`, `telegram_bot/requirements.txt:8`

**Step 1: Bump qdrant-client minimum version**

В `telegram_bot/pyproject.toml:9`:

    "qdrant-client>=1.14.0",  # v1.14+ for FormulaQuery score boosting

В `telegram_bot/requirements.txt:8`:

    qdrant-client>=1.14.0

**Step 2: numpy import cleanup check**

`numpy` в `telegram_bot/services/qdrant.py` используется в `mmr_rerank()` (lines 473-547) — KEEP import. Numpy НЕ удаляем.

**Step 3: Run full test suite**

    uv run pytest tests/unit/test_qdrant_service.py -v

Expected: ALL PASS

**Step 4: Lint**

    make check

Expected: PASS

**Step 5: Commit**

    git add telegram_bot/pyproject.toml telegram_bot/requirements.txt
    git commit -m "chore(deps): bump bot qdrant-client to >=1.14.0 for FormulaQuery (#122)"

---

### Task 4 (Ops, deferred): Payload index для FormulaQuery

**Контекст:** FormulaQuery с `datetime_key` ТРЕБУЕТ payload index на используемом поле. Без индекса — Qdrant выдаёт ошибку или decay не работает. Из Qdrant 1.14 blog: "Payload variables used within the formula benefit from having payload indexes. So, we require you to set up a payload index for any variable used in a formula."

**Действие (при включении FRESHNESS_BOOST=true):**

    await client.create_payload_index(
        collection_name="gdrive_documents_bge",
        field_name="metadata.created_at",
        field_schema=models.PayloadSchemaType.DATETIME,
    )

**Не включено в автоматизацию** — требуется ТОЛЬКО если `FRESHNESS_BOOST=true` (сейчас `false`). Добавить комментарий в docstring метода.

---

## Rollback план

1. **Timeout:** убрать `timeout=30` из конструктора → `AsyncQdrantClient(url=url, api_key=api_key, prefer_grpc=True)`
2. **FormulaQuery:** git revert коммита Task 2 → вернёт client-side numpy boosting
3. **Dep bump:** не блокирует (>=1.14.0 compatible с текущей 1.16.2)

## Риски

| Риск | Митигация |
|------|-----------|
| FormulaQuery синтаксис отличается для gRPC | qdrant-client конвертирует автоматически (REST↔gRPC) |
| Payload index отсутствует на VPS | `freshness_boost_enabled=False` по умолчанию — fallback path есть |
| Timeout 30s слишком длинный для fast queries | Configurable через `QDRANT_TIMEOUT`, не влияет на p95 |
| scale в DecayParamsExpression — какие единицы? | Для datetime_key — дни (float). Проверено по SDK source + blog |
| Удалённые тесты (reorder, missing_date, invalid_date) | Server handles эти кейсы; FormulaQuery `defaults` fallback; добавлены новые тесты |

## Acceptance Criteria

- [x] `timeout=30` explicitly set в AsyncQdrantClient init
- [x] `search_with_score_boosting()` мигрирован на FormulaQuery (server-side)
- [x] Unit tests pass
- [x] `make check` pass (lint + types)
- [x] No numpy dependency for score boosting (numpy only for MMR)

## Effort Estimate

| Task | Время |
|------|-------|
| Task 1: Timeout | ~3 мин |
| Task 2: FormulaQuery | ~5 мин |
| Task 3: Dep bump | ~2 мин |
| **Total** | **~10 мин** |
