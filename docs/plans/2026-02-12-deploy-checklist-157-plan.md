# Plan: Deploy Checklist #157 — CallbackHandler + Dead Code Cleanup

**Issue:** #157 (follow-up от code review #154 — Conversation Memory)
**Branch:** `chore/parallel-backlog/deploy-157`
**Date:** 2026-02-12

## Решение по CallbackHandler

### Контекст

`_create_summarize_model()` в `telegram_bot/graph/graph.py:229-247` создаёт `ChatOpenAI` с `CallbackHandler()` из `langfuse.langchain`.

### Исследование (MCP: Exa + Context7)

| Аспект | CallbackHandler | @observe() |
|--------|----------------|------------|
| Context propagation | Не устанавливает Python context — spans не вкладываются правильно в async/LangGraph (#8009, #7055, #8584) | Использует OpenTelemetry automatic context propagation |
| Prompt linking | Баг: не линкует observations к managed prompts (#8584) | Работает корректно |
| Concurrent/async | Ненадёжен — handler state may not reflect true "current" span | Надёжен |
| Рекомендация Langfuse | "Avoid relying on the internal state of the callback handler" | "Prefer @observe or start_as_current_span" |

### Решение: УДАЛИТЬ CallbackHandler

`SummarizationNode` (LangGraph built-in) уже трассируется через `@observe` на уровне пайплайна.
`CallbackHandler` здесь:
1. Создаёт отдельный trace вместо вложенного span (баг context propagation)
2. Не даёт дополнительной информации — LiteLLM proxy уже логирует все LLM calls
3. Может вызывать дублирование traces

## Tasks

### Task 1: Удалить CallbackHandler из _create_summarize_model
- **File:** `telegram_bot/graph/graph.py:229-247`
- Удалить: import CallbackHandler, callbacks list, передачу callbacks в ChatOpenAI
- Оставить: функцию с упрощённым return

### Task 2: Удалить dead code из CacheLayerManager
- **File:** `telegram_bot/integrations/cache.py`
- Удалить: `store_conversation()` (L387-402) — dead code
- Удалить: `store_conversation_batch()` (L404-426) — вызов удалён в #154
- Удалить: `get_conversation()` (L428-442) — никогда не вызывается
- ОСТАВИТЬ: `clear_conversation()` (L444-452) — используется в /clear

### Task 3: Обновить тесты
- `tests/unit/integrations/test_cache_layers.py` — удалить тесты для удалённых методов
- `tests/unit/graph/test_cache_nodes.py` — удалить test_does_not_call_store_conversation_batch
- Mock-и в других тестах — удалить строки с mock store_conversation_batch

### Task 4: Написать deploy checklist
- **File:** `docs/checklists/deploy-memory-157.md`
- Pre-deploy, deploy steps, post-deploy live tests, rollback

### Task 5: Запустить тесты
- `uv run pytest tests/unit/integrations/test_cache_layers.py tests/unit/graph/test_cache_nodes.py -v -k "cache"`
