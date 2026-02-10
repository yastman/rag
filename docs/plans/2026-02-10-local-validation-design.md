# Local Validation: Rebuild Bot + Capture Traces

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Убедиться что бот работает локально после merge в main (streaming, latency phase 2, rewrite control), собрать трейсы в Langfuse.

**Architecture:** Поднимаем Docker bot profile локально, прогоняем smoke-тест вручную, проверяем трейсы в Langfuse, затем запускаем E2E runner (25 сценариев).

**Tech Stack:** Docker Compose (bot profile), Telegram, Langfuse, Telethon (E2E)

---

### Task 1: Поднять Docker bot stack

**Files:**
- Check: `docker-compose.dev.yml`
- Check: `.env`

**Step 1: Убедиться что .env содержит нужные переменные**

```bash
grep -E "TELEGRAM_BOT_TOKEN|CEREBRAS_API_KEY|LANGFUSE_" .env | head -10
```

Expected: ключи заданы (не пустые).

**Step 2: Поднять bot profile**

```bash
make docker-bot-up
```

Expected: `docker compose --profile bot up -d` стартует сервисы.

**Step 3: Дождаться healthy**

```bash
docker compose -f docker-compose.dev.yml ps
```

Expected: все контейнеры `healthy` или `running` (postgres, redis, qdrant, bge-m3, litellm, bot).

**Step 4: Проверить логи бота**

```bash
docker logs --tail 30 dev-bot
```

Expected: `Preflight checks passed`, бот стартовал без ошибок. Новые env defaults работают:
- `MAX_REWRITE_ATTEMPTS=1`
- `GENERATE_MAX_TOKENS=2048`
- `STREAMING_ENABLED=true`

---

### Task 2: Smoke-тест через Telegram

**Ручной тест — отправить боту в Telegram:**

**Step 1: /start**

Отправить `/start` боту. Expected: приветственное сообщение с доменом.

**Step 2: RAG-запрос**

Отправить: `Какие квартиры в Несебре?`

Expected:
- Видны edit_text обновления (streaming — текст появляется порциями)
- Финальный ответ с Markdown форматированием
- Ответ содержит релевантную информацию

**Step 3: /stats**

Отправить `/stats`. Expected: статистика кеша (hit rates по тирам).

**Step 4: Проверить логи**

```bash
docker logs --tail 50 dev-bot
```

Expected: нет ошибок, видны node spans (classify, retrieve, grade, generate, respond).

---

### Task 3: Проверить Langfuse трейсы

**Step 1: Открыть Langfuse UI**

URL: `http://localhost:3001` (если Langfuse поднят локально) или VPS Langfuse.

**Step 2: Найти трейс от smoke-запроса**

Проверить что трейс содержит:
- Node spans: `node-classify`, `node-cache-check`, `node-retrieve`, `node-grade`, `node-generate`, `node-respond`
- Scores: `latency_total_ms`, `semantic_cache_hit`, `search_results_count`, `rerank_applied`
- `response_sent=true` (streaming доставил ответ)

**Step 3: Записать trace ID**

Сохранить trace ID для сравнения с проблемным трейсом `c2b95d86aa1f643b79016dd611c4691f` из #105.

---

### Task 4: Проверить E2E runner работает

**Files:**
- Check: `scripts/e2e/runner.py`
- Check: `scripts/e2e/test_scenarios.py`
- Check: `.env` (TELEGRAM_API_ID, TELEGRAM_API_HASH, E2E_BOT_USERNAME)

**Step 1: Проверить E2E env vars**

```bash
grep -E "TELEGRAM_API_ID|TELEGRAM_API_HASH|E2E_BOT_USERNAME" .env
```

Expected: все три заданы. Если нет — добавить из https://my.telegram.org.

**Step 2: Установить E2E зависимости**

```bash
make e2e-install
```

Expected: `uv sync --group e2e` — Telethon и зависимости установлены.

**Step 3: Dry run — один сценарий**

```bash
uv run python scripts/e2e/runner.py --scenario 1.1
```

Expected: один тест проходит (команда `/start`), результат PASS/FAIL.

**Step 4: Если сломано — дебажить**

Частые проблемы:
- `TELEGRAM_API_ID not set` → добавить в `.env`
- `FloodWaitError` → подождать, уменьшить `between_tests_delay`
- `AuthKeyError` → удалить сессию Telethon, перелогиниться

---

### Task 5: Полный E2E прогон

**Step 1: Запустить все 25 сценариев**

```bash
make e2e-test
```

Expected: runner прогоняет все сценарии, генерирует отчёт.

**Step 2: Проверить отчёт**

```bash
ls -la reports/e2e_*.json reports/e2e_*.html
```

Открыть HTML отчёт, проверить:
- Pass rate >= 80%
- Avg score
- Какие тесты упали и почему

**Step 3: Проверить трейсы в Langfuse**

25 трейсов должны появиться. Проверить:
- `latency_total_ms` — разброс значений
- `rerank_applied` — true/false корректно
- Нет rewrite-циклов > 1 (MAX_REWRITE_ATTEMPTS=1)
- Streaming работает (response_sent=true)

---

### Task 6: Go/No-Go отчёт

**Step 1: Сравнить с проблемным трейсом**

Проблемный трейс из #105: `c2b95d86aa1f643b79016dd611c4691f`

Проверить:
- [ ] `latency_total_ms` корректный (не NaN, не отрицательный)
- [ ] Нет ложных rewrite-циклов (grade не отправляет на rewrite при relevance > 0.3)
- [ ] `rerank_applied` корректно отражает skip_rerank logic
- [ ] Node-level latency stages записаны

**Step 2: Решение**

- **Баги воспроизводятся** → идём фиксить #107 → #108 → #109
- **Баги НЕ воспроизводятся** → закрываем #105/#107/#108/#109 с evidence (trace IDs)
- **Частично** → сужаем scope оставшихся issues

**Step 3: Записать результат**

Обновить issue #110 с результатами:

```bash
gh issue comment 110 --body "## Validation Results\n\n- Traces: [IDs]\n- Pass rate: X%\n- Reproducible: yes/no\n- Next: ..."
```
