# Production Agents Video — Ideas & Implementation Plan

Источник: [docs/video-notes/2026-02-13-prod-agents-part2.md](../video-notes/2026-02-13-prod-agents-part2.md)
Видео: LMST.ru — Production-Ready AI Agents (Part 2)

## Gap Analysis

| Тема из видео | Статус в проекте | GitHub Issue |
|---------------|-----------------|-------------|
| Source attribution (цитаты в ответах) | Partial — metadata есть, не показываем | [#225](https://github.com/yastman/rag/issues/225) |
| Prompt injection defense | Missing — вход идёт напрямую в LLM | [#226](https://github.com/yastman/rag/issues/226) |
| Content filtering (токсичность) | Missing — нет фильтрации | [#227](https://github.com/yastman/rag/issues/227) |
| Human-in-the-Loop | Missing — нет approval flows | [#228](https://github.com/yastman/rag/issues/228) |
| User feedback (лайк/дизлайк) | Missing — нет кнопок обратной связи | [#229](https://github.com/yastman/rag/issues/229) |
| LLM-as-Judge online eval | Missing — только offline RAGAS | [#230](https://github.com/yastman/rag/issues/230) |
| MCP server для инструментов | Missing — tools hardcoded | [#232](https://github.com/yastman/rag/issues/232) |
| Dataset management from traces | Partial — есть query sets, нет annotation workflow | [#233](https://github.com/yastman/rag/issues/233) |
| Graph RAG integration | Partial — LightRAG есть, не подключён | [#234](https://github.com/yastman/rag/issues/234) |

## Уже хорошо реализовано

| Тема | Детали |
|------|--------|
| Observability/Tracing | Langfuse v3, 35 traced ops, 14 scores, curated spans, error tracking |
| Vector DB (Qdrant) | Hybrid search RRF + ColBERT, gRPC, batch, group_by, quantization |
| Offline Evaluation | RAGAS (faithfulness >= 0.8), MLflow, baseline regression detection |
| PII Masking | phones, emails, tax IDs, passports в `src/security/pii_redaction.py` |
| Rate Limiting | TTL-based throttling middleware, admin bypass |
| Prompt Management | Langfuse Prompt Mgmt с TTL cache, fallback templates |
| Caching | 6-tier (semantic + 5 exact), Redis pipelines |

## Приоритеты реализации

### P1 — Next (высокая ценность, умеренная сложность)

1. **#225 Source Attribution** — цитаты в ответах. Metadata уже в Qdrant, нужно surfacing в generate+respond nodes. ~2-3 дня.
2. **#226 Prompt Injection Defense** — input sanitization. Критично для безопасности. ~2-3 дня.
3. **#229 User Feedback** — кнопки 👍/👎 после ответа. Langfuse scores API готов. Быстрый win для data flywheel. ~1-2 дня.

### P2 — Backlog (важно, но больше усилий)

4. **#227 Content Filtering** — зависит от выбора подхода (regex vs classifier vs LLM guardrail).
5. **#230 LLM-as-Judge** — async post-evaluation. Нужен отдельный бюджет на judge LLM calls.
6. **#228 HITL** — требует LangGraph interrupt(), UI кнопки в Telegram.
7. **#233 Dataset Management** — annotation workflow из Langfuse traces.
8. **#232 MCP Server** — крупный рефакторинг, ценность растёт с количеством агентов.
9. **#234 Graph RAG** — экспериментальный, нужна оценка value vs complexity.

## SDK / Инструменты (2026 best practices)

Результаты исследования: `docs/research/2026-02-13-*.md`

| Issue | Решение | Почему |
|-------|---------|--------|
| **#229 Feedback** | aiogram `CallbackData` factory + `langfuse.score()` API | Type-safe кнопки, scores уже в стеке |
| **#225 Sources** | Prompt engineering `[1][2]` + `parse_citations()` + Telegram HTML | Без новых зависимостей, metadata уже в Qdrant |
| **#226 Injection** | NeMo Guardrails v0.20.0 (`RunnableRails`) + Guardrails AI v0.8.0 | Colang DSL для правил, Validator Hub для extensibility |
| **#227 Filtering** | Detoxify `original-small` (98.28 AUC, CPU, ~30MB) | Лёгкая модель, no GPU, speedtoxify ONNX для 2-4x ускорения |
| **#230 LLM Judge** | Langfuse Evaluators (UI) + custom `AsyncJudge` с GPT-4o-mini | ~$1/day на 1000 traces × 2 evaluators |
| **#228 HITL** | LangGraph `interrupt()` + `AsyncRedisSaver` + Telegram callbacks | Redis checkpointer уже в стеке, dynamic interrupt в LangGraph 0.4+ |
| **#233 Datasets** | Langfuse Datasets API (`create_dataset_item` from traces) | Версионирование, CI eval на PR |
| **#232 MCP** | FastMCP 3.0 (70% market share) + OpenTelemetry | Декларативный API, Langfuse интеграция |
| **#234 Graph RAG** | LightRAG → nano-graphrag → LightRAG+Neo4j | 6,000x дешевле MS GraphRAG, EMNLP 2025 |

### Новые зависимости (оценка)

| Пакет | Размер | GPU | Контейнер |
|-------|--------|-----|-----------|
| `nemoguardrails>=0.20.0` | ~50MB | Нет | bot |
| `guardrails-ai>=0.8.0` | ~30MB | Нет | bot |
| `detoxify` | ~30MB модель | Нет (CPU) | bot |
| `fastmcp>=3.0` | ~5MB | Нет | новый сервис |
| `lightrag-hku` | ~20MB | Нет | новый сервис |
| `langgraph-checkpoint-redis` | ~2MB | Нет | bot |

### Стоимость (ежемесячная)

| Компонент | Стоимость |
|-----------|----------|
| LLM-as-Judge (GPT-4o-mini, 1000/day) | ~$30/month |
| LightRAG graph building (one-time) | ~$5 |
| Остальное | $0 (local/self-hosted) |

## Рекомендуемый порядок

```
#229 (feedback, 1-2d) → #225 (sources, 2-3d) → #226 (injection, 2-3d)
                      → #233 (datasets) → #230 (LLM judge) → #227 (filtering)
                      → #228 (HITL) → #232 (MCP) → #234 (Graph RAG)
```

Логика: сначала feedback loop (данные о качестве), потом прозрачность (sources), потом безопасность (injection), потом evaluation pipeline на основе собранных данных.

## Исследовательские отчёты

| Отчёт | Содержание |
|-------|-----------|
| [stack-audit.md](../research/2026-02-13-stack-audit.md) | Полный аудит Docker-стека, 19 контейнеров, extension points |
| [security-research.md](../research/2026-02-13-security-research.md) | Prompt injection, content filtering, cost control |
| [eval-research.md](../research/2026-02-13-eval-research.md) | User feedback, LLM-as-Judge, datasets, source attribution |
| [tools-research.md](../research/2026-02-13-tools-research.md) | MCP server, Graph RAG, HITL, A2A protocol |
