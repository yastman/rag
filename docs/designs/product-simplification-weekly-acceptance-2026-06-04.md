# Отчет Приемки Недели

Дата: 2026-06-04

Ветка:
- `simplification/core`

Диапазон:
- `dev..simplification/core`

## Выполненные задачи

- Stage 0 source of truth: добавлены план упрощения, workflow Ярослава, решения Этапа 0 и индекс дизайн-документов.
- Stage 1 infrastructure: добавлены синтетический corpus, `golden_cases.yaml`, helper изолированных Qdrant-коллекций и `log_event()` с JSON formatter.
- Stage 2 entrypoint: добавлены `src/core/assistant.py`, `run_assistant_request()`, `AssistantResult`, `CoreDependencies` и контракт точки входа.
- Stage 3 live golden path: добавлен `make e2e-core-live` и первый live E2E через Qdrant + BGE-M3.
- Stage 5 expanded E2E: добавлены сценарии missing corpus, фильтров, source conflict, service policy, CRM/HITL и отказа LLM dependency.
- Stage 6 gates: live core E2E выведен из быстрых PR/CI проверок и закреплен как release/nightly/manual product proof.
- Stage 7 observability simplification: Langfuse/trace targets помечены как optional diagnostics и защищены contract tests.
- Stage 8 docs: README, local development docs, docs index и core product path index ведут к `make local-up && make e2e-core-live`.

## Проверки

- `uv run pytest tests/unit/test_product_events.py tests/e2e_core/test_qdrant_helpers.py tests/unit/e2e_core/test_live_harness.py tests/unit/core/test_assistant_entrypoint.py tests/contract/test_core_live_gate_contract.py tests/contract/test_trace_diagnostics_optional_contract.py tests/contract/test_core_live_gate_placement_contract.py -v`: прошло, 82 passed, 1 warning.
- `make e2e-core-live`: прошло, 8 passed, 1 warning.
- `make e2e-core-live-real-llm`: не запускалось; это ручной opt-in confidence check с реальным LLM provider и бюджетом.

## Доказательство Продукта

Запрос:
- `Найди квартиру-студию у моря до 120000 евро`

Найденные документы:
- `sunny_beach_studio`

Ответ:
- Проверяется по фактам `Sunny Beach` и `110000`, с запретом нерелевантных фактов `Mountain View Villa` и `Bansko`.

Почему это доказывает этап:
- `make e2e-core-live` создает изолированную Qdrant-коллекцию, индексирует синтетические документы, вызывает `run_assistant_request()` напрямую, использует BGE-M3 retrieval, проверяет grounded answer, missing corpus, фильтры, CRM/HITL policy и отказ LLM dependency без Telegram, Langfuse, voice, Mini App, k8s и trace validation.

## Решения Артема

### D1: Мерж `simplification/core -> dev`

Рекомендация:
- утвердить после решения по грязному `dev` worktree.

Почему:
- Пакет прошел focused unit/contract checks и live core E2E. Прямой merge в текущий основной `dev` checkout сейчас не выполнялся, потому что там есть незакоммиченные изменения в Telegram-файлах.

Риск:
- средний.

### D2: Реальный LLM режим

Рекомендация:
- оставить `make e2e-core-live-real-llm` ручным opt-in check.

Почему:
- Основной gate детерминированный и уже проходит с fake LLM. Реальный provider зависит от credentials, стоимости и доступности.

Риск:
- низкий.

## Рискованные Изменения

- Новые зависимости: нет новых runtime-сервисов; lockfile изменен существующими Python dependency updates.
- Новые сервисы: нет.
- Удаленные или архивированные поверхности: нет.
- Изменения поведения CRM: реальные CRM write paths не тронуты; E2E использует mock CRM/HITL policy.
- Langfuse/OTel стал обязательным путем: нет; trace/Langfuse проверки понижены до optional diagnostics.
- Изменения обязательных gates: `make e2e-core-live` закреплен как core product proof, live gate не входит в быстрый PR/CI путь.

## Запрос

Принять или заблокировать мерж:
- `simplification/core -> dev` до текущего HEAD ветки `simplification/core`
  с последним коммитом `docs: finalize simplification acceptance package`.
