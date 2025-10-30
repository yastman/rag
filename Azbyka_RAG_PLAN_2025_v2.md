
# Azbyka RAG — Современный план внедрения (2025, v2)
**Версия:** 2025-10-30  
**Цель:** Построить надёжную, экономичную и оценимую RAG-систему для портала «Азбука», отвечающую **только на основе предоставленных текстов** (книги/статьи/аннотации/описания авторов), со ссылками на источники и подсветкой цитат.

---

## 0. Жёсткие критерии проекта (SLO / KPI)
- **Качество:** >95% корректных ответов, <1% неверных (на test/small/full наборах).
- **Стоимость:** < **$1 / 1000 запросов** при прод-настройке (за счёт кэша и маршрутизации).
- **Надёжность:** error rate <1%, timeout rate <1%.
- **Скорость:** latency P95 ≤ целевого (задать по этапу; ориентир 800–1500 ms при кэше).
- **Нагрузка:** выдержка **100 одновременных запросов** и 1000 последовательных.
- **Безопасность:** 0% срабатываний на risk-наборе (prompt-injection, провокации, jailbreak).

---

## 1. Архитектура (высокоуровнево)
- **Ингест:** HTML → Markdown → чистый текст + метаданные (`author_id`, `book_id`, `section_id`, `book_type`, `branch`, `lang`).
- **Чанкинг:** структурный (по разделам/заголовкам), фиксированный (`size=400/600/800, overlap=50/100`), LLM‑контекстуальный (динамический).
- **Эмбеддинги:** CPU-дружелюбные (FRIDA, Giga-Embeddings-instruct) + бэйзлайн платные/локальные; версионирование `embedding_version`.
- **Хранилище:** Qdrant (несколько коллекций по языку/типу/ветке; canary‑индекс для миграций).
- **Ретривер:** гибрид BM25 + dense с RRF (или Weighted RRF); Top‑K авто-настройка; фильтры по метаданным.
- **Реранкер:** cross-encoder для Top‑M; **ColBERT** как фичефлаг (для сложных запросов).
- **Генерация:** локальные → OpenRouter → Gemini (fallback по цене/латентности/надёжности); температура 0–0.2.
- **Инструменты (Tools):** BibleTool (книга/глава/стих), SectionRetriever (полный раздел/диапазон чанков), AuthorTool (описание, список работ).
- **Наблюдаемость:** Langfuse (LLM/агенты) + OpenTelemetry → Prometheus/Loki/Grafana (системные метрики).
- **Говернанс:** MLflow (эксперименты + Model Registry с alias `Staging`/`Production`), версияция корпусов/конфигов (Hydra/DVC).

Диаграмма директорий:
```
azbyka-rag/
├─ src/
│  ├─ ingest/         # парсинг HTML→MD→TXT, нормализация
│  ├─ chunking/       # стратегии чанкинга
│  ├─ embeddings/     # обёртки моделей, кэш
│  ├─ retriever/      # BM25 + dense + RRF, фильтры
│  ├─ reranker/       # cross-encoder, ColBERT (фича)
│  ├─ llm/            # провайдеры, маршрутизация, политика ответов
│  ├─ tools/          # BibleTool, AuthorTool, SectionRetriever
│  ├─ eval/           # RAG-метрики, автозапуски
│  ├─ utils/          # логирование, OTEL, Langfuse, MLflow, Redis
│  └─ api/            # FastAPI/веб-контроллеры
├─ configs/           # Hydra: *.yaml для всех модулей/профилей
├─ data/              # исходники/подготовка (локально)
├─ docs/              # документация
├─ eval/              # датасеты test/small/full, golden-sets
├─ infra/             # docker-compose, grafana dashboards, prom rules
├─ scripts/           # запуск, снапшоты Qdrant, stress-test
└─ tests/             # pytest + e2e
```

---

## 2. Конфигурации и секреты
- **Hydra** для модульных конфигов: `ingest`, `chunking`, `embeddings`, `retriever`, `reranker`, `llm`, `tools`, `eval`, `cache`, `telemetry`.
- `.env.example` + секрет-менеджмент (локально `dotenv`, прод — Vault/Doppler).
- Профили: `dev`, `staging`, `prod`; для каждого — свои провайдеры/лимиты/квоты.

Пример `configs/retriever/hybrid.yaml`:
```yaml
retriever:
  type: hybrid
  dense:
    model: "giga-embeddings-instruct"
    top_k: 64
    index_version: "v1.2.0"
  bm25:
    analyzer: "ru_en"
    top_k: 64
  fusion:
    method: "rrf"
    k: 60              # RRF parameter
    weighted: false
  filters:
    author: null
    book_type: [1,2]   # 1=Эталон, 2=Обычный (3 исключить по умолчанию)
    lang: ["ru","cs","en"]
```

---

## 3. Чанкинг
- **Structure-first:** использовать заголовки/подзаголовки; хранить `section_path` для подсветки цитат и навигации.
- **Fixed:** `chunk_size={400,600,800}`, `overlap={50,100}`; параметры через Hydra.
- **LLM-contextual:** агрегация/расщепление по релевантности (включать фичефлагом на «тяжёлых» книгах).
- **Церковнославянский:** отдельная коллекция или транслитерация перед эмбеддингом.

---

## 4. Эмбеддинги и индексация
- Модели: **FRIDA**, **Giga-Embeddings-instruct**; базовые платные/локальные для сравнения.
- Пэйлоад в Qdrant: `embedding_version`, `source_id`, `book_type{1,2,3}`, `lang`, `branch`, `author_id`, `book_id`, `section_id`, `section_path`.
- **Коллекции:** по языку/ветке/типу источника; **canary** для миграций.
- **Снапшоты Qdrant:** nightly; совместимость в пределах **minor-версии**; playbook восстановления.

---

## 5. Ретривер, ранжирование и фильтры
- **Hybrid:** BM25 + dense; слияние через **RRF** (или Weighted RRF).
- **Top‑K адаптивный:** авто-расширение до K’ при низкой уверенности.
- **Reranker:** cross‑encoder (легковесный) для Top‑M документов.
- **ColBERT:** включать фичефлагом на сложных запросах (дороже по памяти/скорости).
- **Фильтры:** `author`, `book_type`, `book_id`, `section_id`, `branch`, `lang`.

---

## 6. Генерация и политика ответов
- Температура **0–0.2** для детерминизма; строгая инструкция «Отвечать только из контекста; если недостаточно — сказать „не знаю“».
- В выводе: **ссылки на источники + подсветка цитат** (offsets/section_path).
- Маршрутизация провайдеров: локальные → OpenRouter → Gemini (учёт цены/latency/надёжности).
- **User context:** «текущая книга/группа» добавляется в фильтры retriever и в system‑prompt.

---

## 7. Кэширование (многоуровневое)
- **L1:** in‑proc LRU (миллисекунды, малый объём).
- **L2:** Redis (общий на инстансы, AOF-персистентность).
- **Слои и TTL:**
  - **EMB:** `EMB:{model}:{text_hash}` — **30–90 дней**.
  - **ANN:** `ANN:{index_v}:{query_hash}:{filters_hash}` — **5–30 мин**.
  - **RERANK:** `RERANK:{reranker}:{query_hash}:{docset_hash}` — **5–30 мин**.
  - **LLMRESP (детермин.):** `LLM:{provider}:{model}:{prompt_hash}:{template_v}:{policy_v}:{lang}` — **5–60 мин**.
- **Версионирование ключей:** `index_v`, `template_v`, `policy_v`, `model`, `locale`, (персональные ответы — ещё и `user_id`).

---

## 8. Оценка качества (Eval First)
**Offline (nightly):**  
- **RAG-метрики:** Faithfulness, Answer Relevancy, Context Precision/Recall, Semantic Similarity, Utilization (сколько контекста использовано).  
- **Retrieval:** Recall@K, MRR, nDCG, Hit@K, Coverage.  
- **Regression gates:** релиз блокируется, если падение > заданного дельта‑порога.
**Online:**  
- A/B промптов/моделей, human‑feedback (👍/👎 + текст), анализ в дашбордах.

Артефакты и метрики логируются в **MLflow**; трассировка каждого шага — в **Langfuse**.

---

## 9. Наблюдаемость и логирование
- **Langfuse:** traces/spans для agent-пайплайна (embed → search → rerank → generate), учёт `tokens`, `cost_usd`, `latency_ms`, флаги `cache_hit`.
- **OpenTelemetry → Prometheus/Loki/Grafana:** системные метрики (CPU/GPU/RAM, диск, сетевые, RPS, P50/P95 latency, queue size, error rate, evictions Redis).  
- **MLflow:** эксперименты, артефакты, **Model Registry** (alias `Staging`/`Prod`, промо/откат).

---

## 10. Безопасность и риски
- Политика модерации контента и отказов (PII-редакция до логирования).
- **Red-team агент** (prompt injection, провокационные вопросы, jailbreak).
- **Rate limiting** и защита от спама/перегрузок.
- Секреты — вне Git; ротация ключей (30/60 дней).

---

## 11. Стоимость и производительность
- **Семантический кэш** (near-duplicate запросы) для FAQ.
- Маршрутизация по цене/latency; лимиты токенов/бюджетов по провайдерам.
- Профилирование горячих путей (retriever/reranker); CPU‑friendly по умолчанию, GPU/платные — под пики.

---

## 12. DR / Qdrant снапшоты
- **Nightly snapshots** всех коллекций; хранение 7–14 дней.
- Восстановления совместимы в пределах **minor‑версии**; проверка на canary‑кластер/коллекцию.
- Скрипты: `scripts/qdrant_snapshot.sh`, `scripts/qdrant_restore.sh`; README с пошаговой инструкцией.

---

## 13. План внедрения по неделям (DoD на каждый этап)

### Week 1 — Initial Setup
**Задачи:**
- Репозиторий/структура; Hydra для всех модулей; `.env.example` + секреты.
- Langfuse + OTEL + Prometheus/Loki/Grafana (базовые дашборды).
- MLflow: Experiment Tracking + Model Registry.
- Redis L1/L2 кэш; JSON‑логи (trace_id, user_id).
- Базовый ingestion (HTML→MD→TXT+метаданные); E2E минимальный поток.
**DoD:** локальный запуск, корректный ответ на эталон, базовые графы в Grafana.

### Week 2 — Chunking/Embeddings/Eval v1
**Задачи:**
- 3 стратегии чанкинга; сравнение FRIDA/Giga; Qdrant с `embedding_version`.
- Hybrid retriever (BM25 + dense + RRF); test‑dataset (30–50 вопросов, 3–5 книг).
- Автооценка (RAG‑метрики) nightly; лог в MLflow; трассы в Langfuse.
**DoD:** ≥90% корректных, <5% неверных; стабильные метрики в истории.

### Week 3 — Quality Tuning (small set) + цитаты
**Задачи:**
- Реранкер (cross‑encoder), фича **ColBERT** на сложные запросы.
- Ссылки на источники + подсветка цитат (offsets/section_path).
- Повторная оценка на 100+ вопросах.
**DoD:** >95% корректных, <1% неверных (small set).

### Week 4 — Full dataset & Tools
**Задачи:**
- Препроцессинг 11 GB; фильтр языка; отдельная коллекция/транслит для церковнославянского.
- Полная индексация; несколько коллекций; canary‑индекс.
- BibleTool/AuthorTool/SectionRetriever; трассировка tool‑calls.
- Fallback-маршрутизация LLM (local → OpenRouter → Gemini).
**DoD:** стабильные ответы на полном наборе; защиты от injections включены.

### Week 5 — Cost & Stability
**Задачи:**
- Нагрузочные тесты: 100 concurrent, 1000 последовательных (Locust/k6).
- Redis‑кэш: EMB 30–90д; ANN/RERANK 5–30мин; LLMRESP 5–60мин (deterministic).
- Langfuse: `cache_hit`, `saved_cost_usd`, `saved_latency_ms` (сравнение с baseline).
- Security: rate‑limit, модерация; red-team.
- Qdrant snapshots/restore (проверка совместимости minor).
**DoD:** < $1 / 1K запросов при >95% точности; стресс‑тест выдержан.

### Week 6 — Website Integration & UX
**Задачи:**
- Веб-чат UI: ссылки, подсветка, **фидбек (👍/👎 + текст)** → внутр. БД; модерация.
- Пользовательский контекст (открытая книга/группа) в фильтры и system‑prompt.
- SLA-алерты (Telegram/email): latency/error-rate/квоты.
- Бэкапы: Qdrant + конфиги; Runbook/rollback.
**DoD:** прод запущен, фидбек собирается, алерты работают.

### Week 7 — Public Release & SLA
**Задачи:**
- Недельные отчёты (качество/стоимость/латентность/фидбек).
- Техдолг/улучшения 1.1 (тонкая настройка retriever/reranker, автопополнение датасета).
**DoD:** 48+ часов стабильной работы по SLA.

---

## 14. Release Checklist (кратко)
- [ ] Все тесты (unit/e2e) зелёные; регресс‑гейты пройдены
- [ ] Дашборды Grafana показывают реальное потребление/латентность/ошибки
- [ ] Qdrant снапшоты протестированы (restore на canary)
- [ ] Конфиги Hydra зафиксированы (tags/versions), MLflow Model Registry промо → `Production`
- [ ] Документация: Setup/Usage/Tuning, Tool API, Runbook/rollback

---

## 15. Runbook (инциденты, откат, смена модели)
- **Симптомы:** рост latency P95, рост error rate, падение hit‑rate кэша, деградация RAG‑метрик.
- **Диагностика:** Grafana панели (LLM/агент/системные), Langfuse трассы, MLflow прогон последнего релиза.
- **Действия:** промо предыдущей модели (Model Registry), сброс проблемного кэша/индекса (по `index_v`), throttle/лимиты, перевести трафик на fallback LLM.
- **Коммуникация:** алерты → Telegram/email; запись инцидента в docs/INCIDENTS.md.

---

## 16. Приложения
**A. Фильтры и политика «только из контекста»**  
- `book_type`: 1=Эталон, 2=Обычный, 3=Сомнительный (по умолчанию исключаем 3, если явно не запрошен).
- Если **нет достаточного evidence** (низкая уверенность retriever/реранкер), ответ: «Не знаю. Уточните, пожалуйста…».

**B. Ключи кэша (примеры)**
```
EMB:{model}:{text_hash}
ANN:{index_v}:{query_hash}:{filters_hash}
RERANK:{reranker}:{query_hash}:{docset_hash}
LLM:{provider}:{model}:{prompt_hash}:{template_v}:{policy_v}:{lang}
```

**C. Мини-метрики для трёх экранов Grafana**
- *LLM/Agent:* tokens/input|output, cost_usd, span latency p50/p95, cache_hit, saved_latency_ms.
- *Системные:* CPU/GPU/RAM, I/O, RPS, queue size, Redis mem/evictions, error rate.
- *Качество:* Faithfulness, Relevancy, Context Precision/Recall, MRR, Recall@K (nightly).

---

**Готово.** План можно брать как **рабочий документ** и расширять разделами Implementation/Code Samples (docker-compose, Hydra, eval.py и т.д.) при необходимости.
