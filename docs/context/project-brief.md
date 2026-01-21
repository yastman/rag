# Project Brief для Claude Code

> Краткий контекст проекта для AI-ассистента

---

## Что это

**Contextual RAG Pipeline** — production система поиска по документам.

**Основной use case:** Поиск по Уголовному кодексу Украины (1,294 документа)

---

## Tech Stack

- **Python 3.12** + asyncio
- **Qdrant** — vector database
- **Redis Stack** — caching + semantic search
- **BGE-M3** — embeddings (dense + sparse + ColBERT)
- **Aiogram 3** — Telegram bot
- **Claude/OpenAI/Groq** — LLM providers

---

## Ключевые модули

```
src/
├── core/pipeline.py      <- RAG оркестратор
├── retrieval/            <- Поисковые движки (RRF, DBSF)
├── ingestion/            <- Парсинг документов
├── cache/                <- Redis 4-tier cache
├── contextualization/    <- LLM интеграции
└── config/               <- Настройки

telegram_bot/             <- Telegram интерфейс
```

---

## Текущий статус

- **Версия:** 2.8.0
- **Готовность:** 95% production-ready
- **Локально:** Всё работает
- **Production:** Требует настройки (см. status/local-vs-production.md)

---

## Правила работы

1. **Читай файл перед редактированием** (обязательно!)
2. **Используй Edit вместо Write** для существующих файлов
3. **Обновляй docs/tasks/** при работе над задачами
4. **Conventional Commits** для сообщений коммитов
5. **Тестируй изменения** перед коммитом

---

## Быстрые ссылки

- [docs/index.md](../index.md) — Навигация
- [docs/tasks/todo.md](../tasks/todo.md) — Что делать
- [docs/status/current-state.md](../status/current-state.md) — Статус

---

**Последнее обновление:** 2026-01-21
