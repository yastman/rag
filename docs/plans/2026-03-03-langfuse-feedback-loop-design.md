# Langfuse Feedback Loop & Quality Improvement — Design Document

**Дата:** 2026-03-03
**Ветка:** `worktree-langfuse-feedback-audit`
**Статус:** Draft → Awaiting Approval

---

## 1. Цель

Построить полный feedback loop для RAG-бота: от сбора обратной связи пользователей до
автоматизированного улучшения качества ответов.

**Текущее состояние:** 👍/👎 кнопки пишут `user_feedback` score (0/1) в Langfuse, но
нет ответа на "ПОЧЕМУ плохо" и нет workflow для работы с плохими ответами.

**Целевое состояние:**
```
User 👎 + причина → Langfuse score → Annotation Queue → Expert review
→ Correction → Dataset → Experiment → Prompt improvement → Deploy
```

---

## 2. Контекст и исследование

### 2.1 Текущая интеграция Langfuse (аудит 17 файлов)

| Компонент | Файл | Статус |
|-----------|------|--------|
| Инициализация | `telegram_bot/observability.py:333-339` | ✅ Singleton, PII mask, flush_at=50 |
| Tracing (55+ spans) | Все nodes/services | ✅ Curated I/O, bloat prevention |
| 30+ RAG scores | `telegram_bot/scoring.py` | ✅ latency, cache, confidence... |
| 3 LLM-as-Judge | Langfuse managed evaluators | ✅ faithfulness, relevance, context |
| Feedback 👍/👎 | `telegram_bot/feedback.py`, `bot.py:3150-3207` | ⚠️ Только 0/1, нет причины |
| Prompt management | `telegram_bot/integrations/prompt_manager.py` | ✅ TTL cache, fallback |
| Datasets | `scripts/export_traces_to_dataset.py` | ⚠️ Баг: field mapping mismatch |
| Baseline | `tests/baseline/` | ✅ thresholds.yaml + compare |

### 2.2 Найденные пробелы

**Критические (блокируют feedback loop):**
1. Feedback без причины — `bot.py:3180` пишет только `comment=f"user_id:{user_id}"`
2. Нет Environments — prod/staging/dev traces в одной куче
3. Нет Score Configs — 50+ scores без типизации в Langfuse UI
4. Observation-level evals не настроены (доступны с v3.153, Feb 2026)

**Важные (нужны для improvement loop):**
5. Нет Annotation Queues — dislike-и "пропадают"
6. Нет Corrections — нельзя записать правильный ответ
7. Нет Implicit feedback — retry/reformulation не детектируются
8. Dataset export баг — `retrieved_context` vs `eval_docs` mismatch (`export_traces_to_dataset.py:99`)
9. Нет agent trajectory evaluation — tool routing не проверяется
10. Нет Judge calibration — LLM-judge не сверяется с human feedback

**Quality of life:**
11. 5 env vars не в `.env.example`
12. Legacy `integrations/langfuse.py` не удалён (мёртвый код)
13. `hyde_used=0.0` заглушка в scoring.py:80
14. Trace contract неполный — нет `user_feedback`, `hitl_action`
15. Prompt version не логируется в spans
16. Нет graceful shutdown hook
17. `flush_at`/`flush_interval` hardcoded, не через env vars

### 2.3 Новые возможности Langfuse (2025-2026)

| Фича | Дата | Релевантность |
|------|------|--------------|
| Annotation Queues API | Mar 2025 | Автоматическая маршрутизация dislike → queue |
| Sessions in Annotation Queues | Jul 2025 | Human review всего диалога |
| Evaluator Library (RAGAS) | May 2025 | Prebuilt evaluators из коробки |
| Python SDK v3 GA (OTel) | Jun 2025 | Основа для observation-level evals |
| Experiment Runner SDK | Sep 2025 | High-level API для экспериментов |
| Score Analytics | Nov 2025 | Cohen's Kappa — judge vs human |
| Native MCP Server | Nov 2025 | Claude Code читает/пишет промпты |
| Batch Add to Datasets | Dec 2025 | Быстрое создание test sets из prod |
| Dataset Versioning | Dec 2025 | Воспроизводимость экспериментов |
| Corrected Outputs | Jan 2026 | Diff view: actual vs expected |
| Observation-Level Evals | Feb 2026 | Judge отдельные spans (retrieve/generate) |
| Scores API v2 Filtering | Feb 2026 | Metadata + observation фильтры |
| Official CLI | Feb 2026 | `npx langfuse-cli` — полный API |
| Prompt Improvement Workflow | Feb 2026 | Claude + annotations → prompt fixes |
| Agent Skill Evaluation | Feb 2026 | Tool routing correctness |
| Webhooks (roadmap) | Q2 2026 | Auto-alert на events (заменит cron) |

### 2.4 Best Practices (industry research)

**Источники:** DoorDash Simulation Flywheel, TheyDo Quality Flywheel, Jason Liu (jxnl.co),
Langfuse RAG Observability blog, Langfuse Evaluation Roadmap blog, Merck case study.

**Ключевые принципы:**
- "Fix the measurement before fixing the model" (Jason Liu)
- Один evaluator = одна failure mode (Langfuse)
- Thumbs-down без категории почти бесполезен (TheyDo)
- Калибровать judge vs human: TPR и TNR > 90% (Langfuse)
- Начать с observability → error analysis → automated eval → testing (Langfuse roadmap)
- Prompt improvement: 10% → 70% quality за 2-3 iteration с Claude (Langfuse blog)

**Таксономия причин для RAG (3 bucket'a из OptyxStack):**
- **A: Recall failure** — не нашли правильный документ
- **B: Ranking failure** — нашли, но не попало в top-k
- **C: Generation failure** — контекст ок, ответ плохой

---

## 3. Архитектура решения

### 3.1 Feedback Flow (целевой)

```
Telegram User
     │
     ▼
[Ответ бота + 👍/👎 кнопки]
     │
     ├── 👍 → score(user_feedback=1) → done
     │
     └── 👎 → [6-category inline keyboard]
              │
              ├── "Не по теме"      → fb:0:wt:{tid}
              ├── "Нет информации"   → fb:0:mi:{tid}
              ├── "Плохие источники" → fb:0:bs:{tid}
              ├── "Выдумал факты"    → fb:0:ha:{tid}
              ├── "Неполный ответ"   → fb:0:ic:{tid}
              └── "Плохой формат"    → fb:0:fm:{tid}
                       │
                       ▼
              Langfuse Scores:
              ├── user_feedback = 0 (NUMERIC)
              ├── user_feedback_reason = "hallucination" (CATEGORICAL)
              └── comment = user context
                       │
                       ▼
              [Auto-triage script (cron daily)]
              ├── Fetch dislike traces via Scores API v2
              ├── Add to Annotation Queue (via API)
              └── Alert if spike > 15% dislike rate → Telegram admin
```

### 3.2 Implicit Feedback Detection

```
handle_query()
     │
     ├── Compute embedding(current_query)
     ├── Compare with embedding(previous_query) in session
     │
     ├── cosine_similarity > 0.7 AND time_delta < 60s
     │   └── score(implicit_retry=1) ← user переформулировал
     │
     └── session_turns > median × 2
         └── score(implicit_long_session=1) ← потенциально не доволен
```

### 3.3 Review Pipeline

```
Annotation Queue (Langfuse UI)
     │
     ├── Queue "dislike-review" — traces с user_feedback=0
     ├── Queue "low-judge" — traces с judge_faithfulness < 0.5
     │
     ▼
Expert Review Workflow:
     1. Открыть trace в Langfuse UI
     2. Проставить root cause: Recall / Ranking / Generation
     3. Написать Correction (правильный ответ)
     4. Добавить Comment с анализом
     │
     ▼
Dataset Building:
     - Trace → Dataset Item (via UI или batch API)
     - input: original query
     - expected_output: correction
     - metadata: {reason, root_cause, original_trace_id}
```

### 3.4 Experiment & Improvement Loop

```
Dataset (versioned)
     │
     ▼
Experiment Runner SDK:
     ├── Run current prompt vs dataset
     ├── Run candidate prompt vs dataset
     │
     ▼
LLM-as-Judge (observation-level):
     ├── Retrieval span → context_relevance score
     ├── Generate span → faithfulness score
     ├── Generate span → answer_relevance score
     │
     ▼
Score Analytics:
     ├── Compare experiment runs
     ├── Cohen's Kappa: judge vs human annotations
     ├── Regression detection vs baseline
     │
     ▼
Prompt Update:
     ├── Claude + Langfuse CLI → analyze annotations → propose fix
     ├── Update prompt in Langfuse Prompt Management
     ├── Label: staging → test → production
     └── Monitor deployment via Score Analytics trends
```

### 3.5 Agent Evaluation (tool routing)

```
Dataset "agent-routing":
     ├── {"query": "Квартиры на Подоле", "expected_tool": "apartment_search"}
     ├── {"query": "Что такое ипотека?", "expected_tool": "rag_search"}
     ├── {"query": "Создай задачу в CRM", "expected_tool": "crm_create_task"}
     │
     ▼
Experiment:
     ├── Run query through agent
     ├── Capture trajectory (tool call sequence)
     ├── Compare: actual_tool vs expected_tool
     ├── Score: tool_routing_accuracy
     │
     ▼
Regression Prevention:
     └── Run before each prompt/model change
```

---

## 4. Score Configs (стандартизация)

### 4.1 Feedback Scores

| Name | Data Type | Values | Description |
|------|-----------|--------|-------------|
| `user_feedback` | NUMERIC | 0.0 / 1.0 | User like/dislike |
| `user_feedback_reason` | CATEGORICAL | `wrong_topic`, `missing_info`, `bad_sources`, `hallucination`, `incomplete`, `formatting` | Причина dislike |
| `implicit_retry` | BOOLEAN | true/false | Query reformulation detected |
| `implicit_long_session` | BOOLEAN | true/false | Unusually long session |

### 4.2 RAG Quality Scores

| Name | Data Type | Range | Description |
|------|-----------|-------|-------------|
| `judge_faithfulness` | NUMERIC | 0.0–1.0 | Ответ основан на контексте |
| `judge_answer_relevance` | NUMERIC | 0.0–1.0 | Ответ отвечает на вопрос |
| `judge_context_relevance` | NUMERIC | 0.0–1.0 | Документы релевантны вопросу |
| `confidence_score` | NUMERIC | 0.0–1.0 | Grade confidence |

### 4.3 Performance Scores

| Name | Data Type | Description |
|------|-----------|-------------|
| `latency_total_ms` | NUMERIC | E2E wall-time |
| `llm_ttft_ms` | NUMERIC | Time to first token |
| `llm_tps` | NUMERIC | Tokens per second |
| `results_count` | NUMERIC | Retrieved documents count |

### 4.4 Agent Scores

| Name | Data Type | Values | Description |
|------|-----------|--------|-------------|
| `agent_tool_selected` | CATEGORICAL | rag_search, apartment_search, crm_*, direct | Выбранный tool |
| `tool_routing_correct` | BOOLEAN | true/false | Правильность маршрутизации |

---

## 5. Environment Configuration

```
production  → боевой бот (Telegram)
staging     → тестовый бот
development → локальная разработка
load-test   → нагрузочные тесты
ci          → CI pipeline traces
```

Реализация: `LANGFUSE_TRACING_ENVIRONMENT` env var в каждом deployment.

---

## 6. Production Hardening

### 6.1 Из Production Checklist

| Item | Текущее | Целевое |
|------|---------|---------|
| Graceful shutdown | ❌ | `atexit` + `signal.signal(SIGTERM)` → `langfuse.shutdown()` |
| flush config | Hardcoded 50/5 | `LANGFUSE_FLUSH_AT`, `LANGFUSE_FLUSH_INTERVAL` env vars |
| requestTimeout | Не задано | `LANGFUSE_TIMEOUT=15000` |
| Trace URL logging | Частично | `logger.info(f"trace_id={tid}")` в каждом entry point |

### 6.2 Cleanup

| Item | Действие |
|------|----------|
| `integrations/langfuse.py` | Удалить (мёртвый v2 код) |
| `scoring.py:80` `hyde_used=0.0` | Удалить заглушку |
| `trace_contract.yaml` | Добавить `user_feedback`, `hitl_action`, `supervisor_model`, `user_role` |
| `.env.example` | Добавить 5 недокументированных vars |
| `ENABLE_LANGFUSE` в settings.py | Интегрировать с `observability.py` или удалить |

### 6.3 Fix Bugs

| Баг | Файл:строка | Fix |
|-----|------------|-----|
| Dataset export: `retrieved_context` vs `eval_docs` | `export_traces_to_dataset.py:99-100` | Поменять на `eval_docs` |
| Dataset export: нет dedup | `export_traces_to_dataset.py:209-223` | Добавить `source_trace_id` dedup |
| Dataset export: `create_dataset()` без idempotency | `export_traces_to_dataset.py:206` | Добавить try/except |
| Goldset: `question` vs `query` key mismatch | `goldset_sync.py:52` | Унифицировать на `query` |
| Baseline: `cache_hit` всегда 0 для client_direct | `collector.py:144-150` | Читать из score `semantic_cache_hit` |
| Baseline: judge scores не в compare | `collector.py` | Добавить `api.scores.list()` агрегацию |
| Prompt version не в span output | `prompt_manager.py:58-60` | Добавить `prompt_version` |

---

## 7. Observation-Level Evaluators (настройка)

Используем managed evaluators Langfuse (доступны с v3.153):

| Evaluator | Target | Filter | Variables |
|-----------|--------|--------|-----------|
| `faithfulness` | Observation `node-generate` | `name="node-generate"` | `eval_query` → query, `eval_answer` → output, `eval_context` → context |
| `answer_relevance` | Observation `node-generate` | `name="node-generate"` | `eval_query` → query, `eval_answer` → output |
| `context_relevance` | Observation `node-retrieve` | `name="node-retrieve"` | `eval_query` → query, `eval_docs` → context |

Sampling: 20-30% traces для cost management.

Observation type: изменить `node-retrieve` с `span` на `retriever` для семантической маркировки.

---

## 8. Alerting

### 8.1 Cron-based (до появления webhooks)

```python
# scripts/langfuse_alert.py — запуск раз в час
# 1. Fetch scores за последний час через Scores API v2
# 2. Вычислить dislike rate
# 3. Если > 15% (мин 20 запросов) → alert в Telegram admin chat
# 4. Если judge_faithfulness mean < 0.5 → alert
# 5. Утренний дайджест в 9:00: dislike rate, latency p95, cache hit rate
```

### 8.2 Future: Webhooks (когда выйдут)

```
Webhook: score.created WHERE name="user_feedback" AND value=0
  → Auto-add trace to Annotation Queue

Webhook: evaluation.completed WHERE score < 0.5
  → Alert в Telegram admin chat
```

---

## 9. Дорожная карта реализации

### Фаза 1: Foundation (6-8h)

| Task | Effort | Файлы |
|------|--------|-------|
| Добавить `LANGFUSE_TRACING_ENVIRONMENT` | 1h | `observability.py`, `.env.example` |
| Создать Score Configs через Langfuse API (скрипт) | 2h | `scripts/setup_score_configs.py` (новый) |
| Graceful shutdown hook | 30min | `observability.py` |
| Вынести flush config в env vars | 30min | `observability.py`, `.env.example` |
| Удалить legacy `integrations/langfuse.py` | 15min | |
| Удалить `hyde_used` заглушку | 15min | `scoring.py` |
| Обновить trace contract | 30min | `tests/observability/trace_contract.yaml` |
| Добавить 5 env vars в `.env.example` | 15min | `.env.example` |
| Добавить `prompt_version` в span output | 30min | `prompt_manager.py` |
| Observation type `retriever` для retrieve spans | 1h | `retrieve.py` / graph nodes |
| Trace URL logging в entry points | 30min | `bot.py` |

### Фаза 2: Rich Feedback (8-12h)

| Task | Effort | Файлы |
|------|--------|-------|
| 2-step feedback: 👎 → 6-category keyboard | 4h | `feedback.py`, `bot.py` |
| Обработка category callback + score writing | 2h | `bot.py:handle_feedback` |
| Implicit retry detection (embedding similarity) | 4h | `bot.py:handle_query`, новый модуль |
| Implicit long session detection | 1h | `bot.py` |
| Тесты на feedback + implicit signals | 2h | `tests/unit/test_feedback_handler.py` |

### Фаза 3: Review Pipeline (10-14h)

| Task | Effort | Файлы |
|------|--------|-------|
| Скрипт auto-triage: dislike → Annotation Queue | 4h | `scripts/langfuse_triage.py` (новый) |
| Alert скрипт (cron hourly) | 3h | `scripts/langfuse_alert.py` (новый) |
| Prompt Improvement Workflow документация | 2h | `docs/guides/prompt-improvement.md` |
| Настройка Annotation Queues в Langfuse UI | 1h | UI config |
| Настройка Score Configs для annotation dimensions | 1h | UI config |
| Установка Langfuse CLI (`npx langfuse-cli`) | 30min | Makefile |
| Тесты на triage скрипт | 2h | `tests/unit/` |

### Фаза 4: Experiment Loop (10-14h)

| Task | Effort | Файлы |
|------|--------|-------|
| Fix dataset export (field mapping, dedup, idempotency) | 3h | `export_traces_to_dataset.py` |
| Fix goldset sync (key unification) | 1h | `goldset_sync.py` |
| Fix baseline collector (cache_hit, judge scores) | 2h | `tests/baseline/collector.py` |
| Agent trajectory evaluation dataset + experiment | 4h | `scripts/eval/` (новый) |
| Dev/Test dataset split через tags | 1h | Dataset config |
| Versioned dataset experiments | 1h | Experiment config |
| Настройка observation-level evaluators в Langfuse | 2h | UI config + verify |

### Фаза 5: Monitoring (6-8h)

| Task | Effort | Файлы |
|------|--------|-------|
| Judge calibration: Score Analytics setup | 2h | UI config |
| Утренний дайджест (dislike rate, latency, cache) | 2h | `scripts/langfuse_alert.py` |
| Сравнение human vs judge (Cohen's Kappa analysis) | 2h | `scripts/eval/calibrate_judge.py` (новый) |
| Dashboard в Langfuse UI | 1h | UI config |

### Фаза 6: Automation (future, TBD)

| Task | Trigger |
|------|---------|
| Webhooks → auto-queue routing | Когда Langfuse выпустит observability webhooks |
| Synthetic dataset generation | Когда golden set > 100 items |
| Auto-prompt suggestions через Claude | После 3+ iteration manual workflow |

---

## 10. Метрики успеха

| Метрика | Baseline (сейчас) | Target (после) |
|---------|-------------------|----------------|
| Dislike rate | Неизвестен (нет analytics) | < 10% |
| Dislike с причиной | 0% | 100% dislike-ов |
| Среднее время triage | ∞ (не делается) | < 1h/week |
| Golden dataset size | ~0 quality items | 100+ items |
| Judge-Human agreement | Неизвестен | Cohen's κ > 0.6 |
| Observation-level eval coverage | 0% | 30% traces |
| Prompt improvement iterations | 0 | 2-3/month |
| Time to detect quality drop | ∞ | < 1 hour |

---

## 11. Риски и митигации

| Риск | Вероятность | Митигация |
|------|------------|-----------|
| Пользователи не нажимают 👎+причину (friction) | Высокая | 6 одно-нажатных кнопок, без текстового ввода |
| Мало dislike-данных для анализа | Средняя | Implicit feedback как дополнение |
| LLM-judge не коррелирует с human | Средняя | Калибрация через Score Analytics |
| Self-hosted Langfuse тормозит на analytics | Низкая | ClickHouse bloom indexes, query optimization |
| Annotation Queue overflow | Низкая | Auto-triage + приоритизация по frequency |

---

## 12. Dependencies

- Langfuse v3.153+ (observation-level evals) — ✅ уже доступен
- Python SDK v3+ (OTel) — проверить текущую версию
- Langfuse CLI (`npx langfuse-cli`) — install
- Node.js для `npx` — проверить наличие
- Annotation Queues API — доступен с Mar 2025

---

## 13. Sources

- [Langfuse User Feedback docs](https://langfuse.com/docs/observability/features/user-feedback)
- [Langfuse Annotation Queues](https://langfuse.com/docs/evaluation/evaluation-methods/annotation-queues)
- [Langfuse Datasets](https://langfuse.com/docs/datasets/overview)
- [Langfuse Observation-Level Evals](https://langfuse.com/changelog/2026-02-13-observation-level-evals)
- [Langfuse Score Analytics](https://langfuse.com/docs/evaluation/evaluation-methods/score-analytics)
- [Langfuse Corrections](https://langfuse.com/docs/observability/features/corrections)
- [Langfuse Environments](https://langfuse.com/docs/observability/features/environments)
- [Langfuse CLI](https://langfuse.com/changelog/2026-02-17-langfuse-cli)
- [Langfuse Prompt Improvement with Claude](https://langfuse.com/blog/2026-02-16-prompt-improvement-claude-skills)
- [Langfuse Evaluating Agent Skills](https://langfuse.com/blog/2026-02-26-evaluate-ai-agent-skills)
- [Langfuse RAG Observability and Evals](https://langfuse.com/blog/2025-10-28-rag-observability-and-evals)
- [Langfuse Evaluation Roadmap](https://langfuse.com/blog/2025-11-12-evals)
- [Langfuse Automated Evaluations](https://langfuse.com/blog/2025-09-05-automated-evaluations)
- [Langfuse Scaling](https://langfuse.com/self-hosting/configuration/scaling)
- [Langfuse Production Checklist](https://playbooks.com/skills/jeremylongshore/claude-code-plugins-plus-skills/langfuse-prod-checklist)
- [Merck Case Study](https://langfuse.com/customers/merckgroup)
- [ClickHouse + Langfuse Architecture](https://clickhouse.com/blog/langfuse-llm-analytics)
- [DoorDash Simulation Flywheel](https://careersatdoordash.com/blog/doordash-simulation-evaluation-flywheel-to-develop-llm-chatbots-at-scale/)
- [TheyDo AI Quality Flywheel](https://www.theydo.com/blog/articles/building-the-ai-quality-flywheel-how-theydo-turns-user-feedback-into-better-ai)
- [Jason Liu: Systematically Improving RAG](https://jxnl.co/writing/2025/01/24/systematically-improving-rag-applications/)
- [Seven Failure Points in RAG (arXiv)](https://arxiv.org/abs/2401.05856)
