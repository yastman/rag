# Worker: BGE-M3 Retry & Resilience (#210)

## TASK

Реализуй план `docs/plans/2026-02-12-bge-m3-retry-resilience-plan.md` — 5 тасков.
Цель: tenacity retry + granular timeout на BGE-M3, graceful fallback, Langfuse scores, Loki alerts.

## SKILLS (вызывай в этом порядке)

1. `/executing-plans` — пошаговое выполнение плана (TDD: test → fail → implement → pass → commit)
2. `/requesting-code-review` — code review ПОСЛЕ завершения всех тасков (перед финальным коммитом)
3. `/verification-before-completion` — финальная проверка перед тем как объявить "готово"

## MCP TOOLS

- **Context7**: ПЕРЕД реализацией внешних SDK/API используй MCP Context7 (`resolve-library-id` → `query-docs`) для актуальной документации tenacity, httpx
- **Exa**: Для поиска решений, примеров кода, свежих best practices используй MCP Exa (`web_search_exa`, `get_code_context_exa`)

## GIT

- Ветка: `fix/210-bge-m3-retry-resilience` (создай от `main`)
- ЗАПРЕЩЕНО `git add -A`. ПЕРЕД коммитом: `git diff --cached --stat` — убедись что ТОЛЬКО нужные файлы
- НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки
- Коммит после каждого таска (5 коммитов)

## COMMANDS

```bash
uv run pytest tests/unit/integrations/test_embeddings.py -v          # Task 1 tests
uv run pytest tests/unit/graph/test_cache_nodes.py -v                # Task 2 tests
uv run pytest tests/unit/graph/test_edges.py -v                      # Task 2 edge tests
uv run pytest tests/unit/test_bot_handlers.py -v                     # Task 3 tests
uv run pytest tests/unit/ -n auto --timeout=30                       # Full suite
uv run pytest tests/integration/test_graph_paths.py -v               # Integration
make check                                                           # Lint + types
```

## CRITICAL NOTES

- `tenacity>=8.2.0` уже в `pyproject.toml` (не надо добавлять)
- `@observe` должен быть ВНЕШНИМ декоратором, `@_embed_retry` ВНУТРЕННИМ (один span на все retry)
- `cache_hit=False` при embedding error (НЕ True!) — чтобы не загрязнять метрики cache hit
- `route_cache` в `edges.py` проверяет `embedding_error` ПЕРВЫМ, до `cache_hit`
- `_get_client()` создаёт `httpx.AsyncHTTPTransport(retries=1)` для connect-level + tenacity для protocol/read
- Timeout: `httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)` вместо flat 120s
- Loki rules используют `|=` (exact substring), не `|~` (regex) — per Grafana best practices
- Тесты для retry используют `patch("httpx.AsyncClient.post", side_effect=...)` с call_count
